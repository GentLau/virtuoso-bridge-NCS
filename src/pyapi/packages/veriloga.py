"""``veriloga`` business package: Verilog-A text-view authoring.

Spec: ``spec/design-concepts/上层/11-veriloga.md`` (Draft v1).

Verilog-A code lives in a *text view* (``text.veriloga``, file ``veriloga.va``),
not an OA database view, so the package reads/writes files and performs the
GUI "Check and Save" equivalent headlessly:
``VerAParseModule`` (check) + ``ahdlUpdateViewInfo`` (persist CDF / netlist.oa).
"""
from __future__ import annotations

import hashlib
import posixpath
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common.paths import artifact_dir
from pyapi.models import Middle, VirtuosoResult
from pyapi.packages import basic


VIEW_TYPE = "text.veriloga"
MAIN_FILE = "veriloga.va"
MASTER_TAG = "-- Master.tag File, Rev:1.0\n"
_AHDL_CONTEXT = "ahdlSck.cxt"


@dataclass
class Result:
    ok: bool
    steps: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    value: Any = None


@dataclass(frozen=True)
class ReadRequest:
    token: str
    library: str | None = None
    cell: str | None = None
    view: str = "veriloga"
    view_type: str = VIEW_TYPE
    file_path: str | None = None
    file_is_local: bool = True
    focus: list[str] | None = None
    timeout: int | None = None


@dataclass(frozen=True)
class WriteRequest:
    token: str
    library: str
    cell: str
    commands: list[dict[str, Any]]
    view: str = "veriloga"
    view_type: str = VIEW_TYPE
    timeout: int | None = None


@dataclass(frozen=True)
class CheckSaveRequest:
    token: str
    library: str
    cell: str
    view: str = "veriloga"
    view_type: str = VIEW_TYPE
    timeout: int | None = None


def _step(name: str, ok: bool, detail: Any) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail}


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_timeout(value: Any) -> None:
    if value is not None and (not isinstance(value, (int, float)) or value <= 0):
        raise ValueError("timeout must be a positive number or None")


def _require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _safe_name(value: str, fallback: str = "cell") -> str:
    cleaned = "".join(
        character if character.isalnum() or character in "_.-" else "_"
        for character in (value or "")
    ).strip("_")
    return cleaned or fallback


def _parse_pin_list(raw: str) -> list[dict[str, str]]:
    """Parse the DPL returned by ``ahdlToPinList`` / ``VerAParseModule``."""
    parsed = basic.parse_sexpr(raw.strip())
    pins: list[dict[str, str]] = []
    if not isinstance(parsed, list):
        return pins
    ports = None
    for index, item in enumerate(parsed):
        if item == "ports" and index + 1 < len(parsed):
            ports = parsed[index + 1]
            break
    if isinstance(ports, list):
        for entry in ports:
            if not isinstance(entry, list):
                continue
            record = _dpl_pairs(entry, ("name", "direction", "width"))
            name = record.get("name", "")
            if name:
                pins.append({
                    "name": name,
                    "direction": record.get("direction", "inputOutput"),
                    "width": record.get("width", "1"),
                })
    return pins


class Package:
    def __init__(self, middle: Middle) -> None:
        self.middle = middle

    def _skill(self, expr: str, token: str, timeout: int | float | None = None) -> VirtuosoResult:
        return self.middle.execute_skill(expr, timeout=timeout, token=token)

    def _q(self, expr: str, token: str, timeout: int | float | None = None) -> str:
        result = self._skill(expr, token, timeout)
        if not result.ok:
            raise RuntimeError("; ".join(result.errors) or "SKILL execution failed")
        return result.output or ""

    def _cache_dir(self) -> Path:
        path = artifact_dir() / "veriloga"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _view_dir(self, request: Any) -> str:
        raw = self._q(
            f"let((lib) lib = ddGetObj({basic.q(request.library)}) "
            'unless(lib error("library not found")) ddGetObjReadPath(lib))',
            request.token,
            request.timeout,
        )
        root = raw.strip().strip('"')
        if not root or root == "nil":
            raise RuntimeError(f"library {request.library!r} read path unavailable")
        return f"{root.rstrip('/')}/{_safe_name(request.cell)}/{_safe_name(request.view, request.view)}"

    def _remote_file(self, view_dir: str) -> str:
        return posixpath.join(view_dir, MAIN_FILE)

    def _read_remote(self, remote: str, request: Any) -> str:
        local = self._cache_dir() / Path(remote).name
        result = self.middle.download_file(remote, local, timeout=request.timeout, token=request.token)
        if result.returncode != 0:
            raise RuntimeError(result.stderr or f"download failed: {remote}")
        return local.read_text(encoding="utf-8", errors="replace")

    def _write_remote(self, remote: str, content: str, request: Any) -> None:
        local = self._cache_dir() / Path(remote).name
        local.write_text(content, encoding="utf-8", newline="\n")
        result = self.middle.upload_file(local, remote, timeout=request.timeout, token=request.token)
        if result.returncode != 0:
            raise RuntimeError(result.stderr or f"upload failed: {remote}")

    def _check_lock(self, view_dir: str, request: Any) -> None:
        result = self.middle.run_command(
            f"if ls -A {shlex.quote(view_dir)}/*.cdslck >/dev/null 2>&1; then echo LOCK; else echo OK; fi",
            timeout=60, token=request.token,
        )
        if result.returncode != 0 or (result.stdout or "").strip() == "LOCK":
            raise RuntimeError("view is locked by an open editor; close the Verilog-A editor first")

    def _ensure_context(self, request: Any) -> None:
        probe = self._q("if(getd('VerAParseModule) t nil)", request.token, request.timeout)
        if basic.parse_sexpr(probe.strip()) is True:
            return
        loaded = self._q(
            'let((vbPath) vbPath = strcat(car(getInstallPath()) '
            f'"/etc/context/64bit/{_AHDL_CONTEXT}") '
            "loadContext(vbPath))",
            request.token,
            request.timeout,
        )
        probe = self._q("if(getd('VerAParseModule) t nil)", request.token, request.timeout)
        if basic.parse_sexpr(probe.strip()) is not True:
            raise RuntimeError(
                f"could not load AHDL context (loadContext -> {loaded.strip()!r})"
            )

    # -- read -------------------------------------------------------------------

    def read(self, request: ReadRequest) -> Result:
        _require_text(request.token, "token")
        _require_timeout(request.timeout)
        cell_target = request.library and request.cell
        file_target = bool(request.file_path)
        if cell_target == file_target:
            raise ValueError("provide either library+cell or file_path, not both/none")
        valid_focus = {"source", "ports", "views", "diagnostics"}
        if request.focus is not None:
            if not isinstance(request.focus, list) or not request.focus:
                raise ValueError("focus must be a non-empty list")
            unknown = set(request.focus) - valid_focus
            if unknown:
                raise ValueError(f"unknown focus values: {sorted(unknown)}")
        steps: list[dict[str, Any]] = []
        try:
            if file_target:
                path = Path(request.file_path)
                if request.file_is_local:
                    if not path.is_file():
                        raise RuntimeError(f"file not found: {path}")
                    text = path.read_text(encoding="utf-8", errors="replace")
                else:
                    text = self._read_remote(str(path), request)
                source_path = str(path)
                ports: list[dict[str, str]] = []
                views: list[dict[str, Any]] = []
            else:
                view_dir = self._view_dir(request)
                remote = self._remote_file(view_dir)
                text = self._read_remote(remote, request)
                source_path = remote
                ports = self._read_ports(request)
                views = self._read_views(request)
            diagnostics = self._read_diagnostics(request) if cell_target else {}
            value: dict[str, Any] = {}
            focus = set(request.focus) if request.focus else valid_focus
            if "source" in focus:
                value["source"] = {
                    "text": text,
                    "path": source_path,
                    "size": len(text.encode("utf-8")),
                    "lines": text.count("\n") + (1 if text and not text.endswith("\n") else 0),
                    "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                }
            if "ports" in focus:
                value["ports"] = ports
            if "views" in focus:
                value["views"] = views
            if "diagnostics" in focus:
                value["diagnostics"] = diagnostics
            return Result(True, steps, None, value)
        except Exception as exc:  # noqa: BLE001
            return Result(False, steps, f"{type(exc).__name__}: {exc}")

    def _read_ports(self, request: Any) -> list[dict[str, str]]:
        probe = self._q("if(getd('ahdlToPinList) t nil)", request.token, request.timeout)
        if basic.parse_sexpr(probe.strip()) is not True:
            return [{"unsupported": "AHDL context is not loaded"}]
        raw = self._q(
            f"ahdlToPinList({basic.q(request.library)} {basic.q(request.cell)} "
            f"{basic.q(request.view)})",
            request.token,
            request.timeout,
        )
        return _parse_pin_list(raw)

    def _read_views(self, request: Any) -> list[dict[str, Any]]:
        raw = self._q(
            "let((cell views out) "
            f"cell = ddGetObj({basic.q(request.library)} {basic.q(request.cell)}) "
            "unless(cell error(\"cell not found\")) "
            "views = cell~>views "
            "out = mapcar(lambda((view) "
            "  mapcar(lambda((file) list(view~>name "
            "    ddMapGetFileViewType(file) ddMapGetFileDataType(file) file~>name)) "
            "    ddGetObjFiles(view))) views) "
            "sprintf(nil \"%L\" out))",
            request.token,
            request.timeout,
        )
        parsed = basic.parse_sexpr(raw.strip())
        result: list[dict[str, Any]] = []
        if not isinstance(parsed, list):
            return result
        for view_entry in parsed:
            if not isinstance(view_entry, list):
                continue
            for file_entry in view_entry:
                if isinstance(file_entry, list) and len(file_entry) >= 3:
                    result.append({
                        "view": str(file_entry[0]),
                        "view_type": None if file_entry[1] is None else str(file_entry[1]),
                        "data_type": None if file_entry[2] is None else str(file_entry[2]),
                        "file": None if file_entry[3] is None else str(file_entry[3]),
                    })
        return result

    def _read_diagnostics(self, request: Any) -> dict[str, Any]:
        path = self._err_path(request)
        try:
            text = self._read_remote(path, request)
        except Exception:  # noqa: BLE001 - absent log is not a failure
            return {"log_path": path, "status": "none", "error_count": 0, "errors": []}
        errors = [
            line.strip() for line in text.splitlines()
            if "VACOMP-" in line or "Error" in line
        ]
        return {
            "log_path": path,
            "status": "failed" if errors else "ok",
            "error_count": len(errors),
            "errors": errors[:20],
        }

    def _err_path(self, request: Any) -> str:
        root = self._role_root(request.token)
        return posixpath.join(
            root, "veriloga_err",
            f"{_safe_name(request.library)}__{_safe_name(request.cell)}.log",
        )

    def _role_root(self, token: str) -> str:
        facts = self.middle.query(token=token)
        if facts.status.value != "success":
            raise RuntimeError("; ".join(facts.errors) or "query failed")
        entry = facts.roles.get("daemon")
        if entry is None or not entry.root:
            raise RuntimeError("daemon role root is not available")
        return entry.root.rstrip("/")

    # -- write ------------------------------------------------------------------

    def write(self, request: WriteRequest) -> Result:
        _require_text(request.token, "token")
        _require_text(request.library, "library")
        _require_text(request.cell, "cell")
        _require_text(request.view, "view")
        _require_text(request.view_type, "view_type")
        _require_timeout(request.timeout)
        if not isinstance(request.commands, list) or not request.commands:
            raise ValueError("commands must be a non-empty list")
        steps: list[dict[str, Any]] = []
        planned: list[tuple[int, dict[str, Any]]] = []
        for index, command in enumerate(request.commands):
            if not isinstance(command, dict) or command.get("op") not in (
                "set_source", "patch_source", "ensure_view", "delete_view",
            ):
                return Result(False, steps, f"command {index} must have a valid op")
            planned.append((index, command))
        try:
            view_dir = self._view_dir(request)
            self._check_lock(view_dir, request)
            remote = self._remote_file(view_dir)
            applied = 0
            for _index, command in planned:
                name = command["op"]
                try:
                    if name == "ensure_view":
                        self._ensure_view(view_dir, request)
                    elif name == "delete_view":
                        self._delete_view(request)
                    elif name == "set_source":
                        self._set_source(remote, command, request)
                    else:
                        self._patch_source(remote, command, request)
                except Exception as exc:  # noqa: BLE001
                    steps.append(_step(name, False, f"{type(exc).__name__}: {exc}"))
                    return Result(
                        False, steps,
                        f"{name} failed: {exc} (commands applied: {applied}/{len(planned)})",
                    )
                steps.append(_step(name, True, "ok"))
                applied += 1
            refresh = self._skill("ddUpdateLibList()", request.token, request.timeout)
            steps.append(_step("ddUpdateLibList", refresh.ok, refresh))
            return Result(True, steps, None, {"applied": applied})
        except Exception as exc:  # noqa: BLE001
            return Result(False, steps, f"{type(exc).__name__}: {exc}")

    def _ensure_view(self, view_dir: str, request: Any) -> None:
        template = (
            f"// VerilogA for {request.library}, {request.cell}, {request.view}\n"
            "\n"
            "`include \"constants.vams\"\n"
            "`include \"disciplines.vams\"\n"
            "\n"
            f"module {_safe_name(request.cell)};\n"
            "\n"
            "\n"
            "endmodule\n"
        )
        self.middle.run_command(
            f"mkdir -p {shlex.quote(view_dir)}", timeout=60, token=request.token,
        )
        self._write_remote(posixpath.join(view_dir, "master.tag"),
                           MASTER_TAG + MAIN_FILE + "\n", request)
        self._write_remote(posixpath.join(view_dir, MAIN_FILE), template, request)

    def _delete_view(self, request: Any) -> None:
        raw = self._q(
            f"let((view) view = ddGetObj({basic.q(request.library)} "
            f"{basic.q(request.cell)} {basic.q(request.view)}) "
            'unless(view error("view not found")) ddDeleteObj(view))',
            request.token,
            request.timeout,
        )
        if basic.parse_sexpr(raw.strip()) is not True:
            raise RuntimeError(f"ddDeleteObj returned: {raw.strip()!r}")

    def _set_source(self, remote: str, command: dict[str, Any], request: Any) -> None:
        text = command.get("text")
        if not isinstance(text, str):
            raise ValueError("command.text must be a string")
        expected = command.get("expected_sha256")
        if expected:
            try:
                current = self._read_remote(remote, request)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"expected_sha256 given but current source unavailable: {exc}") from exc
            actual = hashlib.sha256(current.encode("utf-8")).hexdigest()
            if actual != str(expected):
                raise RuntimeError(
                    f"sha256 mismatch: expected {expected}, actual {actual}"
                )
        self._write_remote(remote, text, request)

    def _patch_source(self, remote: str, command: dict[str, Any], request: Any) -> None:
        edits = command.get("edits")
        if not isinstance(edits, list) or not edits:
            raise ValueError("command.edits must be a non-empty list")
        current = self._read_remote(remote, request)
        lines = current.splitlines()
        for edit in edits:
            if not isinstance(edit, dict):
                raise ValueError("each edit must be an object")
            if "old_text" in edit and "new_text" in edit:
                old = edit["old_text"]
                if not isinstance(old, str):
                    raise ValueError("edit.old_text must be a string")
                new = edit["new_text"]
                if not isinstance(new, str):
                    raise ValueError("edit.new_text must be a string")
                count = current.count(old)
                if count == 0:
                    raise RuntimeError(f"old_text not found: {old!r}")
                if count != 1 and not command.get("all"):
                    raise RuntimeError(f"old_text matches {count} places, all=false")
                current = current.replace(old, new)
            elif {"start_line", "end_line", "new_text"} <= set(edit):
                start = int(edit["start_line"])
                end = int(edit["end_line"])
                if start < 1 or end < start or end > len(lines):
                    raise RuntimeError(
                        f"invalid line range {start}:{end} (file has {len(lines)} lines)"
                    )
                replacement = edit["new_text"]
                if not isinstance(replacement, str):
                    raise ValueError("edit.new_text must be a string")
                replacement_lines = replacement.splitlines()
                current_lines = current.splitlines()
                current_lines[start - 1:end] = replacement_lines
                current = "\n".join(current_lines) + "\n"
            else:
                raise ValueError("edit must be old_text/new_text or start_line/end_line/new_text")
        self._write_remote(remote, current, request)

    # -- check_and_save ---------------------------------------------------------

    def check_and_save(self, request: CheckSaveRequest) -> Result:
        _require_text(request.token, "token")
        _require_text(request.library, "library")
        _require_text(request.cell, "cell")
        _require_text(request.view, "view")
        _require_text(request.view_type, "view_type")
        _require_timeout(request.timeout)
        steps: list[dict[str, Any]] = []
        try:
            self._ensure_context(request)
            steps.append(_step("context", True, "AHDL context loaded"))
            view_dir = self._view_dir(request)
            va_path = self._remote_file(view_dir)
            err_path = self._err_path(request)
            self.middle.run_command(
                f"mkdir -p {shlex.quote(posixpath.dirname(err_path))}",
                timeout=60, token=request.token,
            )
            run = self._skill(
                f"VerAParseModule({basic.q(va_path)} {basic.q(request.cell)} "
                f"{basic.q(err_path)})",
                request.token,
                request.timeout,
            )
            steps.append(_step("VerAParseModule", run.ok, run))
            if not run.ok:
                return Result(False, steps, "; ".join(run.errors) or "parse failed")
            parsed = basic.parse_sexpr((run.output or "").strip())
            if not isinstance(parsed, list):
                errors = self._err_lines(err_path, request)
                steps.append(_step("parse", False, {"err_log": err_path}))
                return Result(
                    False, steps,
                    "; ".join(errors) or "Verilog-A parse failed",
                    {"errors": errors, "err_log": err_path},
                )
            # the daemon may wrap the printed DPL in one extra list
            dpl = parsed[0] if len(parsed) == 1 and isinstance(parsed[0], list) else parsed
            if not isinstance(dpl, list) or not _dpl_status(dpl):
                errors = self._err_lines(err_path, request)
                steps.append(_step("parse", False, {"err_log": err_path}))
                return Result(False, steps, "; ".join(errors) or "Verilog-A parse failed",
                              {"errors": errors, "err_log": err_path})
            ports, pin_order, params = _dpl_fields(dpl)
            refresh = self._skill(
                f"ahdlUpdateViewInfo({basic.q(request.library)} "
                f"?cell {basic.q(request.cell)} ?view {basic.q(request.view)})",
                request.token,
                request.timeout,
            )
            steps.append(_step("ahdlUpdateViewInfo", refresh.ok, refresh))
            output = (refresh.output or "").strip()
            if not refresh.ok or (
                output not in ("t", "T") and "Successfully updated" not in output
            ):
                return Result(
                    False, steps,
                    "; ".join(refresh.errors) or f"ahdlUpdateViewInfo failed: {refresh.output}",
                )
            return Result(True, steps, None, {
                "module_name": _dpl_module(dpl),
                "ports": ports,
                "pin_order": pin_order,
                "param_list": params,
                "err_log": err_path,
                "errors": [],
            })
        except Exception as exc:  # noqa: BLE001
            return Result(False, steps, f"{type(exc).__name__}: {exc}")

    def _err_lines(self, err_path: str, request: Any) -> list[str]:
        try:
            text = self._read_remote(err_path, request)
        except Exception:  # noqa: BLE001
            return ["parse failed (no err log available)"]
        return [
            line.strip() for line in text.splitlines()
            if "VACOMP-" in line or "Error" in line
        ][:20]


def _dpl_status(parsed: list) -> bool:
    try:
        return parsed[parsed.index("status") + 1] is True
    except (ValueError, IndexError):
        return False


def _dpl_module(parsed: list) -> str:
    try:
        return str(parsed[parsed.index("moduleName") + 1])
    except (ValueError, IndexError):
        return ""


def _dpl_fields(parsed: list) -> tuple[list[dict[str, str]], list[str], list[dict[str, str]]]:
    pins: list[dict[str, str]] = []
    pin_list = _dpl_value(parsed, "pinList")
    if isinstance(pin_list, list):
        for entry in pin_list:
            if not isinstance(entry, list):
                continue
            record = _dpl_pairs(entry, ("name", "direction", "width"))
            pins.append({
                "name": record.get("name", ""),
                "direction": record.get("direction", "inputOutput"),
                "width": record.get("width", "1"),
            })
    order = _dpl_value(parsed, "pinOrder")
    order_names = [str(item) for item in order] if isinstance(order, list) else []
    params: list[dict[str, str]] = []
    param_list = _dpl_value(parsed, "paramList")
    if isinstance(param_list, list):
        for entry in param_list:
            if not isinstance(entry, list):
                continue
            record = _dpl_pairs(entry, ("name", "type", "default"))
            params.append({
                "name": record.get("name", ""),
                "type": record.get("type", ""),
                "default": record.get("default", ""),
            })
    return pins, order_names, params


def _dpl_value(parsed: list, key: str):
    try:
        return parsed[parsed.index(key) + 1]
    except (ValueError, IndexError):
        return None


def _dpl_pairs(entry: list, keys: tuple[str, ...]) -> dict[str, str]:
    """Extract key/value pairs from a DPL alist with a possible nil head."""
    record: dict[str, str] = {}
    for index in range(len(entry) - 1):
        key = str(entry[index])
        if key in keys:
            record[key] = str(entry[index + 1])
    return record


#: spec 上层 §4.2: package-level self-description
OPERATIONS = (
    ("virtuoso.veriloga.read", "read", ReadRequest, Result),
    ("virtuoso.veriloga.write", "write", WriteRequest, Result),
    ("virtuoso.veriloga.check_and_save", "check_and_save", CheckSaveRequest, Result),
)

OPERATION_NAMES = tuple(operation for operation, *_ in OPERATIONS)

__all__ = [
    "CheckSaveRequest", "MAIN_FILE", "MASTER_TAG", "OPERATIONS", "OPERATION_NAMES",
    "Package", "ReadRequest", "Result", "VIEW_TYPE", "WriteRequest",
]
