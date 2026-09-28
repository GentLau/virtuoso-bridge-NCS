# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-28 20:45
# 依赖: 无
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
#   ① 环境/前置：见正文的 require_environment 或首段只读探测（本节不适用时正文写明）；
#   ②③ 构建/校验被改对象：由用例内建前置保证；④ 只做被测动作；
#   ⑤ 打印期望 vs 实测（判据见正文）；⑥ 半真机不清理现场，留下状态便于复核。
"""In-process probe for the pyapi.packages.symbol package."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from common.paths import init_work_dir  # noqa: E402
from pyapi.packages import symbol  # noqa: E402
from transport.middle import BusinessServer  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

#: 默认打到常驻 vblog 实例；用 `--token` 可换实例（例如 PDK 实例
#: `d6af595b342647b58ec63ca6`，它的 cds.lib 里才有 SRX65/DI65 这些库）
TOKEN = "vb-vblog"


def main() -> int:
    init_work_dir(str(ROOT / "test" / "artifacts" / "env" / "log-vblog"))
    middle = BusinessServer()
    pkg = symbol.Package(middle)
    argv = list(sys.argv[1:])
    token = TOKEN
    if "--token" in argv:
        index = argv.index("--token")
        token = argv[index + 1]
        del argv[index:index + 2]
    mode = argv[0] if argv else "read"
    try:
        if mode == "read":
            result = pkg.read(symbol.ReadRequest(
                token=token, library=argv[1], cell=argv[2],
                view=argv[3] if len(argv) > 3 else "symbol",
            ))
        elif mode == "check":
            result = pkg.check_and_save(symbol.CheckSaveRequest(
                token=token, library=argv[1], cell=argv[2],
                view=argv[3] if len(argv) > 3 else "symbol",
            ))
        elif mode == "generate":
            result = pkg.generate(symbol.GenerateRequest(
                token=token, library=argv[1], cell=argv[2],
                schematic_view=argv[3] if len(argv) > 3 else "schematic",
                symbol_view=argv[4] if len(argv) > 4 else "symbol",
                overwrite=(len(argv) > 5 and argv[5] == "overwrite"),
            ))
        else:
            raise SystemExit(f"unknown mode: {mode}")
        print(json.dumps(result.__dict__, ensure_ascii=False, indent=2, default=str))
        return 0 if result.ok else 1
    finally:
        middle.close()


if __name__ == "__main__":
    raise SystemExit(main())
