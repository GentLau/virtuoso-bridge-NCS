# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-28 17:25
# 依赖: 8127 业务面 + calprobe token；py-spy（仅在卡住时抓栈需要）
# =======================================================================
# 六步流程：① 自检 = /health 可达 + token 可用（不通过即停）；②③ 每轮用唯一 job 名，
# 不复用旧 run_dir；④ 只做被测动作（一次 spectre.run，2 任务 / max_workers=2）；
# ⑤ 读回 = 客户端 artifact 目录 vs 远端 run_dir + /health 的 in_flight 轨迹；
# ⑥ 不清现场：卡住时保留 .vbtmp-* / 日志 / py-spy 栈，供中层定位（P-076）。
"""P-076 复现尝试：与 design_iterate_tb r2_sim 同口径的 2 任务 spectre.run。

每轮：POST /api/operation (spectre.run, calprobe token)，同时后台轮询 /health 记录
in_flight；请求超过 --hang-after 秒仍未返回就 py-spy dump 8127 进程栈（定位挂在哪）。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = "http://127.0.0.1:8127"
API = f"{BASE}/api/operation"
HEALTH = f"{BASE}/health"
TOKEN = "d6af595b342647b58ec63ca6"
STAGE = ROOT / "test" / "artifacts" / "evidence" / "round7" / "design-iterate" / "stage"
OUT = ROOT / "test" / "artifacts" / "evidence" / "p076-repro"


def http_json(url: str, payload: dict | None = None, timeout: float = 30) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"},
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def server_pid(port: str = "8127") -> int:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "
         f"'server.api_server --port {port}' }} | Select-Object -First 1).ProcessId"],
        capture_output=True, text=True,
    )
    return int(out.stdout.strip().splitlines()[-1])


class Monitor(threading.Thread):
    def __init__(self, hang_after: float, pid: int, tag: str) -> None:
        super().__init__(daemon=True)
        self.hang_after = hang_after
        self.pid = pid
        self.tag = tag
        self.t0 = time.monotonic()
        self.samples: list[tuple[float, int]] = []
        self.dumped = False
        self.stop = threading.Event()

    def run(self) -> None:
        while not self.stop.is_set():
            try:
                health = http_json(HEALTH, timeout=5)
                inflight = int(((health.get("data") or {}).get("in_flight", -1)))
            except Exception:  # noqa: BLE001
                inflight = -1
            elapsed = time.monotonic() - self.t0
            self.samples.append((round(elapsed, 1), inflight))
            if (not self.dumped and elapsed > self.hang_after and inflight == 1):
                self.dumped = True
                dump = OUT / f"pyspy-{self.tag}.txt"
                dump.parent.mkdir(parents=True, exist_ok=True)
                result = subprocess.run(
                    [str(Path(sys.executable).parent / "Scripts" / "py-spy.exe"),
                     "dump", "--pid", str(self.pid), "--nonblocking"],
                    capture_output=True, text=True,
                )
                dump.write_text(result.stdout + result.stderr, encoding="utf-8")
                print(f"[monitor] dumped stack to {dump} (rc={result.returncode})")
            time.sleep(1.0)


def run_round(index: int, hang_after: float, pid: int) -> dict:
    tag = f"round{index}"
    stamp = time.strftime("%H%M%S")
    jobs = (f"p076_{stamp}_{index}_ac", f"p076_{stamp}_{index}_tran")
    tasks = [
        {"job": jobs[0], "netlist": str(STAGE / "r2_ac.scs"), "parse": "auto"},
        {"job": jobs[1], "netlist": str(STAGE / "r2_tran.scs"), "parse": "auto"},
    ]
    monitor = Monitor(hang_after, pid, tag)
    monitor.start()
    started = time.monotonic()
    try:
        body = http_json(API, {
            "operation": "spectre.run", "token": TOKEN, "tasks": tasks,
            "max_workers": 2, "parse": "auto", "download": True,
            "keep_run_dir": True, "timeout": 1200,
        }, timeout=hang_after + 60)
        elapsed, error = time.monotonic() - started, None
    except Exception as exc:  # noqa: BLE001
        elapsed, error, body = time.monotonic() - started, f"{type(exc).__name__}: {exc}", {}
    finally:
        monitor.stop.set()
        monitor.join(timeout=5)
    values = ((body.get("data") or {}).get("value") or {}).get("runs") or []
    record = {
        "round": index, "seconds": round(elapsed, 1), "error": error,
        "ok": body.get("ok"),
        "runs": [{"job": (r.get("value") or {}).get("job"),
                  "status": (r.get("value") or {}).get("status"),
                  "error": r.get("error")} for r in values],
        "in_flight_max": max((n for _t, n in monitor.samples), default=-1),
        "stack_dumped": monitor.dumped,
    }
    print(json.dumps(record, ensure_ascii=False), flush=True)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=6)
    parser.add_argument("--hang-after", type=float, default=90.0)
    parser.add_argument("--base", default=BASE,
                        help="业务面地址（默认 8127；独立面/临时面用这个参数指过去）")
    args = parser.parse_args()
    global API, HEALTH
    API, HEALTH = f"{args.base.rstrip('/')}/api/operation", f"{args.base.rstrip('/')}/health"
    port = args.base.rstrip("/").rsplit(":", 1)[-1]
    pid = server_pid(port)
    print(f"{args.base} pid={pid}")
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    for index in range(1, args.rounds + 1):
        records.append(run_round(index, args.hang_after, pid))
        (OUT / "rounds.json").write_text(
            json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
