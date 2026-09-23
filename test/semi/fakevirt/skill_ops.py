"""SKILL 子集求值器 —— fake Virtuoso 的 "SKILL 执行" 层。

设计约束（重要）
================
1. 只实现 `OPS` 中登记的操作，且与 README.md 的"支持的操作"表一一对应；
   未登记的一律抛 SkillError，返回与真 CIW 一致的错误文案，绝不静默给假答案。
2. 语义以真机 IC6.1.8（wsl-gent）为准。`Op.verified=False` 表示尚未在真机
   探测过，属于"暂定"状态（README 的验证状态列会如实标注）。
3. `to_lisp()` 复刻 SKILL `%L` 的格式：字符串带引号、`nil`/`t`、数字裸输出。
   这是 daemon 回传给 middle 的线上格式，必须与真机一致。
"""

from __future__ import annotations

import ast
import operator
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable


class Symbol(str):
    """SKILL 符号：``%L`` 输出裸名（与字符串的带引号输出不同）。"""


class SkillError(Exception):
    """SKILL 级错误；按真机 ``errset.errset`` 的列表结构序列化。

    真机证据（IC6.1.8，wsl-gent，2026-09-20）::

        boom()                      -> ("eval" 0 t nil ("*Error* eval: undefined function" boom))
        zzz                         -> ("eval" 0 t nil ("*Error* eval: unbound variable" zzz))
        strcat(1 2)                 -> ("strcat" 0 t nil ("*Error* strcat: argument #1 should be either a string or a symbol (type template = \"S\")" 1))
        fileLength("/tmp/no-such")  -> ("fileLength" 0 t nil ("*Error* fileLength: no such file or directory" "/tmp/no-such"))

    结构：(<context:string> 0 t nil (<message:string> <culprit>))；
    culprit 是符号时裸输出，是字符串时带引号，是数字时裸输出。
    """

    def __init__(self, message: str, *, context: str = "eval", culprit: object = None) -> None:
        super().__init__(message)
        self.message = message
        self.context = context
        self.culprit = culprit

    def payload(self) -> str:
        culprit = self.culprit
        if isinstance(culprit, Symbol):
            rendered = str(culprit)
        elif isinstance(culprit, str):
            rendered = to_lisp(culprit)
        elif culprit is None:
            rendered = "nil"
        else:
            rendered = str(culprit)
        return (
            f"({to_lisp(self.context)} 0 t nil "
            f"({to_lisp(self.message)} {rendered}))"
        )


# --------------------------------------------------------------------------
# 值格式化（%L）
# --------------------------------------------------------------------------

def to_lisp(value: Any) -> str:
    """按真机 ``sprintf(nil "%L" value)`` 的规则格式化。"""
    if value is None or value is False:
        return "nil"
    if value is True:
        return "t"
    if isinstance(value, Symbol):
        return str(value)
    if isinstance(value, str):
        body = (
            value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\t", "\\t")
        )
        return f'"{body}"'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "(" + " ".join(to_lisp(item) for item in value) + ")"
    raise SkillError(
        f"*Error* sprintf: unsupported value type - {type(value).__name__}"
    )


# --------------------------------------------------------------------------
# 求值上下文
# --------------------------------------------------------------------------

class Ctx:
    """fake CIW 的运行时状态。"""

    def __init__(
        self,
        *,
        hostname: str,
        variables: dict[str, Any],
        log_path: str,
        cwd: str = "/",
    ) -> None:
        self.hostname = hostname
        self.variables = dict(variables)
        self.log_path = log_path
        self.cwd = cwd

    def resolve_path(self, path: str) -> str:
        if not path.startswith("/"):
            return os.path.join(self.cwd, path)
        return path


# --------------------------------------------------------------------------
# 内建操作实现（每个实现都必须能对应到 README 表里的一行）
# --------------------------------------------------------------------------

def _arity(name: str, args: list, n: int) -> None:
    if len(args) != n:
        raise SkillError(f"*Error* {name}: wrong number of arguments",
                         context=name, culprit=len(args))


def _op_hi_flush(ctx: Ctx, args: list) -> bool:
    _arity("hiFlush", args, 0)
    return True  # 真机证据：hiFlush() -> t


def _op_get_host_name(ctx: Ctx, args: list) -> str:
    _arity("getHostName", args, 0)
    return ctx.hostname


def _op_strcat(ctx: Ctx, args: list) -> str:
    out: list[str] = []
    for index, item in enumerate(args, start=1):
        if isinstance(item, str):
            out.append(item)
        else:
            raise SkillError(
                f"*Error* strcat: argument #{index} should be either "
                'a string or a symbol (type template = "S")',
                context="strcat",
                culprit=item,
            )
    return "".join(out)


def _op_printf(ctx: Ctx, args: list) -> bool:
    """v0：仅支持纯文本参数（含转义后的换行）；格式指令按需再实现。

    真机证据：printf 返回 t；其输出进入 CDS.log 时带 ``\\o `` 前缀
    （如 ``printf("probe-log\\n")`` 的 log 增量为 ``\\o probe-log\\n``）。
    """
    text = ""
    for item in args:
        if isinstance(item, str):
            text += item
        else:
            raise SkillError("*Error* printf: unsupported argument type",
                             context="printf", culprit=item)
    # 二进制写：避免 Windows 文本模式把 \n 翻成 \r\n（真机只有 \n）
    with open(ctx.log_path, "ab") as fh:
        fh.write(("\\o " + text).encode("utf-8", errors="replace"))
    return True


def _op_file_length(ctx: Ctx, args: list) -> int:
    _arity("fileLength", args, 1)
    path = ctx.resolve_path(str(args[0]))
    try:
        return os.path.getsize(path)
    except OSError:
        raise SkillError("*Error* fileLength: no such file or directory",
                         context="fileLength", culprit=path) from None


def _op_hi_get_log_file_name(ctx: Ctx, args: list) -> str:
    _arity("hiGetLogFileName", args, 0)
    return ctx.log_path


def _op_list(ctx: Ctx, args: list) -> list:
    return list(args)


# --------------------------------------------------------------------------
# 操作注册表 —— README.md"支持的操作"表的代码侧真源
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Op:
    name: str
    example: str
    impl: Callable[[Ctx, list], Any]
    verified: bool = False
    note: str = ""


OPS: dict[str, Op] = {
    "hiFlush": Op("hiFlush", "hiFlush()", _op_hi_flush,
                  note="桥内部用；真机返回 nil"),
    "getHostName": Op("getHostName", "getHostName()", _op_get_host_name,
                      note="返回 CIW 主机名"),
    "strcat": Op("strcat", 'strcat("a" "b")', _op_strcat,
                 note="字符串拼接；非字符串入参按真机报错"),
    "printf": Op("printf", 'printf("hello\\n")', _op_printf,
                 note="v0 仅纯文本；写入 fake CDS.log"),
    "fileLength": Op("fileLength", 'fileLength("/tmp/x")', _op_file_length,
                     note="返回文件字节数"),
    "hiGetLogFileName": Op("hiGetLogFileName", "hiGetLogFileName()",
                           _op_hi_get_log_file_name,
                           note="返回 fake CDS.log 路径"),
    "list": Op("list", "list(1 2)", _op_list, note="返回列表"),
}


# --------------------------------------------------------------------------
# 表达式求值
# --------------------------------------------------------------------------

_FUNC_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_\[\]]*)\s*\((.*)\)$", re.S)
_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+)([eE][+-]?\d+)?$")
_SYMBOL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_\[\]]*$")
_ARITH_CHARS_RE = re.compile(r"^[0-9+\-*/(). \t\r\n]+$")


def _parse_string(tok: str) -> str:
    inner = tok[1:-1]
    out: list[str] = []
    esc = False
    for ch in inner:
        if esc:
            out.append({"n": "\n", "t": "\t", "\\": "\\", '"': '"'}.get(ch, ch))
            esc = False
        elif ch == "\\":
            esc = True
        else:
            out.append(ch)
    if esc:
        out.append("\\")
    return "".join(out)


def _split_args(src: str) -> list[str]:
    """按顶层空白切分参数，尊重字符串引号与圆括号嵌套。"""
    args: list[str] = []
    buf: list[str] = []
    depth = 0
    in_str = False
    esc = False
    for ch in src:
        if in_str:
            buf.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            buf.append(ch)
        elif ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth -= 1
            buf.append(ch)
        elif ch.isspace() and depth == 0:
            if buf:
                args.append("".join(buf))
                buf = []
        else:
            buf.append(ch)
    if depth != 0 or in_str:
        raise SkillError("*Error* eval: unbalanced expression")
    if buf:
        args.append("".join(buf))
    return args


_AST_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_AST_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval_arith_node(node: ast.AST) -> float | int:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
            and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        # 真机证据（IC6.1.8）：1/2 -> 0；-7/2 -> -3（向零截断）；1.0/2 -> 0.5
        left = _eval_arith_node(node.left)
        right = _eval_arith_node(node.right)
        if right == 0:
            raise SkillError("*Error* eval: divide by zero")
        if isinstance(left, int) and isinstance(right, int):
            quotient = abs(left) // abs(right)
            return quotient if (left >= 0) == (right >= 0) else -quotient
        return left / right
    if isinstance(node, ast.BinOp) and type(node.op) in _AST_BINOPS:
        return _AST_BINOPS[type(node.op)](
            _eval_arith_node(node.left), _eval_arith_node(node.right)
        )
    if isinstance(node, ast.UnaryOp) and type(node.op) in _AST_UNARYOPS:
        return _AST_UNARYOPS[type(node.op)](_eval_arith_node(node.operand))
    raise SkillError("*Error* eval: unsupported arithmetic expression")


def _eval_arith(src: str) -> float | int:
    # SKILL 中换行/制表符只是空白；Python 的 eval 模式不接受断行运算符，
    # 所以先折叠空白再解析（真机 <-> fake 的关键差异点之一）。
    normalized = re.sub(r"\s+", " ", src)
    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError:
        raise SkillError(f"*Error* eval: syntax error - {src}") from None
    return _eval_arith_node(tree.body)


def eval_expr(src: str, ctx: Ctx) -> Any:
    """求值一个 SKILL 表达式（v0：单表达式）。"""
    s = src.strip()
    if not s:
        raise SkillError("*Error* eval: empty expression")

    match = _FUNC_RE.match(s)
    if match:
        name, argtext = match.group(1), match.group(2)
        op = OPS.get(name)
        if op is None:
            raise SkillError("*Error* eval: undefined function",
                             context="eval", culprit=Symbol(name))
        args = [eval_expr(a, ctx) for a in _split_args(argtext)] \
            if argtext.strip() else []
        return op.impl(ctx, args)

    if _ARITH_CHARS_RE.match(s) and re.search(r"[+\-*/]", s):
        return _eval_arith(s)
    if _INT_RE.match(s):
        return int(s)
    if _FLOAT_RE.match(s):
        return float(s)
    if s == "t":
        return True
    if s.lower() == "nil":
        return None
    if s.startswith('"'):
        if not s.endswith('"') or len(s) < 2:
            raise SkillError("*Error* eval: unbalanced string literal")
        return _parse_string(s)
    if _SYMBOL_RE.match(s):
        if s in ctx.variables:
            return ctx.variables[s]
        raise SkillError("*Error* eval: unbound variable",
                         context="eval", culprit=Symbol(s))
    raise SkillError("*Error* eval: undefined function",
                     context="eval", culprit=Symbol(s))


__all__ = ["SkillError", "Ctx", "Op", "OPS", "eval_expr", "to_lisp"]
