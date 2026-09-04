# -*- coding: utf-8 -*-
"""Harness 绑定 — 把 registry 投影成 OpenAI function calling 格式。

投影规则:
    schema    -> function.parameters(JSON Schema 原样)
    参数来源  -> tool_call["function"]["arguments"] 是 JSON 字符串,需 json.loads
    输出      -> 序列化为字符串回给模型(模型只能看到文本)
    错误      -> 错误文本返回给模型,让模型自行处理或重试

真实集成只需两处调用点:
    1. 请求前:tools=to_openai_tools()
    2. 收到 tool_call 后:execute_tool_call(tool_call) 的结果作为
       role="tool" 消息追加,再发起下一次请求。
"""
from __future__ import annotations

import json

from .. import core
from ..registry import TOOLS


def to_openai_tools() -> list[dict]:
    """registry -> OpenAI chat.completions 的 tools 数组。"""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": t["description"],
                "parameters": t["inputSchema"],
            },
        }
        for name, t in TOOLS.items()
    ]


def execute_tool_call(tool_call: dict) -> str:
    """执行模型返回的 tool_call,结果序列化为字符串(role="tool" 消息体)。"""
    fn = tool_call["function"]
    name = fn["name"]
    arguments = json.loads(fn.get("arguments") or "{}")
    tool = TOOLS[name]
    try:
        result = tool["handler"](arguments["a"], arguments["b"])
    except core.CalcError as exc:
        return f"error: {exc}"
    return json.dumps(result.to_dict(), ensure_ascii=False)


# ---- 与 OpenAI SDK 的真实集成片段(需安装 openai 并配置 API key) ----
def run_with_openai_sdk(api_key: str, base_url: str | None = None):
    """演示完整的 tool-call 循环;无 key 时不执行,仅作参考。"""
    from openai import OpenAI  # 延迟导入,演示脚本不依赖它

    client = OpenAI(api_key=api_key, base_url=base_url)
    messages = [{"role": "user", "content": "帮我算 3.5 + 4.5"}]
    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        tools=to_openai_tools(),
    )
    msg = resp.choices[0].message
    messages.append(msg)
    for tc in msg.tool_calls:
        result_text = execute_tool_call(tc.model_dump())
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": result_text,
        })
    final = client.chat.completions.create(model="gpt-4.1-mini", messages=messages)
    return final.choices[0].message.content


def demo() -> None:
    """无 API key 的离线演示:打印工具定义 + 执行一个伪造的 tool_call。"""
    print("== 工具定义(与 MCP tools/list 同源)==")
    print(json.dumps(to_openai_tools(), ensure_ascii=False, indent=2))
    fake_call = {
        "function": {"name": "add", "arguments": '{"a": 1, "b": 2}'},
    }
    print("\n== 执行伪造 tool_call ==")
    print("tool result:", execute_tool_call(fake_call))


if __name__ == "__main__":
    demo()
