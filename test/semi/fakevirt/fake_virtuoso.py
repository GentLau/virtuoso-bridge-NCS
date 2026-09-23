#!/usr/bin/env python3
"""fake Virtuoso —— CIW 侧测试替身（lab 资源）。

职责边界（fake 的部分）
=======================
只替代 **Virtuoso/CIW 本身**；链路上的其它组件全部是项目原码：

    [fake Virtuoso (本文件)] --ipcBeginProcess 语义--> [真 ramic_bridge_daemon_*.py]
            ^                                                |
            | 读 daemon stdout（裸 SKILL 文本）               | TCP: 02/15 + JSON + 1e
            | 执行 SKILL（skill_ops.py）                      v
            +-- 回帧 02 + %L(value) + 1e                [真 middle / 真 client]
                 log 请求时同一写内追加 02 + path + 1f + start + 1f + end + 1e

真实 CIW 的对应实现见 ``src/bridge/resources/ramic_bridge.il`` 的
``RBIpcDataHandler`` / ``RBIpcErrHandler``；本文件复刻其可观测行为。

用法（lab 内）：

    python3 fake_virtuoso.py --daemon /opt/fake/virtuoso/ramic_bridge_daemon_3.py \
        --bind 0.0.0.0 --port 65121 --token vb-lab1 \
        --temp-dir ~/.virtuoso-bridge/fakevirt/tmp

行为说明：
  * ``--bind``：真机部署时 daemon 绑 127.0.0.1（客户端经 SSH 隧道进来）；
    lab 里为了让 Windows 直连可绑 0.0.0.0 或身份 IP。
  * fake CDS.log 位于 ``<temp-dir>/CDS.log``；log 请求的 [start,end) 偏移
    以该文件字节长度计算，语义与真机 ``hiFlushLogFile()/fileLength()`` 对齐。
"""

from __future__ import annotations

import argparse
import os
import re
import socket
import subprocess
import sys
import threading
from collections import deque

from skill_ops import Ctx, SkillError, eval_expr, to_lisp

STX = 0x02
NAK = 0x15
RS = 0x1E
US = 0x1F

#: 注意 re.S：daemon 的 body 可能跨行（`let(((__vb_r progn(<skill>\n))) ...`），
#: 没有 DOTALL 时 `.` 不跨行、`$` 也就永远匹配不上（2026-09-22 实测）。
_DIRECTIVE_RE = re.compile(r"^RBDLogOn=(t|nil) (.*)$", re.S)
#: 多行 body 也适用的前缀判定（`_DIRECTIVE_RE` 的 `$` 不跨行）
_DIRECTIVE_PREFIX_RE = re.compile(r"^RBDLogOn=(t|nil) ", re.S)
#: 现行 daemon 的包装：`let(((__vb_r progn(<skill>\n))) hiFlush() __vb_r)`。
#: 必须显式吃掉 `progn(`，否则贪婪分组会把 `progn(` 一起captured（实测被当成函数调用）。
_SINGLE_RE = re.compile(r"^let\(\(\(__vb_r progn\((.*)\)\)\) hiFlush\(\) __vb_r\)$", re.S)
_LOAD_RE = re.compile(r'^load\("([^"]+)"\) hiFlush\(\) _vb_eval_result$')
_BANNER_RE = re.compile(r"\[RB-banner\] pid=(\d+) bind=(\S+) host=(\S+) ip=(\S+) user=(\S+)")
_DEFAULT_TEMP_DIR = os.path.join(
    os.path.expanduser("~"), ".virtuoso-bridge", "fakevirt", "tmp"
)


class FakeCIW:
    """fake Virtuoso 主进程：冒号左边的那个 'CIW'。"""

    def __init__(self, opts: argparse.Namespace) -> None:
        self.daemon = opts.daemon
        self.python = opts.python
        self.bind = opts.bind
        self.port = opts.port
        self.token = opts.token
        self.temp_dir = opts.temp_dir or _DEFAULT_TEMP_DIR
        self.log_path = os.path.join(self.temp_dir, "CDS.log")
        self.quiet = opts.quiet
        self.proc: subprocess.Popen[bytes] | None = None
        self.ctx: Ctx | None = None
        self.stderr_lines: deque[str] = deque(maxlen=500)
        self.daemon_pid: int | None = None
        self.daemon_bind: str | None = None

    # -------------------------------------------------------------- 启动
    def start(self) -> None:
        os.makedirs(self.temp_dir, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8"):
            pass  # 保证 CDS.log 存在

        self.ctx = Ctx(
            hostname=socket.gethostname(),
            variables={"RBDToken": self.token, "RBPort": self.port},
            log_path=self.log_path,
            cwd=self.temp_dir,
        )

        argv = [
            self.python,
            self.daemon,
            self.bind,
            str(self.port),
            self.token,
            self.temp_dir,
        ]
        self._ciw(f"fake Virtuoso CIW (IC6.1.8-fake) — daemon spawn: {argv}")
        self.proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.temp_dir,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        threading.Thread(target=self._pump_stderr, daemon=True).start()
        self._ciw(f"daemon pid={self.proc.pid} temp_dir={self.temp_dir}")

    # -------------------------------------------------------------- 日志
    def _ciw(self, message: str) -> None:
        if not self.quiet:
            print(f"[fake-ciw] {message}", flush=True)

    def _pump_stderr(self) -> None:
        assert self.proc is not None and self.proc.stderr is not None
        for raw in iter(self.proc.stderr.readline, b""):
            line = raw.decode("utf-8", errors="replace").rstrip("\n")
            self.stderr_lines.append(line)
            match = _BANNER_RE.search(line)
            if match:
                self.daemon_pid = int(match.group(1))
                self.daemon_bind = match.group(2)
                self._ciw(
                    f"daemon banner: pid={self.daemon_pid} bind={self.daemon_bind} "
                    f"host={match.group(3)} ip={match.group(4)}"
                )
                self._ciw("ready")
            else:
                self._ciw(f"[daemon stderr] {line}")

    # -------------------------------------------------------------- 主循环
    def run(self) -> int:
        self.start()
        assert self.proc is not None and self.proc.stdout is not None
        pending = ""
        for raw in iter(self.proc.stdout.readline, b""):
            line = raw.decode("utf-8", errors="replace").rstrip("\n")
            # 当前 daemon 的包装可能是多行：
            #   let(((__vb_r progn(<skill>
            #   ))) hiFlush() __vb_r)
            # 逐行处理会把前缀当成完整 payload（"unrecognized daemon payload"）。
            # 这里按"已知完整形状"成帧；不成形的行仍走旧路径（保持协议语义不变）。
            # 真实行形如 `RBDLogOn=t let(((__vb_r progn(<skill>`，body 可能跨行；
            # 判断"body 是否已经完整"，不完整就继续累积（旧行为只对单行 body 正确）。
            candidate = f"{pending}\n{line}" if pending else line
            directive = _DIRECTIVE_PREFIX_RE.match(candidate)
            if pending or directive:
                body = candidate.split(" ", 1)[1] if directive else ""
                if body and (_SINGLE_RE.match(body) or _LOAD_RE.match(body)):
                    pending = ""
                    self._handle_payload(candidate)
                    continue
                pending = candidate
                if len(pending) > 200_000:      # 防御：异常输出不无限累积
                    self._ciw(f"unrecognized daemon write (ignored): {pending[:80]!r}")
                    pending = ""
                continue
            self._handle_payload(line)
        code = self.proc.wait()
        self._ciw(f"daemon exited with code {code}")
        return code

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    # -------------------------------------------------------------- IPC
    def _handle_payload(self, payload: str) -> None:
        match = _DIRECTIVE_RE.match(payload)
        if not match:
            self._ciw(f"unrecognized daemon write (ignored): {payload[:120]!r}")
            return
        log_on = match.group(1) == "t"
        body = match.group(2)

        lo_start = self._log_size()
        try:
            expr = self._extract_skill(body)
            value = eval_expr(expr, self.ctx)
            ok, out = True, to_lisp(value)
        except SkillError as exc:
            expr = body
            ok, out = False, exc.payload()
        except Exception as exc:  # noqa: BLE001 — 模拟 CIW 层意外错误也要回帧
            expr = body
            ok, out = False, to_lisp(f"*Error* fake-ciw: {exc}")
        lo_end = self._log_size()

        frames = bytes([STX if ok else NAK]) + out.encode("utf-8") + bytes([RS])
        if log_on:
            meta = f"{self.log_path}\x1f{lo_start}\x1f{lo_end}\x1e"
            frames += bytes([STX]) + meta.encode("utf-8")
        assert self.proc is not None and self.proc.stdin is not None
        self.proc.stdin.write(frames)
        self.proc.stdin.flush()
        tag = " [log]" if log_on else ""
        self._ciw(f"eval {expr!r} -> {out}{tag}")

    def _log_size(self) -> int:
        try:
            return os.path.getsize(self.log_path)
        except OSError:
            return 0

    @staticmethod
    def _extract_skill(body: str) -> str:
        single = _SINGLE_RE.match(body)
        if single:
            # daemon 在闭合括号前插了一个换行（用于终止行尾注释），提取后要去掉
            return single.group(1).strip()
        load = _LOAD_RE.match(body)
        if load:
            path = load.group(1)
            with open(path, "r", encoding="utf-8") as fh:
                content = fh.read()
            prefix = "_vb_eval_result = progn("
            if content.startswith(prefix) and content.rstrip().endswith(")"):
                inner = content[len(prefix):].rstrip()
                return inner[:-1].strip()
            raise SkillError(f"*Error* load: unsupported file content - {path}")
        raise SkillError("*Error* eval: unrecognized daemon payload")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="fake Virtuoso CIW (lab test double)")
    parser.add_argument("--daemon", required=True,
                        help="真实 ramic_bridge_daemon_3.py 的路径")
    parser.add_argument("--python", default="python3",
                        help="启动 daemon 的解释器（默认 python3）")
    parser.add_argument("--bind", default="127.0.0.1",
                        help="daemon 监听地址（真机为 127.0.0.1；lab 可 0.0.0.0）")
    parser.add_argument("--port", type=int, required=True, help="daemon 监听端口")
    parser.add_argument("--token", required=True, help="RBD 鉴权 token")
    parser.add_argument("--temp-dir", default=_DEFAULT_TEMP_DIR,
                        help="工作目录（fake CDS.log 与临时 .il 都放这里）")
    parser.add_argument("--quiet", action="store_true", help="少打日志")
    args = parser.parse_args(argv)

    ciw = FakeCIW(args)
    try:
        return ciw.run()
    except KeyboardInterrupt:
        ciw._ciw("interrupted; stopping daemon")
        ciw.stop()
        return 130


if __name__ == "__main__":
    sys.exit(main())
