# -*- coding: utf-8 -*-
"""S4-scale-100 的**负向对照**：故意把 registry 指错端口，验证"答非自己的 token"能被抓到。

为什么单独一个进程：P-072 口径定为「**一进程一 work root**」（`init_work_dir` 一次性、
没有测试 override），而父进程已经绑定了自己的 work dir。所以负向对照必须在**子进程**
里绑定 `--work-dir`（见 `test/docs/工作根与测试姿势.md`）。

用法（由 `test/live/flows/scale_100_tb.py` 调起）::

    python test/shared/fixtures/scale100_negative_control.py \
        --work-dir <control_dir> --wrong-port 6701

约定：registry 里 `cloud-a`/`cloud-b` 都存在，但 `cloud-b` 的 daemon 端口被改成
`cloud-a` 的监听端口 → 用 `cloud-b` 的 token 打过去必然拿到 NAK 或别人的答复。
stdout 最后一行是 JSON：``{"ok": ..., "output": ..., "errors": [...]}``。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--wrong-port", type=int, required=True)
    parser.add_argument("--token", default="cloud-b")
    args = parser.parse_args(argv)

    work_dir = Path(args.work_dir)
    registry_path = work_dir / "registry.json"
    users = json.loads(registry_path.read_text(encoding="utf-8"))
    # 把 cloud-b 的 daemon 指到 cloud-a 的监听上
    users["cloud-b"]["roles"]["daemon"]["daemon_port"] = args.wrong_port
    registry_path.write_text(json.dumps(users, ensure_ascii=False, indent=1),
                             encoding="utf-8")

    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
    from common.paths import init_work_dir           # noqa: E402
    from transport.middle import BusinessServer      # noqa: E402

    init_work_dir(str(work_dir))
    result = BusinessServer().execute_skill("RBDToken", timeout=30, token=args.token)
    payload = {"ok": bool(result.ok),
               "output": (result.output or "").strip().strip('"'),
               "errors": list(result.errors or [])}
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
