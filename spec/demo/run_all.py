# -*- coding: utf-8 -*-
"""从命令行依次运行当前 demo：完整业务 + CDS.log 增量。"""
from __future__ import annotations

try:
    from .full_demo import run_demo as run_full
    from .cdslog_demo import run_demo as run_cdslog
except ImportError:  # 允许直接执行 python spec/demo/run_all.py
    from full_demo import run_demo as run_full
    from cdslog_demo import run_demo as run_cdslog


def main() -> None:
    print("=== full business demo (register + token route + parallel) ===")
    run_full()
    print("=== CDS.log increment ===")
    run_cdslog()


if __name__ == "__main__":
    main()
