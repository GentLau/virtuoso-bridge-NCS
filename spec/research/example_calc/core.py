# -*- coding: utf-8 -*-
"""核心业务逻辑 — 纯函数,零 I/O。

纪律:
    - 不读 argv/stdin,不 print,不起子进程;
    - 输入参数 -> 结构化结果(CalcResult);
    - 业务失败抛类型化异常(CalcError),"怎么呈现"是适配器的事。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


class CalcError(Exception):
    """类型化业务异常。三种适配器各自翻译:
    CLI      -> stderr 文本 + exit code 1
    MCP      -> content + isError=true
    Harness  -> 错误文本字符串回给模型
    """


@dataclass
class CalcResult:
    """一次运算的结构化结果,三种界面共用。"""

    operation: str
    a: float
    b: float
    result: float

    def to_dict(self) -> dict:
        return {
            "operation": self.operation,
            "a": self.a,
            "b": self.b,
            "result": self.result,
        }


def add(a: float, b: float) -> CalcResult:
    return CalcResult("add", a, b, a + b)


def sub(a: float, b: float) -> CalcResult:
    return CalcResult("sub", a, b, a - b)


def mul(a: float, b: float) -> CalcResult:
    return CalcResult("mul", a, b, a * b)


def div(a: float, b: float) -> CalcResult:
    if b == 0:
        raise CalcError("division by zero")
    return CalcResult("div", a, b, a / b)


# 操作名 -> 处理器。registry 从这里取 handler。
OPERATIONS: dict[str, Callable[[float, float], CalcResult]] = {
    "add": add,
    "sub": sub,
    "mul": mul,
    "div": div,
}
