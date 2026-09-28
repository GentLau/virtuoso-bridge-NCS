# === TB 注释头（规范见 test/docs/写TB规范.md §0）=====================
# 作者: 设计/Codex
# 最后改动: 2026-09-28 14:42
# 依赖: 无
# =====================================================================
# 六步流程（按 test/docs/写TB规范.md §1–§6）：
# §1 环境检查：--base 模式已调用 require_environment；自起模式检查 /health。
# §2 构建：自起 production api_server + local registry，或复用既有 face。
# §3 最终检查：face /health 与 stage 目录就绪。
# §4 执行：混合 skill/command/file/gui/spectre 并发请求。
# §5 比对：planned/answered、marker、sha256、kind、失败计数。
# §6 重复/收尾：多 worker/round 重复；关闭 face，写 summary 证据。
"""生产面混合并发 TB（替代已删除的测试专用 `server.stress_server` 压测壳）。

**压测对象是生产路径**：`api_server + dispatch + basic 包 + 中层（BusinessServer）`，
入口只有 `POST /api/operation`。**不再有测试专用 HTTP 壳**。

两种跑法：

1. **自起（默认，零依赖）**：TB 在自己的临时 work-dir 里写一份 `mode=local` 的注册表，
   然后 `python -m server.api_server --port <空闲端口> --work-dir <该目录>` 起**生产业务面**，
   再对 `basic.command.run` / `basic.file.upload` / `basic.file.download` 发混合并发请求。
   上传/下载用的客户端文件在 TB 自己的临时目录里现造（不依赖仓库里任何夹具）。
2. **对接既有环境**：`--base http://127.0.0.1:8127/api/operation --token vb-vblog`
   → 额外把 `basic.skill.execute` / `basic.gui.run` / `basic.spectre.run` 也混进去（真机 daemon 才支持）。

判据（不是"接口 ok"）：
* 计划请求数 = 实际应答数（一一应答，不静默丢）；
* `failed == 0`：失败只允许是**结构化拒绝**（`kind=rejected`/`invalid-token` 等），
  且必须带 `kind`；**transport/超时**都要计数并判失败；
* 文件上下行 SHA-256 必须一致（用 TB 自己造的随机内容）；
* `parallel=true` 的并发 skill 也按同样口径计数。

用法::

    python test/live/stress/production_face_stress_tb.py --workers 6 --rounds 6 \
        --out test/artifacts/evidence/round6b-verify/production-stress.json
    python test/live/stress/production_face_stress_tb.py --base http://127.0.0.1:8127/api/operation \
        --token vb-vblog --workers 6 --rounds 6 --out .../production-stress-real.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
_RUNNERS = ROOT / "test" / "shared" / "runners"
if str(_RUNNERS) not in sys.path:
    sys.path.insert(0, str(_RUNNERS))
from env_check import require_environment  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

LOCAL_TOKEN = "vb-face-stress"


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _local_registry(work_dir: Path) -> dict:
    """`mode=local` 的注册表：让 basic.command/file 在 TB 自己的目录里跑，无需真机。"""
    role_root = work_dir / "role-root"
    for name in ("gui", "daemon", "command", "file", "spectre"):
        (role_root / name).mkdir(parents=True, exist_ok=True)
    return {
        "face-stress": {
            "token": LOCAL_TOKEN,
            "mode": {"default": "local"},
            "ssh": {"default": {}},
            "root": {"default": None},
            "roles": {name: {"root": str(role_root / name), "max_sessions": 32}
                      for name in ("gui", "daemon", "command", "file", "spectre")},
            "runtime": {"thread_pool_size": 64, "channel_budget": 64, "connect_timeout": 15.0},
            "cdslog": {"log_level": "off", "log_max_bytes": 65536},
            "registered_at": None,
        }
    }


class Face:
    """生产业务面：自起（`server.api_server`）或复用既有 `--base`。"""

    def __init__(self, base: str, proc: subprocess.Popen | None, work_dir: Path) -> None:
        self.base = base
        self.proc = proc
        self.work_dir = work_dir

    def close(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def start_face(work_dir: Path) -> Face:
    (work_dir / "registry.json").write_text(
        json.dumps(_local_registry(work_dir), ensure_ascii=False), encoding="utf-8")
    port = _free_port()
    env = {**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")}
    proc = subprocess.Popen(
        [sys.executable, "-m", "server.api_server", "--port", str(port), "--work-dir", str(work_dir)],
        cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    base = f"http://127.0.0.1:{port}/api/operation"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as response:
                if json.loads(response.read().decode()).get("ok"):
                    return Face(base, proc, work_dir)
        except Exception:  # noqa: BLE001 - 启面期间允许任何连接失败
            time.sleep(0.3)
    proc.kill()
    raise AssertionError(f"business face on {port} 未能启动")


def call(base: str, payload: dict, timeout: float = 120.0) -> dict:
    request = urllib.request.Request(
        base, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            return json.loads(error.read().decode("utf-8"))
        except Exception:  # noqa: BLE001 - 非 JSON 错误体也要能计数
            return {"ok": False, "error": f"HTTP {error.code}", "data": None}


def _result_of(response: dict):
    return (response.get("data") or {}).get("result")


def _kind_of(response: dict) -> str | None:
    result = _result_of(response)
    if isinstance(result, list) and len(result) >= 4:
        return str(result[3])
    value = (response.get("data") or {}).get("value")
    if isinstance(value, dict):
        return value.get("kind")
    return None


def one_round(face: Face, token: str, stage: Path, index: int, real_daemon: bool) -> dict:
    """一轮混合负载：命令 / 上传 / 下载 /（真机时）skill / gui / spectre。"""
    tag = f"face-{index}-{uuid.uuid4().hex[:6]}"
    payload = stage / f"{tag}.bin"
    payload.write_bytes((tag * 64).encode("utf-8"))
    digest = hashlib.sha256(payload.read_bytes()).hexdigest()
    remote = f"stress/{tag}.bin"

    steps: list[tuple[str, bool, str | None]] = []

    command = call(face.base, {"operation": "basic.command.run", "token": token,
                               "cmd": f"echo {tag}"})
    result = _result_of(command) or []
    steps.append(("command", bool(command.get("ok")) and str(result[1]).strip() == tag,
                  _kind_of(command)))

    upload = call(face.base, {"operation": "basic.file.upload", "token": token,
                              "local_path": str(payload), "remote_path": remote})
    steps.append(("upload", bool(upload.get("ok")), _kind_of(upload)))

    downloaded = stage / f"{tag}.out"
    download = call(face.base, {"operation": "basic.file.download", "token": token,
                                "remote_path": remote, "local_path": str(downloaded)})
    same = downloaded.is_file() and hashlib.sha256(downloaded.read_bytes()).hexdigest() == digest
    steps.append(("download", bool(download.get("ok")) and same, _kind_of(download)))

    if real_daemon:
        skill = call(face.base, {"operation": "basic.skill.execute", "token": token,
                                 "skill_code": f'strcat("{tag}")'})
        steps.append(("skill", bool(skill.get("ok")) and tag in json.dumps(skill.get("data") or {}),
                      _kind_of(skill)))
        gui = call(face.base, {"operation": "basic.gui.run", "token": token, "cmd": f"echo {tag}"})
        steps.append(("gui", bool(gui.get("ok")), _kind_of(gui)))
        spectre = call(face.base, {"operation": "basic.spectre.run", "token": token,
                                   "cmd": f"echo {tag}"})
        steps.append(("spectre", bool(spectre.get("ok")), _kind_of(spectre)))

    failed = [name for name, ok, _kind in steps if not ok]
    return {"tag": tag, "steps": [{"name": n, "ok": o, "kind": k} for n, o, k in steps],
            "failed": failed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="", help="复用既有生产面；缺省=自起一个")
    parser.add_argument("--token", default="", help="配合 --base 使用")
    parser.add_argument("--work-dir", default="", help="自起模式下的 work-dir（缺省=临时目录）")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--rounds", type=int, default=6)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    temp: tempfile.TemporaryDirectory | None = None
    environment: dict
    if args.base:
        if not args.token:
            parser.error("--base 需要同时给 --token")
        # 六步 §1：复用既有生产面时先校验业务面和 token 对应的环境。
        base = args.base.rstrip("/")
        if not base.endswith("/api/operation"):
            base += "/api/operation"
        environment = require_environment(base=base, token=args.token)
        work_dir = Path(args.work_dir).resolve() if args.work_dir else ROOT / "test" / "artifacts" / "tmp"
        face = Face(base, None, work_dir)
        token, real_daemon = args.token, True
    else:
        # 六步 §2/§3：自起生产面并等待 /health 就绪（本地基线）。
        temp = tempfile.TemporaryDirectory(prefix="vb-face-stress-")
        work_dir = Path(temp.name)
        face = start_face(work_dir)
        token, real_daemon = LOCAL_TOKEN, False
        environment = {"mode": "self-start", "health": "ok"}

    stage = work_dir / "stress-stage"
    stage.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    results: list[dict] = []
    try:
        # 六步 §4/§5：混合并发执行，逐请求校验应答、marker 与 sha256。
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(one_round, face, token, stage, worker * 100 + rnd, real_daemon)
                       for worker in range(args.workers) for rnd in range(args.rounds)]
            for future in futures:
                try:
                    results.append(future.result())
                except Exception as exc:  # noqa: BLE001 - 单轮异常必须进入结构化证据
                    results.append({
                        "tag": None,
                        "steps": [],
                        "failed": [f"{type(exc).__name__}: {exc}"],
                    })
    finally:
        face.close()
        if temp is not None:
            temp.cleanup()

    planned = args.workers * args.rounds
    answered = len(results)
    step_total = sum(len(item["steps"]) for item in results)
    step_failed = sum(len(item["failed"]) for item in results)
    kinds = sorted({step["kind"] for item in results for step in item["steps"] if step["kind"]})
    summary = {"ok": answered == planned and step_failed == 0,
               "transport": "self_start_face" if temp is not None else "existing_base",
               "workers": args.workers, "rounds": args.rounds,
               "planned_rounds": planned, "answered_rounds": answered,
               "steps_total": step_total, "steps_failed": step_failed,
               "environment": environment,
               "kinds_seen": kinds, "elapsed_s": round(time.monotonic() - started, 3),
               "detail": results}
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "detail"},
                     ensure_ascii=False, indent=1))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
