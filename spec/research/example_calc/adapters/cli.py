# -*- coding: utf-8 -*-
"""CLI 薄壳 — 从 registry 自动生成子命令。

投影规则:
    参数来源  -> argv(a、b 作为位置参数)
    schema    -> argparse 子命令(名称/帮助来自 registry 的 name/description)
    输出      -> 人类可读文本走 stdout,错误走 stderr + exit code 1
    生命周期  -> 每次调用一个短命进程(registry 构建成本为零)

用法:
    python -m example_calc.adapters.cli add 1 2
    python -m example_calc.adapters.cli div 5 0
"""
from __future__ import annotations

import argparse
import sys

from .. import core
from ..registry import TOOLS


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="calc",
        description="算术计算器 — CLI 界面(与 MCP/harness 共享同一 registry)",
    )
    sub = ap.add_subparsers(dest="op", required=True, metavar="OPERATION")
    for name, tool in TOOLS.items():
        p = sub.add_parser(name, help=tool["description"])
        p.add_argument("a", type=float, help="第一个操作数")
        p.add_argument("b", type=float, help="第二个操作数")

    args = ap.parse_args(argv)
    tool = TOOLS[args.op]
    try:
        result = tool["handler"](args.a, args.b)
    except core.CalcError as exc:
        print(f"error: {exc}", file=sys.stderr)  # 错误语义:stderr + 非零退出码
        return 1
    # 呈现是适配器的事:CLI 选择人类可读文本
    print(f"{result.a} {result.operation} {result.b} = {result.result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
