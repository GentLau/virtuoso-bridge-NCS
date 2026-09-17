"""``basic`` business package: one operation per middle-layer interface.

六个业务操作就是中层六个方法的直通（Skill / 命令 / 文件上传 / 文件下载 /
GUI 命令 / Spectre 命令），不做任何编排、不做领域校验：参数结构校验由 Request
完成，运行结果原样放进 Result 的步骤痕迹里，让调用方拿到与中层一致的信息。

按 spec 上层 §2/§4 实现：包只接受一个 ``Middle``，方法同步无状态，
token 每次调用原样透传。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pyapi.models import Middle

#: spec 上层 §4.2：包级自描述（操作名, 方法名, Request, Result）
OPERATION_NAMES = (
    "basic.skill.execute",
    "basic.command.run",
    "basic.file.upload",
    "basic.file.download",
    "basic.gui.run",
    "basic.spectre.run",
)


@dataclass
class Result:
    """Uniform result for the six passthrough operations."""

    ok: bool
    steps: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    result: Any = None


@dataclass(frozen=True)
class SkillRequest:
    token: str
    skill_code: str
    timeout: float | None = None


@dataclass(frozen=True)
class CommandRequest:
    token: str
    cmd: str
    timeout: int | None = None
    parallel: bool = False


@dataclass(frozen=True)
class UploadRequest:
    token: str
    local_path: str
    remote_path: str
    timeout: int | None = None
    recursive: bool = False


@dataclass(frozen=True)
class DownloadRequest:
    token: str
    remote_path: str
    local_path: str
    timeout: int | None = None
    recursive: bool = False


@dataclass(frozen=True)
class GuiRequest:
    token: str
    cmd: str
    timeout: int | None = None


@dataclass(frozen=True)
class SpectreRequest:
    token: str
    cmd: str
    timeout: int | None = None


def _require_token(token: Any) -> str:
    if not isinstance(token, str) or not token:
        raise ValueError("token must be a non-empty string")
    return token


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_timeout(timeout: Any) -> None:
    if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0):
        raise ValueError("timeout must be a positive number or None")


class Package:
    """Direct passthrough of the six middle interfaces (no orchestration)."""

    def __init__(self, middle: Middle) -> None:
        self.middle = middle

    # -- one method per middle interface ---------------------------------------
    def execute_skill(self, request: SkillRequest) -> Result:
        token = _require_token(request.token)
        _require_text(request.skill_code, "skill_code")
        _require_timeout(request.timeout)
        skill = self.middle.execute_skill(
            request.skill_code, timeout=request.timeout, token=token
        )
        return Result(
            ok=bool(skill.ok),
            steps=[{"name": "skill", "ok": bool(skill.ok), "detail": skill}],
            error="; ".join(skill.errors) or None,
            result=skill,
        )

    def run_command(self, request: CommandRequest) -> Result:
        token = _require_token(request.token)
        _require_text(request.cmd, "cmd")
        _require_timeout(request.timeout)
        command = self.middle.run_command(
            request.cmd, timeout=request.timeout, token=token,
            parallel=bool(request.parallel),
        )
        return Result(
            ok=command.returncode == 0,
            steps=[{"name": "command", "ok": command.returncode == 0,
                    "detail": command}],
            error=command.stderr or None,
            result=command,
        )

    def upload_file(self, request: UploadRequest) -> Result:
        token = _require_token(request.token)
        _require_text(request.local_path, "local_path")
        _require_text(request.remote_path, "remote_path")
        _require_timeout(request.timeout)
        upload = self.middle.upload_file(
            Path(request.local_path), request.remote_path,
            timeout=request.timeout, token=token, recursive=bool(request.recursive),
        )
        return Result(
            ok=upload.returncode == 0,
            steps=[{"name": "upload", "ok": upload.returncode == 0, "detail": upload}],
            error=upload.stderr or None,
            result=upload,
        )

    def download_file(self, request: DownloadRequest) -> Result:
        token = _require_token(request.token)
        _require_text(request.remote_path, "remote_path")
        _require_text(request.local_path, "local_path")
        _require_timeout(request.timeout)
        download = self.middle.download_file(
            request.remote_path, Path(request.local_path),
            timeout=request.timeout, token=token, recursive=bool(request.recursive),
        )
        return Result(
            ok=download.returncode == 0,
            steps=[{"name": "download", "ok": download.returncode == 0,
                    "detail": download}],
            error=download.stderr or None,
            result=download,
        )

    def run_gui_command(self, request: GuiRequest) -> Result:
        token = _require_token(request.token)
        _require_text(request.cmd, "cmd")
        _require_timeout(request.timeout)
        gui = self.middle.run_gui_command(request.cmd, timeout=request.timeout, token=token)
        return Result(
            ok=gui.returncode == 0,
            steps=[{"name": "gui", "ok": gui.returncode == 0, "detail": gui}],
            error=gui.stderr or None,
            result=gui,
        )

    def run_spectre_command(self, request: SpectreRequest) -> Result:
        token = _require_token(request.token)
        _require_text(request.cmd, "cmd")
        _require_timeout(request.timeout)
        spectre = self.middle.run_spectre_command(
            request.cmd, timeout=request.timeout, token=token
        )
        return Result(
            ok=spectre.returncode == 0,
            steps=[{"name": "spectre", "ok": spectre.returncode == 0,
                    "detail": spectre}],
            error=spectre.stderr or None,
            result=spectre,
        )


#: 操作名 -> (方法名, Request 模型)
OPERATIONS = (
    ("basic.skill.execute", "execute_skill", SkillRequest, Result),
    ("basic.command.run", "run_command", CommandRequest, Result),
    ("basic.file.upload", "upload_file", UploadRequest, Result),
    ("basic.file.download", "download_file", DownloadRequest, Result),
    ("basic.gui.run", "run_gui_command", GuiRequest, Result),
    ("basic.spectre.run", "run_spectre_command", SpectreRequest, Result),
)

__all__ = [
    "escape_skill_string",
    "is_single_complete_skill_list",
    "parse_sexpr",
    "parse_skill_str_list",
    "q",
    "scan_top_groups",
    "tokenize_top_level",
    "CommandRequest",
    "DownloadRequest",
    "GuiRequest",
    "OPERATIONS",
    "OPERATION_NAMES",
    "Package",
    "Result",
    "SkillRequest",
    "SpectreRequest",
    "UploadRequest",
]


# ---- SKILL text utilities shared by business packages ------------------------

def escape_skill_string(value: str) -> str:
    """Escape a Python string for use inside a SKILL string literal."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def q(value: str) -> str:
    """Return a quoted, escaped SKILL string literal for ``value``."""
    return f'"{escape_skill_string(value)}"'


def tokenize_top_level(body: str, *, include_groups: bool = True,
                       include_strings: bool = False,
                       include_atoms: bool = False,
                       max_tokens: int | None = None) -> list[str]:
    """Split SKILL text into top-level tokens, respecting strings/parens."""
    tokens: list[str] = []
    i, n = 0, len(body)
    while i < n and (max_tokens is None or len(tokens) < max_tokens):
        ch = body[i]
        if ch.isspace():
            i += 1
            continue
        if ch == '"':
            j = _scan_string(body, i)
            if include_strings:
                tokens.append(body[i:j])
            i = j
            continue
        if ch == "(":
            j = _scan_group(body, i)
            if include_groups:
                tokens.append(body[i:j])
            i = j
            continue
        j = i
        while j < n and not body[j].isspace() and body[j] not in "()":
            j += 1
        if include_atoms:
            tokens.append(body[i:j])
        i = j
    return tokens


def scan_top_groups(body: str) -> list[str]:
    """Return top-level parenthesized groups in ``body``."""
    return tokenize_top_level(body, include_groups=True,
                              include_strings=False, include_atoms=False)


def parse_sexpr(tok: str):
    """Parse one SKILL atom/list into Python values.

    Strings are unescaped; ``nil`` -> ``None``; ``t`` -> ``True``; lists parse
    recursively; other atoms stay strings.
    """
    tok = (tok or "").strip()
    if not tok:
        return None
    if tok == "nil":
        return None
    if tok == "t":
        return True
    if tok.startswith('"') and tok.endswith('"') and len(tok) >= 2:
        return _unescape_skill_string(tok[1:-1])
    if tok.startswith("(") and tok.endswith(")"):
        return [parse_sexpr(item) for item in tokenize_top_level(
            tok[1:-1], include_groups=True, include_strings=True,
            include_atoms=True)]
    return tok


def parse_skill_str_list(raw: str) -> list[str]:
    """Parse SKILL **string** values from a list or bare top-level strings.

    只有真正的字符串字面量会被返回；符号/数字原子（如 ``(1 2 3)``）返回空列表，
    嵌套列表会被展平。
    """
    text = (raw or "").strip()
    if not text or text == "nil":
        return []
    values: list[str] = []
    for token in tokenize_top_level(text, include_groups=True,
                                    include_strings=True, include_atoms=True):
        token = token.strip()
        if len(token) >= 2 and token.startswith('"') and token.endswith('"'):
            values.append(_unescape_skill_string(token[1:-1]))
        elif token.startswith("(") and token.endswith(")"):
            inner = token[1:-1].strip()
            if inner:
                values.extend(parse_skill_str_list(inner))
    return values


def is_single_complete_skill_list(raw: str) -> bool:
    """True when ``raw`` is exactly one balanced top-level SKILL list."""
    text = (raw or "").strip()
    if not text.startswith("("):
        return False
    depth = 0
    in_string = False
    escaped = False
    for index, character in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth < 0 or (depth == 0 and index != len(text) - 1):
                return False
    return depth == 0 and not in_string


def _scan_string(text: str, start: int) -> int:
    i = start + 1
    while i < len(text):
        if text[i] == '"' and not _is_escaped(text, i):
            return i + 1
        i += 1
    return len(text)


def _scan_group(text: str, start: int) -> int:
    depth = 1
    i = start + 1
    in_str = False
    while i < len(text) and depth:
        ch = text[i]
        if in_str:
            if ch == '"' and not _is_escaped(text, i):
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        i += 1
    return i


def _is_escaped(text: str, index: int) -> bool:
    slash_count = 0
    i = index - 1
    while i >= 0 and text[i] == "\\":
        slash_count += 1
        i -= 1
    return slash_count % 2 == 1


def _unescape_skill_string(value: str) -> str:
    chars: list[str] = []
    i = 0
    escapes = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            chars.append(escapes.get(value[i + 1], "\\" + value[i + 1]))
            i += 2
            continue
        chars.append(ch)
        i += 1
    return "".join(chars)


def _collect_strings(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for entry in value for item in _collect_strings(entry)]
    return []
