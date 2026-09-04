# -*- coding: utf-8 -*-
"""MCP 薄壳 — stdio JSON-RPC,自包含最小实现(仅演示协议骨架)。

★ stdout 纪律:stdout 是协议通道,只允许出现 JSON-RPC 帧;
  任何日志都必须走 stderr。

生产环境强烈建议改用官方 ``mcp`` Python SDK(维护握手、版本协商、
错误码等协议细节),本文件只为展示"registry 如何投影到 MCP"。

用法(手动测试,三条消息依次走一个会话):
    python -m example_calc.adapters.mcp < 手写 JSON 帧
"""
from __future__ import annotations

import json
import sys

from .. import core
from ..registry import TOOLS

SERVER_NAME = "calc-mcp"
SERVER_VERSION = "0.1.0"


def _reply(req: dict, result: dict) -> None:
    frame = {"jsonrpc": "2.0", "id": req.get("id"), "result": result}
    sys.stdout.write(json.dumps(frame, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _reply_error(req: dict, code: int, message: str) -> None:
    frame = {"jsonrpc": "2.0", "id": req.get("id"),
             "error": {"code": code, "message": message}}
    sys.stdout.write(json.dumps(frame, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle_initialize(req: dict) -> None:
    _reply(req, {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {}},
        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
    })


def handle_tools_list(req: dict) -> None:
    # registry -> MCP 工具清单(inputSchema 原样投影)
    tools = [
        {"name": name, "description": t["description"],
         "inputSchema": t["inputSchema"]}
        for name, t in TOOLS.items()
    ]
    _reply(req, {"tools": tools})


def handle_tools_call(req: dict) -> None:
    name = req.get("params", {}).get("name")
    arguments = req.get("params", {}).get("arguments") or {}
    tool = TOOLS.get(name)
    if tool is None:
        _reply_error(req, -32602, f"unknown tool: {name}")
        return
    try:
        result = tool["handler"](arguments["a"], arguments["b"])
    except core.CalcError as exc:
        # 错误语义:isError=true,而不是让进程崩溃
        _reply(req, {
            "content": [{"type": "text", "text": f"error: {exc}"}],
            "isError": True,
        })
        return
    _reply(req, {
        "content": [{
            "type": "text",
            "text": f"{result.a} {result.operation} {result.b} = {result.result}",
        }],
        "isError": False,
    })


def serve() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            _reply_error({}, -32700, "parse error")
            continue
        method = req.get("method")
        if method == "initialize":
            handle_initialize(req)
        elif method == "notifications/initialized":
            pass  # 通知,不应答
        elif method == "tools/list":
            handle_tools_list(req)
        elif method == "tools/call":
            handle_tools_call(req)
        else:
            _reply_error(req, -32601, f"method not found: {method}")


def main() -> None:
    # 注意:日志走 stderr,绝不污染 stdout 协议通道
    print(f"[{SERVER_NAME}] stdio ready (logs on stderr)", file=sys.stderr)
    serve()


if __name__ == "__main__":
    main()
