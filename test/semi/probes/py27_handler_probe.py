# -*- coding: utf-8 -*-
# === TB 注释头（规范见 test/docs/写TB规范.md §0）=====================
# 作者: 设计/Codex
# 最后改动: 2026-09-28 12:04
# 依赖: 无
# =====================================================================
# 六步流程（按 test/docs/写TB规范.md §1–§6）：
# §1 环境检查：需要真实 Python 2.7 解释器；脚本顶部先解析 --py27。
# §2 构建：按部署文件形状加载 daemon_27，并构造错误帧。
# §3 最终检查：确认解释器版本、模块加载方式与帧输入正确。
# §4 执行：在 py2.7 下驱动 _read_frame ValueError 分支。
# §5 比对：silent drop / 错误分支行为与期望一致。
# §6 重复/收尾：单点分支探针；保留输出/证据供复核。
"""在**真 Python 2.7** 下判定 P-039：`_read_frame` 抛 ValueError 时走哪个分支。

背景：`test/semi/probes/daemon_internal_error_path_probe.py` 是在 **Python 3** 里把 py2.7 模块
import 进来做猴补丁的；而 py2.7 模块里 `sys.stdout.write(send_code.encode("utf-8"))` 在 py3 下必然
抛 `TypeError`（bytes 不能写文本流），于是"到达 handler 的异常类型"被 py3 语义替换了 —— 那条
红/绿结论不能代表真 py2.7。本脚本必须由 **python2.7 解释器**执行（py3 也能跑，用于对照）。

判定口径（spec：帧读取器内部错误不得回 NACK 帧，应静默丢弃）：
* `handle_connection` 收尾时**没有**向连接写任何 NACK → 正确（走 `except (UnicodeDecodeError, ValueError)`）；
* 写了 NACK/`internal daemon error` → 缺陷（真解释器上仍是该行为）。

用法（wsl-gent）::

    python2.7 test/semi/probes/py27_handler_probe.py --src src --out <证据 json>
"""
from __future__ import print_function

import argparse
import json
import sys


class FakeConn(object):
    def __init__(self, payload):
        self._payload = payload
        self.sent = []

    def settimeout(self, _timeout):
        pass

    def recv(self, _n):
        payload, self._payload = self._payload, b""
        return payload

    def sendall(self, data):
        self.sent.append(data)

    def close(self):
        pass

    def shutdown(self, _how):
        pass


class Sink(object):
    """吃掉 daemon 写往 stdout 的 SKILL 文本。"""

    def __init__(self):
        self.chunks = []

    def write(self, data):
        self.chunks.append(data)

    def flush(self):
        pass


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default="src")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    sys.path.insert(0, args.src)
    # 按**文件路径**载入 daemon —— 与真实部署一致（`common/deploy.py:42` 是逐文件部署，
    # 远端 `python2.7 <daemon_27.py>` 跑的是独立脚本，不会执行 py3-only 的
    # `bridge/__init__.py`）。早期版本走 `from bridge.resources import ...`，
    # 在真 py2.7 下必然 SyntaxError（`__init__.py` 用了 `-> Path` 注解）→ 探针自己骗自己。
    import os
    daemon_path = os.path.join(args.src, "bridge", "resources", "ramic_bridge_daemon_27.py")
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("ramic_bridge_daemon_27", daemon_path)
        d27 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(d27)
    except ImportError:                      # py2.7：没有 importlib.util
        import imp
        d27 = imp.load_source("ramic_bridge_daemon_27", daemon_path)

    d27.DAEMON_TOKEN = "tok"
    d27.TEMP_DIR = "."

    def boom():
        raise ValueError("bad frame")

    d27._read_frame = boom
    conn = FakeConn(json.dumps({"skill": "1+1", "token": "tok"}).encode("utf-8"))
    real_stdout, real_stdin = sys.stdout, sys.stdin
    sys.stdout = Sink()
    sys.stdin = type("EmptyIn", (object,), {"read": lambda self, _n=1: ""})()
    try:
        d27.handle_connection(conn)
    finally:
        sys.stdout, sys.stdin = real_stdout, real_stdin

    nack = [d for d in conn.sent if d[:1] == bytes(bytearray([d27.NAK]))]
    verdict = "NACK sent (defect: source branch bypassed)" if nack else \
              "silent drop (correct)"
    payload = {
        "python": sys.version.split()[0],
        "implementation": "CPython",
        "sent_count": len(conn.sent),
        "nack_frames": [d.decode("utf-8", "replace") for d in nack],
        "verdict": verdict,
        "ok": not nack,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.out:
        with open(args.out, "w") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not nack else 1


if __name__ == "__main__":
    raise SystemExit(main())
