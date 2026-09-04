# -*- coding: utf-8 -*-
"""工具注册表 — 三种界面的唯一事实源(★ 本架构的核心)。

每个工具 = {name, description, inputSchema(JSON Schema), handler(指向 core)}。
三种适配器都从这里投影,绝不各自手写定义:
    CLI     -> 遍历 TOOLS 生成 argparse 子命令
    MCP     -> tools/list 输出 inputSchema;tools/call 调 handler
    Harness -> 转成 OpenAI function calling 的 function.parameters
"""
from __future__ import annotations

from typing import Any

from . import core

# 四个算术操作的参数形状完全相同:{a: number, b: number}。
# 生产中 schema 可以由 pydantic 模型自动生成,这里手写只为最小示例直白。
_BINARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "a": {"type": "number", "description": "第一个操作数"},
        "b": {"type": "number", "description": "第二个操作数"},
    },
    "required": ["a", "b"],
}

_DESCRIPTIONS = {
    "add": "两数相加 (a + b)",
    "sub": "两数相减 (a - b)",
    "mul": "两数相乘 (a * b)",
    "div": "两数相除 (a / b),除数为 0 时报错",
}


def _build_registry() -> dict[str, dict[str, Any]]:
    tools: dict[str, dict[str, Any]] = {}
    for name, handler in core.OPERATIONS.items():
        tools[name] = {
            "name": name,
            "description": _DESCRIPTIONS[name],
            "inputSchema": _BINARY_SCHEMA,
            "handler": handler,
        }
    return tools


TOOLS = _build_registry()
