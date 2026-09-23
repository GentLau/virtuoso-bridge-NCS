"""``maestro`` business package: ADE Assembler / Explorer orchestration.

Spec: ``spec/design-concepts/上层/6-maestro.md`` (Draft v4).  The package
owns only upper-layer orchestration: every remote action goes through the
five middle interfaces (plus the read-only ``query`` companion).

The public operations are intentionally few and session-free for callers:

* ``virtuoso.maestro.read_config``
* ``virtuoso.maestro.write``
* ``virtuoso.maestro.read_results``
* ``virtuoso.maestro.export``
* ``virtuoso.maestro.read_history``
* ``virtuoso.maestro.write_history``
* ``virtuoso.maestro.open_gui`` / ``close_gui``
* ``virtuoso.maestro.run``
* ``virtuoso.maestro.open_waveform_gui`` / ``close_waveform_gui``

``maeOpenSetup`` reuses an already-open session for the same cellview.  A
session that the package created itself is saved/closed by the package; a
session that was already open (usually the GUI session required by
``maeRunSimulation``) is left open.
"""
from __future__ import annotations

import posixpath
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common.paths import artifact_dir
from pyapi.models import Middle, VirtuosoResult
from pyapi.packages import gui as gui_pkg
from pyapi.packages.basic import parse_sexpr, q
from pyapi.packages._maestro_util import (
    decode_skill_text,
    natural_sort_histories,
    pairs_to_dict,
    parse_bool,
    parse_detail_csv,
    parse_ocn_text,
    parse_overall_yield,
    parse_skill_str_leaves,
    skill_alist,
    skill_string_list,
    skill_value,
    unquote,
)


# ---------------------------------------------------------------------------
# Requests and the uniform result
# ---------------------------------------------------------------------------

@dataclass
class Result:
    """Uniform operation result with a step trace and a payload."""

    ok: bool
    steps: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    value: Any = None


@dataclass(frozen=True)
class ReadConfigRequest:
    token: str
    library: str
    cell: str
    view: str = "maestro"
    include_parameters: bool = True
    include_raw: bool = False
    timeout: int | None = None


@dataclass(frozen=True)
class WriteRequest:
    token: str
    library: str
    cell: str
    commands: list[dict[str, Any]]
    view: str = "maestro"
    save: bool = True
    timeout: int | None = None


@dataclass(frozen=True)
class ReadResultsRequest:
    token: str
    library: str
    cell: str
    history: str | None = None
    test: str | None = None
    analysis: str | None = None
    waveform: str | None = None
    result: str | None = None
    view: str = "maestro"
    notation: str = "scientific"
    precision: int | None = None
    width: int | None = None
    output_path: str | None = None
    timeout: int | None = None


@dataclass(frozen=True)
class ExportRequest:
    token: str
    library: str
    cell: str
    kind: str
    view: str = "maestro"
    history: str | None = None
    test: str | None = None
    corner: str | None = None
    output_path: str | None = None
    window_id: int | None = None
    region: list[float] | None = None
    toplevel: bool = True
    include_results: bool = True
    timeout: int | None = None


@dataclass(frozen=True)
class ReadHistoryRequest:
    token: str
    library: str
    cell: str
    history: str | None = None
    view: str = "maestro"
    timeout: int | None = None


@dataclass(frozen=True)
class WriteHistoryRequest:
    token: str
    library: str
    cell: str
    commands: list[dict[str, Any]]
    view: str = "maestro"
    timeout: int | None = None


@dataclass(frozen=True)
class OpenGuiRequest:
    token: str
    library: str
    cell: str
    view: str = "maestro"
    history: str | None = None
    timeout: int | None = None


@dataclass(frozen=True)
class CloseGuiRequest:
    token: str
    library: str
    cell: str
    view: str = "maestro"
    timeout: int | None = None


@dataclass(frozen=True)
class RunRequest:
    token: str
    library: str
    cell: str
    view: str = "maestro"
    history: str | None = None
    blocking: bool = False
    poll_interval: float = 2.0
    timeout: int | None = None


@dataclass(frozen=True)
class OpenWaveformRequest:
    token: str
    library: str
    cell: str
    history: str
    signals: list[str]
    view: str = "maestro"
    test: str | None = None
    analysis: str | None = None
    result: str | None = None
    timeout: int | None = None


@dataclass(frozen=True)
class CloseWaveformRequest:
    token: str
    session: str | None = None
    window: str | None = None
    timeout: int | None = None


# ---------------------------------------------------------------------------
# Small validation / formatting helpers
# ---------------------------------------------------------------------------

def _step(name: str, ok: bool, detail: Any) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail}


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_timeout(value: Any) -> None:
    if value is not None and (not isinstance(value, (int, float)) or value <= 0):
        raise ValueError("timeout must be a positive number or None")


def _require_history_name(value: Any, name: str = "history") -> str:
    text = _require_text(value, name)
    if "/" in text or "\\" in text or text in (".", "..") or ".." in text:
        raise ValueError(f"{name} must not contain path separators or '..'")
    return text


def _require_output_name(value: Any, name: str = "name") -> str:
    text = _require_text(value, name)
    if any(ch in text for ch in ("\n", "\r", "\t")):
        raise ValueError(f"{name} must not contain control characters")
    return text


def _session_kw(session: str) -> str:
    return f" ?session {q(session)}" if session else ""


def _unwrap_errset(value: Any) -> Any:
    """Unwrap the first element of an ``errset`` result list."""
    if isinstance(value, list) and len(value) == 1:
        return value[0]
    return value


def _to_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _window_target_fields(title: str) -> list[str] | None:
    """Parse the ``lib cell view`` tokens after Editing:/Reading: in a title."""
    for marker in ("Editing:", "Reading:"):
        if marker in title:
            tail = title.rsplit(marker, 1)[1].strip()
            fields = tail.split()
            if len(fields) >= 3:
                return fields[:3]
    return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _local_artifact_dir(kind: str) -> Path:
    path = artifact_dir() / "maestro" / kind
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_token(value: str | None, fallback: str = "unknown") -> str:
    text = (value or "").strip()
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text)
    return text or fallback


def _skill_atom_value(text: Any) -> Any:
    """Decode one ``%L``-printed SKILL field from a line-oriented readback."""
    value = str(text or "").strip()
    if value == "nil":
        return None
    if value == "t":
        return True
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        return unquote(value)
    if value.startswith("(") and value.endswith(")"):
        return parse_sexpr(value)
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _skill_value_expr(value: Any) -> str:
    """Serialize a write value as a SKILL expression.

    Plain strings stay SKILL strings, numbers/booleans stay atoms, and
    mappings/sequences are emitted as SKILL lists.
    """
    if isinstance(value, str):
        return q(value)
    return skill_value(value)


def _skill_name_list(value: Any, name: str) -> str:
    """Return a quoted SKILL list for ``?typeValue``-style name lists."""
    if value is None:
        raise ValueError(f"{name} is required")
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError(f"{name} must not be empty")
        if text.startswith(("'", "`")):
            return text
        if text.startswith("("):
            return "'" + text
        return "'(" + q(text) + ")"
    if isinstance(value, (list, tuple)):
        names = [str(item).strip() for item in value if str(item).strip()]
        if not names:
            raise ValueError(f"{name} must not be empty")
        return "'(" + " ".join(q(item) for item in names) + ")"
    raise ValueError(f"{name} must be a string or a list of strings")


def _skill_name_list_body(value: Any, name: str) -> str:
    """Return the parenthesized body of :func:`_skill_name_list`."""
    text = _skill_name_list(value, name)
    return text[1:] if text.startswith("'") else text


# ---------------------------------------------------------------------------
# Package
# ---------------------------------------------------------------------------

class Package:
    """Maestro domain package.

    The package is stateless: every operation resolves its own session and
    every token is passed through unchanged.
    """

    def __init__(self, middle: Middle) -> None:
        self.middle = middle

    # -- low-level Skill helpers ------------------------------------------------

    def _skill(
        self,
        expr: str,
        token: str,
        timeout: int | float | None = None,
    ) -> VirtuosoResult:
        return self.middle.execute_skill(expr, timeout=timeout, token=token)

    def _q(
        self,
        expr: str,
        token: str,
        timeout: int | float | None = None,
    ) -> str:
        result = self._skill(expr, token, timeout)
        if not result.ok:
            raise RuntimeError("; ".join(result.errors) or "SKILL execution failed")
        return result.output or ""

    def _role_root(self, token: str, role: str) -> str:
        facts = self.middle.query(token=token)
        if facts.status.value != "success":
            raise RuntimeError("; ".join(facts.errors) or "query failed")
        entry = facts.roles.get(role)
        if entry is None or not entry.root:
            raise RuntimeError(f"{role} role root is not available")
        return entry.root.rstrip("/")

    # -- session lifecycle -----------------------------------------------------

    def _session_list(self, token: str, timeout: int | float | None) -> list[str]:
        raw = self._q("maeGetSessions()", token, timeout)
        return parse_skill_str_leaves(raw)

    def _open_session(
        self,
        library: str,
        cell: str,
        view: str,
        token: str,
        timeout: int | float | None,
    ) -> tuple[str, bool]:
        """Open/reuse a Maestro session and report whether it was created."""
        before = set(self._session_list(token, timeout))
        raw = self._q(
            f"maeOpenSetup({q(library)} {q(cell)} {q(view)})",
            token,
            timeout,
        )
        session = unquote(raw)
        if not session or session in ("nil", "t"):
            raise RuntimeError(f"maeOpenSetup failed for {library}/{cell}/{view}")
        return session, session not in before

    def _save_setup(
        self,
        library: str,
        cell: str,
        view: str,
        session: str,
        token: str,
        timeout: int | float | None,
    ) -> str:
        return self._q(
            "maeSaveSetup("
            f"?lib {q(library)} ?cell {q(cell)} ?view {q(view)}"
            f"{_session_kw(session)})",
            token,
            timeout,
        )

    def _close_session(
        self,
        session: str,
        token: str,
        timeout: int | float | None,
    ) -> str:
        return self._q(
            f"maeCloseSession(?session {q(session)} ?forceClose t)",
            token,
            timeout,
        )

    def _session_windows(
        self,
        token: str,
        timeout: int | float | None,
    ) -> list[dict[str, Any]]:
        """Return Maestro windows as ``{session, window, title, mode}``."""
        expr = (
            "let((result) "
            "result = nil "
            "foreach(w hiGetWindowList() "
            "  let((s name) "
            "    s = car(errset(axlGetWindowSession(w))) "
            "    name = hiGetWindowName(w) "
            "    when(s && name "
            "      result = cons(list(s w~>windowNum name) result)))) "
            "result)"
        )
        raw = self._q(expr, token, timeout)
        parsed = parse_sexpr(raw.strip())
        windows: list[dict[str, Any]] = []
        for item in _as_list(parsed):
            if not isinstance(item, list) or len(item) < 3:
                continue
            session = str(item[0])
            window_num = _to_int(item[1])
            title = str(item[2])
            if not session or window_num is None or not title:
                continue
            if "Assembler" not in title and "Explorer" not in title:
                continue
            mode = "editing" if "Editing:" in title else "reading"
            windows.append({
                "session": session,
                "window": window_num,
                "title": title,
                "mode": mode,
            })
        return windows

    def _find_gui_session(
        self,
        library: str,
        cell: str,
        view: str,
        token: str,
        timeout: int | float | None,
    ) -> dict[str, Any] | None:
        for window in self._session_windows(token, timeout):
            fields = _window_target_fields(window["title"])
            if fields is not None and fields == [library, cell, view]:
                return window
        return None

    def _session_window(
        self,
        session: str,
        token: str,
        timeout: int | float | None,
    ) -> dict[str, Any] | None:
        for window in self._session_windows(token, timeout):
            if window["session"] == session:
                return window
        return None

    def _ensure_session_editable(
        self,
        session: str,
        token: str,
        timeout: int | float | None,
        steps: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Promote a reading GUI session to editing before a write.

        Background sessions have no window and are already writable.  A GUI
        session that was opened read-only must be promoted explicitly;
        otherwise ``maeSet*`` calls can fail or be silently ignored.
        """
        window = self._session_window(session, token, timeout)
        if window is None:
            if steps is not None:
                steps.append(_step(
                    "session_editable", True, {"session": session, "mode": "background"},
                ))
            return True
        if window["mode"] == "editing":
            if steps is not None:
                steps.append(_step(
                    "session_editable", True, {"session": session, "mode": "editing"},
                ))
            return True
        made = self.middle.execute_skill(
            f"maeMakeEditable(?session {q(session)})",
            timeout=timeout,
            token=token,
        )
        if steps is not None:
            steps.append(_step("make_editable", made.ok, made))
        if not made.ok or unquote(made.output or "") in ("", "nil"):
            return False
        window = self._session_window(session, token, timeout)
        return bool(window and window["mode"] == "editing")

    def _background_sessions(
        self,
        token: str,
        timeout: int | float | None,
    ) -> list[str]:
        """Return stale non-GUI Maestro sessions.

        Do not force-close them here: on IC6.1.8 a force-close followed
        immediately by a GUI open/close of the same cellview was observed to
        crash Virtuoso (SIGSEGV).  Session conflicts are reported to the
        caller instead; only the owning operation may close its own session.
        """
        gui_sessions = {
            window["session"] for window in self._session_windows(token, timeout)
        }
        return [
            session for session in self._session_list(token, timeout)
            if session not in gui_sessions
        ]

    def _ensure_gui_session(
        self,
        library: str,
        cell: str,
        view: str,
        token: str,
        timeout: int | float | None,
        *,
        open_if_missing: bool = True,
    ) -> dict[str, Any]:
        background_sessions = self._background_sessions(token, timeout)
        found = self._find_gui_session(library, cell, view, token, timeout)
        if found is not None:
            if found["mode"] == "reading":
                made = self._skill(
                    f"maeMakeEditable(?session {q(found['session'])})",
                    token,
                    timeout,
                )
                if not made.ok or unquote(made.output or "") in ("", "nil"):
                    raise RuntimeError(
                        f"maeMakeEditable failed for {library}/{cell}/{view}"
                    )
                found = self._find_gui_session(library, cell, view, token, timeout)
            if found is not None:
                if background_sessions:
                    found["background_sessions"] = background_sessions
                return found
        if not open_if_missing:
            raise RuntimeError(f"no GUI session is open for {library}/{cell}/{view}")

        opened = self._skill(
            f"deOpenCellView({q(library)} {q(cell)} {q(view)} "
            f'"maestro" nil "a")',
            token,
            timeout,
        )
        if not opened.ok or unquote(opened.output or "") in ("", "nil"):
            raise RuntimeError(
                f"deOpenCellView failed for {library}/{cell}/{view}: "
                f"{'; '.join(opened.errors) or opened.output or 'nil'}; "
                f"background_sessions={background_sessions}"
            )
        deadline = time.monotonic() + (float(timeout) if timeout else 60.0)
        while time.monotonic() < deadline:
            found = self._find_gui_session(library, cell, view, token, timeout)
            if found is not None:
                if background_sessions:
                    found["background_sessions"] = background_sessions
                return found
            time.sleep(0.5)
        raise RuntimeError(f"GUI window did not appear for {library}/{cell}/{view}")

    def _purge_cellview(
        self,
        library: str,
        cell: str,
        view: str,
        token: str,
        timeout: int | float | None,
    ) -> VirtuosoResult:
        expr = (
            "foreach(cv dbGetOpenCellViews() "
            f"  when(cv~>libName == {q(library)} && cv~>cellName == {q(cell)} "
            f"&& cv~>viewName == {q(view)} errset(dbPurge(cv))))"
        )
        return self._skill(expr, token, timeout)

    # -- history / result helpers ---------------------------------------------

    def _main_setup_db_expr(self, session: str) -> str:
        return f"axlGetMainSetupDB({q(session)})"

    def _history_names(
        self,
        session: str,
        library: str,
        cell: str,
        view: str,
        token: str,
        timeout: int | float | None,
    ) -> list[str]:
        expr = (
            f"cadr(axlGetHistory({self._main_setup_db_expr(session)}))"
        )
        sdb_names: list[str] = []
        try:
            sdb_names = parse_skill_str_leaves(self._q(expr, token, timeout))
        except Exception:
            sdb_names = []

        disk_names: list[str] = []
        try:
            listing_expr = (
                "let((p d) "
                f"p = ddGetObj({q(library)})~>readPath "
                f"d = strcat(p \"/{cell}/{view}/results/maestro\") "
                "if(isDir(d) getDirFiles(d) nil))"
            )
            raw = self._q(listing_expr, token, timeout)
            disk_names = natural_sort_histories(parse_skill_str_leaves(raw))
        except Exception:
            disk_names = []

        result: list[str] = []
        seen: set[str] = set()
        for name in sdb_names + disk_names:
            if name and name not in seen:
                seen.add(name)
                result.append(name)
        return result

    def _history_lock_flag(
        self,
        session: str,
        history: str,
        token: str,
        timeout: int | float | None,
    ) -> int | None:
        raw = self._q(
            f"maeGetHistoryLockFlag({q(history)}{_session_kw(session)})",
            token,
            timeout,
        )
        return _to_int(unquote(raw))

    def _run_status(
        self,
        session: str,
        history: str,
        token: str,
        timeout: int | float | None,
        *,
        option: str | None = None,
    ) -> dict[str, int | str | None]:
        option_kw = f' ?optionName {q(option)}' if option else ""
        raw = self._q(
            f"axlGetRunStatus({q(session)} ?historyName {q(history)}{option_kw})",
            token,
            timeout,
        )
        parsed = parse_sexpr(raw.strip())
        if isinstance(parsed, list) and len(parsed) >= 2:
            done = _to_int(parsed[0])
            total = _to_int(parsed[1])
            if done is not None and total is not None:
                if total <= 0:
                    status = "unknown"
                elif done >= total:
                    status = "done"
                else:
                    status = "running"
                return {"done": done, "total": total, "status": status}
        return {"done": None, "total": None, "status": "unknown"}

    def _current_history(
        self,
        session: str,
        token: str,
        timeout: int | float | None,
    ) -> str | None:
        raw = self._q(
            "let((h) "
            f"h = axlGetCurrentHistory({q(session)}) "
            "when(h axlGetHistoryName(h)))",
            token,
            timeout,
        )
        text = unquote(raw)
        return text if text and text != "nil" else None

    def _results_location(
        self,
        session: str,
        history: str,
        token: str,
        timeout: int | float | None,
    ) -> str | None:
        try:
            raw = self._q(
                "axlGetResultsLocation("
                f"axlGetHistoryEntry({self._main_setup_db_expr(session)} "
                f"{q(history)}))",
                token,
                timeout,
            )
        except Exception:
            return None
        text = unquote(raw)
        return text if text and text != "nil" else None

    def _history_entry_exists(
        self,
        session: str,
        history: str,
        token: str,
        timeout: int | float | None,
    ) -> bool:
        try:
            raw = self._q(
                "car(errset(axlGetHistoryEntry("
                f"{self._main_setup_db_expr(session)} {q(history)})))",
                token,
                timeout,
            )
        except Exception:
            return False
        text = unquote(raw)
        return bool(text and text not in ("nil", "0"))

    def _history_in_sdb(
        self,
        session: str,
        history: str,
        token: str,
        timeout: int | float | None,
    ) -> bool:
        try:
            names = parse_skill_str_leaves(self._q(
                f"cadr(axlGetHistory({self._main_setup_db_expr(session)}))",
                token,
                timeout,
            ))
        except Exception:
            return False
        return history in names

    def _latest_history(
        self,
        session: str,
        library: str,
        cell: str,
        view: str,
        token: str,
        timeout: int | float | None,
    ) -> str | None:
        names = self._history_names(session, library, cell, view, token, timeout)
        for name in reversed(names):
            raw = self._q(
                "let((r) "
                f"r = maeOpenResults(?session {q(session)} ?history {q(name)}) "
                "maeCloseResults() r)",
                token,
                timeout,
            )
            if unquote(raw) not in ("", "nil"):
                return name
        return names[-1] if names else None

    # -- atomic command builders ----------------------------------------------

    def _command_exprs(
        self,
        command: dict[str, Any],
        session: str,
    ) -> list[str]:
        """Translate one write/write_history atomic into SKILL expressions."""
        if not isinstance(command, dict):
            raise ValueError("command must be an object")
        op = command.get("op")
        if not isinstance(op, str) or not op:
            raise ValueError("command.op must be a non-empty string")
        sess = _session_kw(session)

        if op == "set_test":
            test = _require_text(command.get("test"), "command.test")
            library = _require_text(command.get("lib") or command.get("library"), "command.lib")
            cell = _require_text(command.get("cell"), "command.cell")
            view = command.get("view", "schematic")
            simulator = command.get("simulator", "spectre")
            return [
                "if(member("
                f"{q(test)} maeGetSetup({sess})) "
                f"maeSetDesign({q(test)} {q(library)} {q(cell)} {q(view)}{sess}) "
                f"maeCreateTest({q(test)} ?lib {q(library)} ?cell {q(cell)} "
                f"?view {q(view)} ?simulator {q(simulator)}{sess}))"
            ]

        if op == "set_design":
            test = _require_text(command.get("test"), "command.test")
            library = _require_text(command.get("lib") or command.get("library"), "command.lib")
            cell = _require_text(command.get("cell"), "command.cell")
            view = command.get("view", "schematic")
            return [
                f"maeSetDesign({q(test)} {q(library)} {q(cell)} {q(view)}{sess})"
            ]

        if op == "delete_test":
            test = _require_text(command.get("test"), "command.test")
            return [f"maeDeleteTest({q(test)}{sess})"]

        if op == "set_analysis":
            test = _require_text(command.get("test"), "command.test")
            analysis = _require_text(command.get("analysis"), "command.analysis")
            enable = "t" if command.get("enable", True) else "nil"
            options = skill_alist(command.get("options"), name="command.options")
            options_kw = f" ?options `{options}" if options else ""
            return [
                f"maeSetAnalysis({q(test)} {q(analysis)} ?enable {enable}"
                f"{options_kw}{sess})"
            ]

        if op == "set_var":
            name = _require_text(command.get("name"), "command.name")
            if "value" not in command:
                raise ValueError("command.value is required")
            value = _skill_value_expr(command["value"])
            type_name = command.get("type_name")
            type_value = command.get("type_value")
            scope = command.get("scope", "global")
            if scope == "test":
                type_name = "test"
                if type_value is None:
                    type_value = command.get("tests") or command.get("test")
            elif scope == "corner":
                type_name = "corner"
                if type_value is None:
                    type_value = command.get("corners") or command.get("corner")
            type_kw = ""
            if type_name in ("test", "corner"):
                names_expr = _skill_name_list(type_value, "command.type_value")
                type_kw = (
                    f" ?typeName {q(type_name)}"
                    f" ?typeValue {names_expr}"
                )
                names_body = _skill_name_list_body(
                    type_value, "command.type_value",
                )
                if type_name == "corner":
                    check = (
                        "let((sdb h) "
                        f"sdb = {self._main_setup_db_expr(session)} "
                        f"foreach(cn '{names_body} "
                        "  h = axlGetCorner(sdb cn) "
                        "  when(h == 0 || h == nil "
                        "    error(strcat(\"corner not found: \" cn)))) "
                        f"maeSetVar({q(name)} {value}{type_kw}{sess}))"
                    )
                    return [check]
                check = (
                    "let((sdb h) "
                    f"sdb = {self._main_setup_db_expr(session)} "
                    f"foreach(tn '{names_body} "
                    "  h = axlGetTest(sdb tn) "
                    "  when(h == 0 || h == nil "
                    "    error(strcat(\"test not found: \" tn)))) "
                    f"maeSetVar({q(name)} {value}{type_kw}{sess}))"
                )
                return [check]
            return [f"maeSetVar({q(name)} {value}{type_kw}{sess})"]

        if op == "delete_var":
            name = _require_text(command.get("name"), "command.name")
            sdb = self._main_setup_db_expr(session)
            scope = command.get("scope", "global")
            tests = command.get("tests")
            if tests is None and command.get("test"):
                tests = [command["test"]]
            corners = command.get("corners")
            if corners is None and command.get("corner"):
                corners = [command["corner"]]

            if scope == "all" or command.get("all_tests"):
                return [
                    "let((sdb) "
                    f"sdb = {sdb} "
                    "foreach(tn cadr(axlGetTests(sdb)) "
                    "  let((tv) "
                    f"    tv = axlGetVar(axlGetTest(sdb tn) {q(name)}) "
                    "    when(tv axlRemoveElement(tv)))) "
                    "foreach(cn cadr(axlGetCorners(sdb)) "
                    "  let((cv) "
                    f"    cv = axlGetVar(axlGetCorner(sdb cn) {q(name)}) "
                    "    when(cv axlRemoveElement(cv)))) "
                    "let((gv) "
                    f"  gv = axlGetVar(sdb {q(name)}) "
                    "  when(gv axlRemoveElement(gv))))"
                ]

            if scope == "corner" or corners:
                if not corners:
                    raise ValueError("command.corner is required for corner scope")
                body = _skill_name_list_body(corners, "command.corners")
                return [
                    "let((sdb h) "
                    f"sdb = {sdb} "
                    f"foreach(cn '{body} "
                    "  h = axlGetCorner(sdb cn) "
                    "  when(h == 0 || h == nil "
                    "    error(strcat(\"corner not found: \" cn)))) "
                    f"foreach(cn '{body} "
                    "  let((cv) "
                    f"    cv = axlGetVar(axlGetCorner(sdb cn) {q(name)}) "
                    "    when(cv axlRemoveElement(cv)))))"
                ]

            if scope == "test" or tests:
                if not tests:
                    raise ValueError("command.test is required for test scope")
                exprs = [
                    "let((tv) "
                    f"tv = axlGetVar(axlGetTest({sdb} {q(test)}) {q(name)}) "
                    "when(tv axlRemoveElement(tv)))"
                    for test in (tests if isinstance(tests, (list, tuple)) else [tests])
                ]
                return ["progn(" + " ".join(exprs) + ")"]

            return [
                "let((gv) "
                f"gv = axlGetVar({sdb} {q(name)}) "
                "when(gv axlRemoveElement(gv)))"
            ]

        if op == "set_parameter":
            name = _require_text(command.get("name"), "command.name")
            if "value" not in command:
                raise ValueError("command.value is required")
            if len([part for part in name.split("/") if part.strip()]) < 5:
                raise ValueError(
                    "command.name must be Library/Cell/View/Instance/Property"
                )
            scope = command.get("scope", "global")
            if command.get("type_name") == "corner":
                scope = "corner"
            corners = command.get("corners")
            if corners is None and command.get("corner"):
                corners = [command["corner"]]
            if scope == "corner" or corners:
                if not corners:
                    raise ValueError("command.corner is required for corner scope")
                body = _skill_name_list_body(corners, "command.corners")
                type_kw = f" ?typeName \"corner\" ?typeValue `{body}"
                return [
                    "let((sdb h) "
                    f"sdb = {self._main_setup_db_expr(session)} "
                    f"foreach(cn '{body} "
                    "  h = axlGetCorner(sdb cn) "
                    "  when(h == 0 || h == nil "
                    "    error(strcat(\"corner not found: \" cn)))) "
                    f"maeSetParameter({q(name)} "
                    f"{_skill_value_expr(command['value'])}{type_kw}{sess}))"
                ]
            else:
                # Per the SKILL reference, a test-level parameter is global.
                type_kw = ""
            return [
                f"maeSetParameter({q(name)} {_skill_value_expr(command['value'])}"
                f"{type_kw}{sess})"
            ]

        if op == "delete_parameter":
            name = _require_text(command.get("name"), "command.name")
            scope = command.get("scope", "global")
            corners = command.get("corners")
            if corners is None and command.get("corner"):
                corners = [command["corner"]]
            sdb = self._main_setup_db_expr(session)
            if scope == "corner" or corners:
                if not corners:
                    raise ValueError("command.corner is required for corner scope")
                body = _skill_name_list_body(corners, "command.corners")
                return [
                    "let((sdb h) "
                    f"sdb = {sdb} "
                    f"foreach(cn '{body} "
                    "  h = axlGetCorner(sdb cn) "
                    "  when(h == 0 || h == nil "
                    "    error(strcat(\"corner not found: \" cn)))) "
                    f"foreach(cn '{body} "
                    "  let((ph) "
                    f"    ph = axlGetParameter(axlGetCorner(sdb cn) {q(name)}) "
                    "    when(ph axlRemoveElement(ph)))))"
                ]
            return [
                "let((ph) "
                f"ph = axlGetParameter({sdb} {q(name)}) "
                "when(ph axlRemoveElement(ph)))"
            ]

        if op in ("set_env_option", "set_sim_option"):
            test = _require_text(command.get("test"), "command.test")
            options = skill_alist(command.get("options"), name="command.options")
            if not options:
                raise ValueError("command.options is required")
            fn = "maeSetEnvOption" if op == "set_env_option" else "maeSetSimOption"
            return [f"{fn}({q(test)} ?options `{options}{sess})"]

        if op == "set_corner":
            name = _require_text(command.get("name"), "command.name")
            parts = [f"maeSetCorner({q(name)}"]
            if "enabled" in command:
                parts.append(f" ?enabled {'t' if command['enabled'] else 'nil'}")
            if command.get("enable_tests"):
                body = _skill_name_list_body(
                    command["enable_tests"], "command.enable_tests",
                )
                parts.append(f" ?enableTests `{body}")
            if command.get("disable_tests"):
                body = _skill_name_list_body(
                    command["disable_tests"], "command.disable_tests",
                )
                parts.append(f" ?disableTests `{body}")
            parts.append(f"{sess})")
            return ["".join(parts)]

        if op == "delete_corner":
            name = _require_text(command.get("name"), "command.name")
            return [f"maeDeleteCorner({q(name)}{sess})"]

        if op == "setup_corner":
            name = _require_text(command.get("name"), "command.name")
            exprs = [f"maeSetCorner({q(name)}{sess})"]
            for var_name, var_value in (command.get("variables") or {}).items():
                exprs.append(
                    f"maeSetVar({q(var_name)} {_skill_value_expr(var_value)} "
                    f"?typeName \"corner\" ?typeValue "
                    f"{_skill_name_list(name, 'command.name')}{sess})"
                )
            model_file = command.get("model_file")
            model_section = command.get("model_section")
            if model_file:
                model_name = str(model_file).rsplit("/", 1)[-1]
                model_expr = (
                    "let((sdb corn model) "
                    f"sdb = {self._main_setup_db_expr(session)} "
                    f"corn = axlGetCorner(sdb {q(name)}) "
                    f"model = axlPutModel(corn {q(model_name)}) "
                    f"axlSetModelFile(model {q(model_file)}) "
                )
                if model_section:
                    model_expr += f"axlSetModelSection(model {q(model_section)}) "
                model_expr += "model)"
                exprs.append(model_expr)
            return ["progn(" + " ".join(exprs) + ")"]

        if op == "load_corners":
            filepath = _require_text(
                command.get("filepath") or command.get("remote_path"),
                "command.filepath",
            )
            sections = command.get("sections", "corners")
            operation = command.get("operation", "overwrite")
            return [
                f"maeLoadCorners({q(filepath)} ?sections {q(sections)} "
                f"?operation {q(operation)})"
            ]

        if op == "set_run_mode":
            mode = _require_text(command.get("run_mode"), "command.run_mode")
            return [f"maeSetCurrentRunMode(?runMode {q(mode)}{sess})"]

        if op == "set_job_control_mode":
            mode = _require_text(command.get("mode"), "command.mode")
            return [f"maeSetJobControlMode({q(mode)}{sess})"]

        if op == "set_job_policy":
            policy = command.get("policy")
            if policy is None:
                raise ValueError("command.policy is required")
            test_name = command.get("test") or command.get("test_name")
            job_type = command.get("job_type")
            lookup_kw = ""
            set_kw = ""
            if test_name:
                lookup_kw += f" ?testName {q(test_name)}"
                set_kw += f" ?testName {q(test_name)}"
            if job_type:
                lookup_kw += f" ?jobType {q(job_type)}"
                set_kw += f" ?jobType {q(job_type)}"
            lookup_kw += sess
            set_kw += sess
            if isinstance(policy, dict):
                assignments = []
                for key, value in policy.items():
                    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", str(key)):
                        raise ValueError(f"invalid job policy property: {key!r}")
                    assignments.append(f"jp->{key} = {_skill_value_expr(value)}")
                return [
                    "let((jp) "
                    f"jp = maeGetJobPolicy({lookup_kw}) "
                    f"when(jp {' '.join(assignments)}) "
                    f"maeSetJobPolicy(jp{set_kw}))"
                ]
            if isinstance(policy, str):
                text = policy.strip()
                if not text.startswith(("(", "'")):
                    raise ValueError(
                        "command.policy string must be a raw job-policy expression"
                    )
                return [f"maeSetJobPolicy({text}{set_kw})"]
            raise ValueError("command.policy must be a mapping or raw expression")

        if op == "set_simulator_mode":
            mode = _require_text(command.get("mode"), "command.mode")
            option = command.get("option", "uniMode")
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", str(option)):
                raise ValueError("command.option must be a SKILL symbol name")
            return [
                "let((as) "
                f"as = asiGetSession({q(session)}) "
                "when(as "
                f"  asiSetHighPerformanceOptionVal(as '{option} {q(mode)}) "
                f"  asiGetHighPerformanceOptionVal(as '{option})))"
            ]

        if op == "add_output":
            name = _require_text(command.get("name"), "command.name")
            test = _require_text(command.get("test"), "command.test")
            parts = [f"maeAddOutput({q(name)} {q(test)}"]
            mapping = (
                ("output_type", "outputType"),
                ("signal_name", "signalName"),
                ("expr", "expr"),
            )
            for key, keyword in mapping:
                if command.get(key):
                    parts.append(f" ?{keyword} {q(command[key])}")
            for key, keyword in (("plot", "plot"), ("save", "save")):
                if key in command:
                    parts.append(f" ?{keyword} {'t' if command[key] else 'nil'}")
            parts.append(f"{sess})")
            return ["".join(parts)]

        if op == "set_spec":
            name = _require_text(command.get("name"), "command.name")
            test = _require_text(command.get("test"), "command.test")
            aliases = {
                "gt": "gt",
                "lt": "lt",
                "min": "min",
                "minimum": "min",
                "max": "max",
                "maximum": "max",
                "tol": "tol",
                "tolerance": "tol",
                "range": "range",
            }
            bounds = [
                (aliases[key], command[key])
                for key in aliases
                if key in command and command[key] is not None
            ]
            distinct = {key for key, _ in bounds}
            if len(distinct) > 1:
                raise ValueError(
                    "one output can carry only one spec bound "
                    "(gt/lt/min/max/tol/range)"
                )
            if not bounds and not any(
                command.get(key) is not None
                for key in ("info", "weight", "corner")
            ):
                raise ValueError("set_spec requires one spec bound")
            parts = [
                "let((rc) rc = axlAddSpecToOutput("
                f"{self._main_setup_db_expr(session)} {q(test)} {q(name)}"
            ]
            if bounds:
                key, value = bounds[0]
                parts.append(f" ?{key} {_skill_value_expr(value)}")
            for key in ("info", "weight", "corner"):
                if command.get(key) is not None:
                    parts.append(f" ?{key} {_skill_value_expr(command[key])}")
            parts.append(
                ') if(rc == t t error(if(stringp(rc) rc "spec failed"))))'
            )
            return ["".join(parts)]

        if op == "delete_output":
            name = _require_text(command.get("name"), "command.name")
            test = _require_text(command.get("test"), "command.test")
            exprs = [f"maeDeleteOutput({q(name)} {q(test)}{sess})"]
            if command.get("delete_spec"):
                spec_name = command.get("spec_name") or f"{test}.{name}"
                exprs.append(
                    "let((sp) "
                    f"sp = axlGetSpec({self._main_setup_db_expr(session)} "
                    f"{q(spec_name)}) "
                    "when(sp axlRemoveElement(sp)))"
                )
            return exprs

        if op == "delete_spec":
            name = command.get("spec_name") or command.get("name")
            name = _require_text(name, "command.spec_name")
            test = command.get("test")
            output = command.get("output")
            if test and output:
                name = f"{test}.{output}"
            return [
                "let((sp) "
                f"sp = axlGetSpec({self._main_setup_db_expr(session)} {q(name)}) "
                "when(sp axlRemoveElement(sp)))"
            ]

        # -- history atomics ---------------------------------------------------
        if op == "delete":
            history = _require_history_name(command.get("history"))
            return [
                "let((sdb rc) "
                f"sdb = {self._main_setup_db_expr(session)} "
                f"rc = errset(axlRemoveElement(axlGetHistoryEntry(sdb {q(history)}))) "
                "if(rc car(rc) nil))"
            ]

        if op == "delete_results":
            history = _require_history_name(command.get("history"))
            keep_netlist = "t" if command.get("keep_netlist") else "nil"
            keep_quick = "t" if command.get("keep_quick_plot") else "nil"
            return [
                f"maeDeleteSimulationData({q(history)} ?keepNetlist {keep_netlist} "
                f"?keepQuickPlot {keep_quick}{sess})"
            ]

        if op == "rename":
            history = _require_history_name(command.get("history"))
            new_name = _require_history_name(command.get("new_name"), "command.new_name")
            return [
                "let((sdb h) "
                f"sdb = {self._main_setup_db_expr(session)} "
                f"h = axlGetHistoryEntry(sdb {q(history)}) "
                f"when(h axlSetHistoryName(h {q(new_name)})))"
            ]

        if op in ("lock", "unlock"):
            history = _require_history_name(command.get("history"))
            lock_value = "t" if op == "lock" else "nil"
            return [
                f"maeSetHistoryLock({q(history)} {lock_value}{sess})"
            ]

        raise ValueError(f"unknown atomic op: {op}")

    # -- session cleanup helper ------------------------------------------------

    def _close_if_created(
        self,
        session: str | None,
        created: bool,
        token: str,
        timeout: int | float | None,
        steps: list[dict[str, Any]],
    ) -> None:
        if not created or not session:
            return
        try:
            out = self._close_session(session, token, timeout)
            steps.append(_step("close_session", True, out))
        except Exception as exc:  # noqa: BLE001 - close is best-effort
            steps.append(_step("close_session", False, str(exc)))

    # -- read_config -----------------------------------------------------------

    def read_config(self, request: ReadConfigRequest) -> Result:
        _require_text(request.token, "token")
        _require_text(request.library, "library")
        _require_text(request.cell, "cell")
        _require_text(request.view, "view")
        _require_timeout(request.timeout)

        steps: list[dict[str, Any]] = []
        result: Result | None = None
        session: str | None = None
        created = False
        try:
            session, created = self._open_session(
                request.library, request.cell, request.view,
                request.token, request.timeout,
            )
            steps.append(_step(
                "open_session", True,
                {"session": session, "created": created},
            ))

            setup_expr = (
                "let((s) "
                f"s = {q(session)} "
                "list("
                "maeGetSetup(?session s) "
                "maeGetSetup(?typeName \"corners\" ?session s) "
                "maeGetSetup(?typeName \"variables\" ?session s) "
                "maeGetSetup(?typeName \"parameters\" ?session s) "
                "maeGetCurrentRunMode(?session s) "
                "maeGetJobControlMode(?session s)))"
            )
            setup_raw = self._q(setup_expr, request.token, request.timeout)
            setup = parse_sexpr(setup_raw.strip())
            if not isinstance(setup, list) or len(setup) < 6:
                raise RuntimeError("could not parse maeGetSetup readback")
            tests = [str(item) for item in _as_list(setup[0])]
            corners = [str(item) for item in _as_list(setup[1])]
            # maeGetSetup(?typeName "variables") only reports variables that
            # exist in the global table; test-only variables are invisible.
            # The axl* list APIs are the authoritative per-scope sources.
            sdb_expr = self._main_setup_db_expr(session)
            variable_names = parse_skill_str_leaves(self._q(
                f"cadr(axlGetVars({sdb_expr}))",
                request.token,
                request.timeout,
            ))
            parameter_names = parse_skill_str_leaves(self._q(
                f"axlGetParameters({sdb_expr})",
                request.token,
                request.timeout,
            ))
            run_mode = setup[4]
            job_control_mode = setup[5]
            steps.append(_step("setup", True, {
                "tests": tests,
                "corners": corners,
                "global_variables": variable_names,
                "global_parameters": parameter_names,
            }))

            analyses: dict[str, dict[str, Any]] = {}
            if tests:
                tests_list = skill_string_list(tests)
                analyses_expr = (
                    "let((s) "
                    f"s = {q(session)} "
                    "mapcar(lambda((tn) list(tn "
                    "mapcar(lambda((an) list(an "
                    "maeGetAnalysis(tn an ?session s))) "
                    "maeGetEnabledAnalysis(tn ?session s)))) "
                    f"'{tests_list}))"
                )
                analyses_raw = self._q(analyses_expr, request.token, request.timeout)
                parsed_analyses = parse_sexpr(analyses_raw.strip())
                if isinstance(parsed_analyses, list):
                    for test_item in parsed_analyses:
                        if not isinstance(test_item, list) or len(test_item) < 2:
                            continue
                        test_name = str(test_item[0])
                        test_analyses: dict[str, Any] = {}
                        for ana_item in _as_list(test_item[1]):
                            if not isinstance(ana_item, list) or len(ana_item) < 2:
                                continue
                            ana_name = str(ana_item[0])
                            test_analyses[ana_name] = pairs_to_dict(ana_item[1])
                        analyses[test_name] = test_analyses
                steps.append(_step("analyses", True, analyses))

            env_options: dict[str, dict[str, Any]] = {}
            sim_options: dict[str, dict[str, Any]] = {}
            for test_name in tests:
                try:
                    env_raw = self._q(
                        f"maeGetEnvOption({q(test_name)}{_session_kw(session)})",
                        request.token,
                        request.timeout,
                    )
                    env_options[test_name] = pairs_to_dict(
                        parse_sexpr(env_raw.strip())
                    )
                except Exception:
                    env_options[test_name] = {}
                try:
                    sim_raw = self._q(
                        f"maeGetSimOption({q(test_name)}{_session_kw(session)})",
                        request.token,
                        request.timeout,
                    )
                    sim_options[test_name] = pairs_to_dict(
                        parse_sexpr(sim_raw.strip())
                    )
                except Exception:
                    sim_options[test_name] = {}
            steps.append(_step("options", True, {
                "env": env_options,
                "sim": sim_options,
            }))

            outputs: dict[str, list[dict[str, Any]]] = {}
            if tests:
                tests_list = skill_string_list(tests)
                outputs_expr = (
                    "let((s) "
                    f"s = {q(session)} "
                    "buildString(mapcar(lambda((tn) "
                    "sprintf(nil \"TEST\\t%s\\n%s\" tn "
                    "buildString(mapcar(lambda((o) "
                    "sprintf(nil \"OUT\\t%L\\t%L\\t%L\\t%L\\t%L\\t%L\\t%L\\t%L\\t%L\\n\" "
                    "o~>name o~>type o~>signal o~>expression o~>plot "
                    "o~>save o~>evalType o~>yaxisUnit o~>spec)) "
                    "maeGetTestOutputs(tn ?session s)) \"\"))) "
                    f"'{tests_list}) \"\"))"
                )
                outputs_raw = self._q(outputs_expr, request.token, request.timeout)
                current_test: str | None = None
                for line in decode_skill_text(outputs_raw).splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("TEST\t"):
                        current_test = unquote(line[len("TEST\t"):].strip())
                        outputs.setdefault(current_test, [])
                        continue
                    if line.startswith("OUT\t") and current_test:
                        fields = line[len("OUT\t"):].split("\t")
                        fields += ["nil"] * (9 - len(fields))
                        outputs[current_test].append({
                            "name": _skill_atom_value(fields[0]),
                            "type": _skill_atom_value(fields[1]),
                            "signal": _skill_atom_value(fields[2]),
                            "expression": _skill_atom_value(fields[3]),
                            "plot": _skill_atom_value(fields[4]),
                            "save": _skill_atom_value(fields[5]),
                            "eval_type": _skill_atom_value(fields[6]),
                            "yaxis_unit": _skill_atom_value(fields[7]),
                            "spec": _skill_atom_value(fields[8]),
                        })
                steps.append(_step("outputs", True, outputs))

            variables: dict[str, Any] = {}
            if variable_names:
                variables_expr = (
                    "let((s) "
                    f"s = {q(session)} "
                    "mapcar(lambda((n) list(n "
                    "maeGetVar(n ?session s))) "
                    f"'{skill_string_list(variable_names)}))"
                )
                variables_raw = self._q(variables_expr, request.token, request.timeout)
                for item in _as_list(parse_sexpr(variables_raw.strip())):
                    if isinstance(item, list) and len(item) >= 2:
                        variables[str(item[0])] = item[1]
                steps.append(_step("variables", True, variables))

            test_variables: dict[str, dict[str, Any]] = {}
            for test_name in tests:
                try:
                    names_raw = self._q(
                        "cadr(axlGetVars(axlGetTest("
                        f"{sdb_expr} {q(test_name)})))",
                        request.token,
                        request.timeout,
                    )
                    names = parse_skill_str_leaves(names_raw)
                    if not names:
                        test_variables[test_name] = {}
                        continue
                    values_expr = (
                        "let((s) "
                        f"s = {q(session)} "
                        "mapcar(lambda((n) list(n "
                        f"maeGetVar(n ?typeName \"test\" ?typeValue {q(test_name)} "
                        "?session s))) "
                        f"'{skill_string_list(names)}))"
                    )
                    values_raw = self._q(
                        values_expr, request.token, request.timeout,
                    )
                    values: dict[str, Any] = {}
                    for item in _as_list(parse_sexpr(values_raw.strip())):
                        if isinstance(item, list) and len(item) >= 2:
                            values[str(item[0])] = item[1]
                    test_variables[test_name] = values
                except Exception:
                    test_variables[test_name] = {}
            steps.append(_step("test_variables", True, test_variables))

            corner_variables: dict[str, dict[str, Any]] = {}
            for corner in corners:
                try:
                    names_raw = self._q(
                        "cadr(axlGetVars(axlGetCorner("
                        f"{self._main_setup_db_expr(session)} {q(corner)})))",
                        request.token,
                        request.timeout,
                    )
                    names = parse_skill_str_leaves(names_raw)
                    if not names:
                        corner_variables[corner] = {}
                        continue
                    values_expr = (
                        "let((s) "
                        f"s = {q(session)} "
                        "mapcar(lambda((n) list(n "
                        f"maeGetVar(n ?typeName \"corner\" ?typeValue {q(corner)} "
                        "?session s))) "
                        f"'{skill_string_list(names)}))"
                    )
                    values_raw = self._q(
                        values_expr, request.token, request.timeout,
                    )
                    values: dict[str, Any] = {}
                    for item in _as_list(parse_sexpr(values_raw.strip())):
                        if isinstance(item, list) and len(item) >= 2:
                            values[str(item[0])] = item[1]
                    corner_variables[corner] = values
                except Exception:
                    corner_variables[corner] = {}
            steps.append(_step("corner_variables", True, corner_variables))

            parameters: dict[str, Any] = {}
            if request.include_parameters and parameter_names:
                parameters_expr = (
                    "let((s) "
                    f"s = {q(session)} "
                    "mapcar(lambda((n) list(n "
                    "maeGetParameter(n ?session s))) "
                    f"'{skill_string_list(parameter_names)}))"
                )
                parameters_raw = self._q(
                    parameters_expr, request.token, request.timeout,
                )
                for item in _as_list(parse_sexpr(parameters_raw.strip())):
                    if isinstance(item, list) and len(item) >= 2:
                        parameters[str(item[0])] = item[1]
                steps.append(_step("parameters", True, parameters))

            corner_parameters: dict[str, dict[str, Any]] = {}
            for corner in corners:
                try:
                    paths_raw = self._q(
                        "axlGetParameters(axlGetCorner("
                        f"{sdb_expr} {q(corner)}))",
                        request.token,
                        request.timeout,
                    )
                    paths = parse_skill_str_leaves(paths_raw)
                    values: dict[str, Any] = {}
                    for path in paths:
                        value_raw = self._q(
                            f"maeGetParameter({q(path)} ?typeName \"corner\" "
                            f"?typeValue {q(corner)}{_session_kw(session)})",
                            request.token,
                            request.timeout,
                        )
                        values[path] = _skill_atom_value(unquote(value_raw))
                    corner_parameters[corner] = values
                except Exception:
                    corner_parameters[corner] = {}
            steps.append(_step("corner_parameters", True, corner_parameters))

            specs: list[dict[str, Any]] = []
            for test_name, items in outputs.items():
                for item in items:
                    output_name = item.get("name")
                    if not output_name:
                        continue
                    try:
                        spec_raw = self._q(
                            "axlGetSpecData("
                            f"axlGetMainSetupDB({q(session)}) "
                            f"{q(output_name)} {q(test_name)})",
                            request.token,
                            request.timeout,
                        )
                        spec_parsed = parse_sexpr(spec_raw.strip())
                    except Exception:
                        spec_parsed = None
                    if isinstance(spec_parsed, list) and spec_parsed:
                        entry = {
                            "name": f"{test_name}.{output_name}",
                            "test": test_name,
                            "output": output_name,
                            "type": spec_parsed[0],
                            "value": spec_parsed[1] if len(spec_parsed) > 1 else None,
                        }
                        specs.append(entry)
                        item["spec"] = {
                            "type": entry["type"],
                            "value": entry["value"],
                        }
            steps.append(_step("specs", True, specs))

            current_history = self._current_history(
                session, request.token, request.timeout,
            )
            config = {
                "library": request.library,
                "cell": request.cell,
                "view": request.view,
                "tests": tests,
                "corners": corners,
                "corner_variables": corner_variables,
                "test_variables": test_variables,
                "variables": variables,
                "parameters": parameters,
                "corner_parameters": corner_parameters,
                "analyses": analyses,
                "env_options": env_options,
                "sim_options": sim_options,
                "outputs": outputs,
                "specs": specs,
                "run_mode": run_mode,
                "job_control_mode": job_control_mode,
                "current_history": current_history,
            }
            if request.include_raw:
                config["raw"] = {
                    "setup": setup_raw,
                    "analyses": locals().get("analyses_raw", ""),
                    "outputs": locals().get("outputs_raw", ""),
                }
            result = Result(True, steps, None, config)
        except Exception as exc:  # noqa: BLE001 - structured business failure
            result = Result(False, steps, f"{type(exc).__name__}: {exc}")
        finally:
            self._close_if_created(
                session, created, request.token, request.timeout, steps,
            )
        return result or Result(False, steps, "read_config failed")

    # -- write -----------------------------------------------------------------

    def write(self, request: WriteRequest) -> Result:
        _require_text(request.token, "token")
        _require_text(request.library, "library")
        _require_text(request.cell, "cell")
        _require_text(request.view, "view")
        _require_timeout(request.timeout)
        if not isinstance(request.commands, list) or not request.commands:
            raise ValueError("commands must be a non-empty list")

        steps: list[dict[str, Any]] = []
        result: Result | None = None
        session: str | None = None
        created = False
        try:
            session, created = self._open_session(
                request.library, request.cell, request.view,
                request.token, request.timeout,
            )
            steps.append(_step(
                "open_session", True,
                {"session": session, "created": created},
            ))
            if not self._ensure_session_editable(
                session, request.token, request.timeout, steps,
            ):
                result = Result(False, steps, "session is not editable")
                raise RuntimeError("session is not editable")
            for index, command in enumerate(request.commands):
                op = command.get("op") if isinstance(command, dict) else None
                try:
                    prepared = dict(command) if isinstance(command, dict) else command
                    if (
                        isinstance(prepared, dict)
                        and prepared.get("op") == "load_corners"
                        and prepared.get("local_path")
                    ):
                        remote_path = prepared.get("remote_path")
                        if not remote_path:
                            daemon_root = self._role_root(request.token, "daemon")
                            remote_path = posixpath.join(
                                daemon_root,
                                f".maestro-corners-{uuid.uuid4().hex}.csv",
                            )
                        uploaded = self.middle.upload_file(
                            Path(prepared["local_path"]),
                            remote_path,
                            timeout=request.timeout,
                            token=request.token,
                        )
                        steps.append(_step(
                            "upload_corners",
                            uploaded.returncode == 0,
                            uploaded,
                        ))
                        if uploaded.returncode != 0:
                            result = Result(
                                False, steps,
                                uploaded.stderr or "corner CSV upload failed",
                            )
                            break
                        prepared["filepath"] = remote_path
                    exprs = self._command_exprs(prepared, session)
                except Exception as exc:  # noqa: BLE001 - command validation
                    result = Result(
                        False, steps,
                        f"command {index} invalid: {exc}",
                    )
                    break
                failed = False
                for expr in exprs:
                    run = self.middle.execute_skill(
                        expr, timeout=request.timeout, token=request.token,
                    )
                    steps.append(_step(f"command:{op}", run.ok, run))
                    if not run.ok:
                        result = Result(
                            False, steps,
                            "; ".join(run.errors) or f"command {op} failed",
                        )
                        failed = True
                        break
                if failed:
                    break
            else:
                value = {"applied": len(request.commands), "session": session}
                if request.save:
                    try:
                        saved = self._save_setup(
                            request.library, request.cell, request.view,
                            session, request.token, request.timeout,
                        )
                        steps.append(_step("save_setup", True, saved))
                    except Exception as exc:  # noqa: BLE001
                        result = Result(
                            False, steps, f"save_setup failed: {exc}",
                        )
                        raise
                if result is None:
                    result = Result(True, steps, None, value)
        except Exception as exc:  # noqa: BLE001
            if result is None:
                result = Result(False, steps, f"{type(exc).__name__}: {exc}")
        finally:
            self._close_if_created(
                session, created, request.token, request.timeout, steps,
            )
        return result or Result(False, steps, "write failed")

    # -- read_results ----------------------------------------------------------

    def _results_dir_for_history(
        self,
        session: str,
        history: str,
        token: str,
        timeout: int | float | None,
    ) -> str | None:
        try:
            base = unquote(self._q(
                "axlGetResultsLocation("
                f"axlGetMainSetupDB({q(session)}))",
                token,
                timeout,
            ))
        except Exception:
            return None
        if not base or base == "nil":
            return None
        base = base.rstrip("/")
        if base.endswith("/" + history):
            return base + "/"
        return posixpath.join(base, history) + "/"

    def _find_psf_dir(
        self,
        history_dir: str,
        test: str | None,
        analysis: str | None,
        token: str,
        timeout: int | float | None,
    ) -> str | None:
        """Locate the PSF directory that ``openResults`` should open.

        Maestro stores single-point results under
        ``<history>/<point>/<test>/psf``.  There is no portable SKILL
        accessor that is independent of the focused GUI window, so this
        helper asks the command interface for ``logFile`` markers and
        selects the first matching point/test/analysis combination.
        """
        cmd = (
            f"find {history_dir} -type f -name logFile 2>/dev/null | sort"
        )
        result = self.middle.run_command(cmd, timeout=timeout, token=token)
        if result.returncode != 0:
            return None
        candidates = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        directories = [posixpath.dirname(path) for path in candidates]
        if test:
            directories = [
                path for path in directories if f"/{test}/" in path + "/"
            ]
        if analysis:
            directories = [
                path for path in directories if f"/{analysis}/" in path + "/"
            ]
        if not directories:
            directories = [posixpath.dirname(path) for path in candidates]
        if not directories:
            return None
        directories.sort(key=lambda path: (0 if "/1/" in path else 1, path))
        return directories[0]

    def read_results(self, request: ReadResultsRequest) -> Result:
        _require_text(request.token, "token")
        _require_text(request.library, "library")
        _require_text(request.cell, "cell")
        _require_text(request.view, "view")
        _require_timeout(request.timeout)
        if request.history is not None:
            _require_history_name(request.history)
        if request.precision is not None and not 1 <= request.precision <= 16:
            raise ValueError("precision must be between 1 and 16")
        if request.width is not None and request.width < 4:
            raise ValueError("width must be >= 4")
        if request.notation not in ("suffix", "engineering", "scientific", "none"):
            raise ValueError(
                "notation must be suffix/engineering/scientific/none"
            )
        if request.waveform and not request.analysis:
            raise ValueError("analysis is required when waveform is requested")

        steps: list[dict[str, Any]] = []
        result: Result | None = None
        session: str | None = None
        created = False
        try:
            session, created = self._open_session(
                request.library, request.cell, request.view,
                request.token, request.timeout,
            )
            steps.append(_step(
                "open_session", True,
                {"session": session, "created": created},
            ))
            history = request.history or self._latest_history(
                session, request.library, request.cell, request.view,
                request.token, request.timeout,
            )
            if not history:
                raise RuntimeError("no Maestro history is available")

            if request.waveform:
                history_dir = self._results_dir_for_history(
                    session, history, request.token, request.timeout,
                )
                if not history_dir:
                    raise RuntimeError("could not determine results directory")
                results_dir = self._find_psf_dir(
                    history_dir, request.test, request.analysis,
                    request.token, request.timeout,
                )
                if not results_dir:
                    raise RuntimeError(
                        f"no PSF logFile found under {history_dir}"
                    )
                daemon_root = self._role_root(request.token, "daemon")
                remote_txt = posixpath.join(
                    daemon_root,
                    f".maestro-wave-{_safe_token(history)}-"
                    f"{uuid.uuid4().hex}.txt",
                )
                expr = request.waveform.strip()
                if not expr.startswith(("(", "v(")):
                    expr = f"v({q(expr)}"
                    if request.result:
                        expr += f" ?result {q(request.result)}"
                    expr += ")"
                elif request.result and expr.startswith("v("):
                    expr = expr[:-1] + f" ?result {q(request.result)})"
                precision_kw = (
                    f" ?precision {request.precision}"
                    if request.precision is not None else ""
                )
                width_kw = (
                    f" ?width {request.width}"
                    if request.width is not None else ""
                )
                skill = (
                    "progn("
                    f"openResults({q(results_dir)}) "
                    f"selectResults({q(request.analysis)}) "
                    f"ocnPrint({expr} "
                    f"?numberNotation '{request.notation}{precision_kw}{width_kw} "
                    f"?numSpaces 1 ?output {q(remote_txt)}))"
                )
                run = self.middle.execute_skill(
                    skill, timeout=request.timeout, token=request.token,
                )
                steps.append(_step("waveform", run.ok, run))
                if not run.ok:
                    raise RuntimeError("; ".join(run.errors) or "ocnPrint failed")

                local_path = (
                    Path(request.output_path)
                    if request.output_path
                    else _local_artifact_dir("waves")
                    / f"{_safe_token(history)}-{uuid.uuid4().hex}.txt"
                )
                downloaded = self.middle.download_file(
                    remote_txt, local_path,
                    timeout=request.timeout, token=request.token,
                )
                steps.append(_step("download_waveform",
                                   downloaded.returncode == 0, downloaded))
                if downloaded.returncode != 0:
                    raise RuntimeError(downloaded.stderr or "waveform download failed")
                try:
                    text = local_path.read_text(encoding="utf-8", errors="replace")
                except OSError as exc:
                    raise RuntimeError(f"cannot read downloaded waveform: {exc}")
                points = parse_ocn_text(text)
                self.middle.run_command(
                    f"rm -f {remote_txt}", timeout=10, token=request.token,
                )
                result = Result(True, steps, None, {
                    "history": history,
                    "waveform": points,
                    "local_path": str(local_path),
                    "results_dir": results_dir,
                })
            else:
                test_kw = f" ?testName {q(request.test)}" if request.test else ""
                daemon_root = self._role_root(request.token, "daemon")
                remote_csv = posixpath.join(
                    daemon_root,
                    f".maestro-results-{_safe_token(history)}-"
                    f"{uuid.uuid4().hex}.csv",
                )
                export = self.middle.execute_skill(
                    f"maeExportOutputView(?session {q(session)}{test_kw} "
                    f"?historyName {q(history)} ?view \"Detail\" "
                    f"?fileName {q(remote_csv)})",
                    timeout=request.timeout,
                    token=request.token,
                )
                steps.append(_step("export_detail", export.ok, export))
                if not export.ok:
                    raise RuntimeError(
                        "; ".join(export.errors) or "maeExportOutputView failed"
                    )
                local_path = (
                    Path(request.output_path)
                    if request.output_path
                    else _local_artifact_dir("results")
                    / f"{_safe_token(history)}-{uuid.uuid4().hex}.csv"
                )
                downloaded = self.middle.download_file(
                    remote_csv, local_path,
                    timeout=request.timeout, token=request.token,
                )
                steps.append(_step("download_detail",
                                   downloaded.returncode == 0, downloaded))
                if downloaded.returncode != 0:
                    raise RuntimeError(downloaded.stderr or "detail CSV download failed")
                try:
                    text = local_path.read_text(encoding="utf-8", errors="replace")
                except OSError as exc:
                    raise RuntimeError(f"cannot read downloaded Detail CSV: {exc}")
                parsed = parse_detail_csv(text, history=history)

                overall_spec: Any = None
                statuses = [
                    info.get("pass_fail", "")
                    for point in parsed["points"]
                    for info in point["outputs"].values()
                ]
                statuses = [status for status in statuses if str(status).strip()]
                if statuses:
                    overall_spec = (
                        "passed"
                        if all(str(status).lower().startswith("pass")
                               for status in statuses)
                        else "failed"
                    )
                overall_yield: dict[str, Any] = {}
                try:
                    yield_raw = self._q(
                        f"maeGetOverallYield({q(history)}"
                        f"{_session_kw(session)})",
                        request.token,
                        request.timeout,
                    )
                    overall_yield = parse_overall_yield(yield_raw)
                except Exception:
                    overall_yield = {}
                self.middle.run_command(
                    f"rm -f {remote_csv}", timeout=10, token=request.token,
                )
                result = Result(True, steps, None, {
                    "history": history,
                    "tests": parsed["tests"],
                    "points": parsed["points"],
                    "outputs": parsed["outputs"],
                    "overall_spec": overall_spec,
                    "overall_yield": overall_yield,
                    "local_path": str(local_path),
                })
        except Exception as exc:  # noqa: BLE001
            result = Result(False, steps, f"{type(exc).__name__}: {exc}")
        finally:
            self._close_if_created(
                session, created, request.token, request.timeout, steps,
            )
        return result or Result(False, steps, "read_results failed")

    # -- export ----------------------------------------------------------------

    def export(self, request: ExportRequest) -> Result:
        _require_text(request.token, "token")
        _require_text(request.library, "library")
        _require_text(request.cell, "cell")
        _require_text(request.view, "view")
        _require_text(request.kind, "kind")
        _require_timeout(request.timeout)
        if request.kind not in (
            "netlist", "script", "outputs_csv", "snapshot", "screenshot",
        ):
            raise ValueError(
                "kind must be netlist/script/outputs_csv/snapshot/screenshot"
            )

        steps: list[dict[str, Any]] = []
        result: Result | None = None
        session: str | None = None
        created = False
        try:
            if request.kind == "screenshot":
                return self._export_screenshot(request, steps)

            session, created = self._open_session(
                request.library, request.cell, request.view,
                request.token, request.timeout,
            )
            steps.append(_step(
                "open_session", True,
                {"session": session, "created": created},
            ))
            history = request.history or self._latest_history(
                session, request.library, request.cell, request.view,
                request.token, request.timeout,
            )

            if request.kind == "outputs_csv":
                daemon_root = self._role_root(request.token, "daemon")
                remote_csv = posixpath.join(
                    daemon_root,
                    f".maestro-results-{_safe_token(history)}-"
                    f"{uuid.uuid4().hex}.csv",
                )
                test_kw = f" ?testName {q(request.test)}" if request.test else ""
                run = self.middle.execute_skill(
                    f"maeExportOutputView(?session {q(session)}{test_kw} "
                    f"?historyName {q(history)} ?view \"Detail\" "
                    f"?fileName {q(remote_csv)})",
                    timeout=request.timeout,
                    token=request.token,
                )
                steps.append(_step("outputs_csv", run.ok, run))
                if not run.ok:
                    raise RuntimeError("; ".join(run.errors) or "outputs CSV export failed")
                local_path = (
                    Path(request.output_path)
                    if request.output_path
                    else _local_artifact_dir("results")
                    / f"{_safe_token(history)}-{uuid.uuid4().hex}.csv"
                )
                downloaded = self.middle.download_file(
                    remote_csv, local_path,
                    timeout=request.timeout, token=request.token,
                )
                steps.append(_step("download", downloaded.returncode == 0, downloaded))
                if downloaded.returncode != 0:
                    raise RuntimeError(downloaded.stderr or "outputs CSV download failed")
                result = Result(True, steps, None, {
                    "kind": request.kind,
                    "history": history,
                    "local_path": str(local_path),
                })

            elif request.kind == "netlist":
                if not request.test or not request.corner:
                    raise ValueError("test and corner are required for netlist export")
                daemon_root = self._role_root(request.token, "daemon")
                remote_dir = posixpath.join(
                    daemon_root, "maestro", "exports", uuid.uuid4().hex,
                )
                self.middle.run_command(
                    f"mkdir -p {remote_dir}",
                    timeout=request.timeout,
                    token=request.token,
                )
                run = self.middle.execute_skill(
                    f"maeCreateNetlistForCorner({q(request.test)} "
                    f"{q(request.corner)} {q(remote_dir)} {_session_kw(session)})",
                    timeout=request.timeout,
                    token=request.token,
                )
                steps.append(_step("netlist", run.ok, run))
                if not run.ok:
                    raise RuntimeError("; ".join(run.errors) or "netlist export failed")
                local_dir = (
                    Path(request.output_path)
                    if request.output_path
                    else _local_artifact_dir("exports") / "netlist" / uuid.uuid4().hex
                )
                downloaded = self.middle.download_file(
                    remote_dir, local_dir, recursive=True,
                    timeout=request.timeout, token=request.token,
                )
                steps.append(_step("download", downloaded.returncode == 0, downloaded))
                if downloaded.returncode != 0:
                    raise RuntimeError(downloaded.stderr or "netlist download failed")
                result = Result(True, steps, None, {
                    "kind": request.kind,
                    "local_path": str(local_dir),
                    "remote_path": remote_dir,
                })

            elif request.kind == "script":
                daemon_root = self._role_root(request.token, "daemon")
                remote_file = posixpath.join(
                    daemon_root,
                    f".maestro-script-{_safe_token(request.cell)}-"
                    f"{uuid.uuid4().hex}.ocn",
                )
                run = self.middle.execute_skill(
                    f"maeWriteScript({q(remote_file)})",
                    timeout=request.timeout,
                    token=request.token,
                )
                steps.append(_step("script", run.ok, run))
                if not run.ok:
                    raise RuntimeError("; ".join(run.errors) or "script export failed")
                local_path = (
                    Path(request.output_path)
                    if request.output_path
                    else _local_artifact_dir("exports") / Path(remote_file).name
                )
                downloaded = self.middle.download_file(
                    remote_file, local_path,
                    timeout=request.timeout, token=request.token,
                )
                steps.append(_step("download", downloaded.returncode == 0, downloaded))
                if downloaded.returncode != 0:
                    raise RuntimeError(downloaded.stderr or "script download failed")
                result = Result(True, steps, None, {
                    "kind": request.kind,
                    "local_path": str(local_path),
                    "remote_path": remote_file,
                })

            elif request.kind == "snapshot":
                result = self._export_snapshot(
                    request, session, history, steps,
                )
        except Exception as exc:  # noqa: BLE001
            result = Result(False, steps, f"{type(exc).__name__}: {exc}")
        finally:
            self._close_if_created(
                session, created, request.token, request.timeout, steps,
            )
        return result or Result(False, steps, "export failed")

    def _export_snapshot(
        self,
        request: ExportRequest,
        session: str,
        history: str | None,
        steps: list[dict[str, Any]],
    ) -> Result:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        local_root = (
            Path(request.output_path)
            if request.output_path
            else _local_artifact_dir("snapshots")
            / f"{stamp}__{_safe_token(request.library)}__{_safe_token(request.cell)}"
        )
        local_root.mkdir(parents=True, exist_ok=True)

        lib_path = unquote(self._q(
            f"ddGetObj({q(request.library)})~>readPath",
            request.token,
            request.timeout,
        ))
        files: list[str] = []

        remote_sdb = posixpath.join(
            lib_path, request.cell, request.view, f"{request.view}.sdb",
        )
        downloaded = self.middle.download_file(
            remote_sdb, local_root / "maestro.sdb",
            timeout=request.timeout, token=request.token,
        )
        steps.append(_step("snapshot_sdb", downloaded.returncode == 0, downloaded))
        if downloaded.returncode == 0:
            files.append(str(local_root / "maestro.sdb"))

        remote_state = posixpath.join(
            lib_path, request.cell, request.view, "active.state",
        )
        downloaded = self.middle.download_file(
            remote_state, local_root / "active.state",
            timeout=request.timeout, token=request.token,
        )
        steps.append(_step("snapshot_state", downloaded.returncode == 0, downloaded))
        if downloaded.returncode == 0:
            files.append(str(local_root / "active.state"))

        if history:
            results_dir = self._results_dir_for_history(
                session, history, request.token, request.timeout,
            )
            if results_dir:
                results_dir = results_dir.rstrip("/")
                parent_dir = posixpath.dirname(results_dir)
                for suffix in (".log", ".rdb", ".msg.db"):
                    remote_file = posixpath.join(
                        parent_dir, f"{history}{suffix}",
                    )
                    local_file = local_root / f"{history}{suffix}"
                    downloaded = self.middle.download_file(
                        remote_file, local_file,
                        timeout=request.timeout, token=request.token,
                    )
                    steps.append(_step(
                        f"snapshot_history{suffix}",
                        downloaded.returncode == 0,
                        downloaded,
                    ))
                    if downloaded.returncode == 0:
                        files.append(str(local_file))

                remote_history_dir = results_dir
                local_history_dir = local_root / history
                downloaded = self.middle.download_file(
                    remote_history_dir, local_history_dir, recursive=True,
                    timeout=request.timeout, token=request.token,
                )
                steps.append(_step(
                    "snapshot_per_point",
                    downloaded.returncode == 0,
                    downloaded,
                ))
                if downloaded.returncode == 0:
                    files.append(str(local_history_dir))

        return Result(True, steps, None, {
            "kind": "snapshot",
            "history": history,
            "local_path": str(local_root),
            "files": files,
        })

    def _export_screenshot(
        self,
        request: ExportRequest,
        steps: list[dict[str, Any]],
    ) -> Result:
        region: tuple[float, float, float, float] | None = None
        if request.region is not None:
            if len(request.region) != 4:
                return Result(False, steps, "region must be [x1, y1, x2, y2]")
            try:
                x1, y1, x2, y2 = (float(v) for v in request.region)
            except (TypeError, ValueError):
                return Result(False, steps, "region must contain numbers")
            if x1 >= x2 or y1 >= y2:
                return Result(False, steps, "region requires x1 < x2 and y1 < y2")
            region = (x1, y1, x2, y2)

        if request.output_path:
            base = Path(request.output_path)
        else:
            base = (
                _local_artifact_dir("screenshots")
                / f"{_safe_token(request.cell)}-{uuid.uuid4().hex}.png"
            )
        if base.suffix.lower() == ".png":
            local_png = base
        elif base.suffix:
            local_png = base.with_suffix(base.suffix + ".png")
        else:
            local_png = base.with_suffix(".png")

        # hiWindowSaveImage is the only capture path: it is the same primitive
        # as the old generic VirtuosoClient.screenshot and produces a real PNG.
        remote_png: str | None = None
        try:
            gui_root = self._role_root(request.token, "gui")
            remote_png = posixpath.join(
                gui_root, f".maestro-screenshot-{uuid.uuid4().hex}.png",
            )
            if request.window_id is not None:
                window_expr = (
                    "let((found) foreach(win hiGetWindowList() "
                    f"when(win~>windowNum == {int(request.window_id)} "
                    "found = win)) found)"
                )
            else:
                window_expr = (
                    "let((found title) "
                    "foreach(win hiGetWindowList() "
                    "  title = hiGetWindowName(win) "
                    "  when(win~>cellView "
                    f"    && win~>cellView~>libName == {q(request.library)} "
                    f"    && win~>cellView~>cellName == {q(request.cell)} "
                    f"    && win~>cellView~>viewName == {q(request.view)} "
                    "    found = win) "
                    "  when(!found && stringp(title) "
                    "    && index(title \"ADE \") "
                    f"    && index(title {q(request.library)}) "
                    f"    && index(title {q(request.cell)}) "
                    f"    && index(title {q(request.view)}) "
                    "    found = win)) "
                    "found)"
                )
            zoom_step = ""
            if region is not None:
                rx1, ry1, rx2, ry2 = region
                zoom_step = (
                    f"hiZoomIn(vbW list({rx1:g}:{ry1:g} {rx2:g}:{ry2:g})) "
                )
            top = "t" if request.toplevel else "nil"
            skill = (
                "let((vbW vbRc) "
                f"vbW = {window_expr} "
                "unless(vbW error(\"window not found\")) "
                "hiDeiconifyWindow(vbW) "
                "hiRaiseWindow(vbW) "
                f"{zoom_step}"
                f"vbRc = hiWindowSaveImage(?target vbW ?path {q(remote_png)} "
                f"?format \"png\" ?toplevel {top}) "
                "if(vbRc \"saved\" \"capture-failed\"))"
            )
            capture = self.middle.execute_skill(
                skill, timeout=request.timeout, token=request.token,
            )
            steps.append(_step("hiWindowSaveImage", capture.ok, capture))
            if not capture.ok:
                return Result(
                    False, steps,
                    "; ".join(capture.errors) or "hiWindowSaveImage failed",
                )
            output = unquote(capture.output or "")
            if output in ("", "nil", "capture-failed"):
                return Result(
                    False, steps,
                    f"hiWindowSaveImage failed: {output or 'nil'}",
                )
            downloaded = self.middle.download_file(
                remote_png, local_png,
                timeout=request.timeout, token=request.token,
            )
            steps.append(_step(
                "download_png", downloaded.returncode == 0, downloaded,
            ))
            if downloaded.returncode != 0:
                return Result(
                    False, steps,
                    downloaded.stderr or "screenshot download failed",
                )
            if not local_png.is_file() or local_png.stat().st_size <= 0:
                return Result(
                    False, steps, "screenshot file is missing or empty",
                )
            return Result(True, steps, None, {
                "kind": "screenshot",
                "method": "hiWindowSaveImage",
                "format": "png",
                "local_path": str(local_png),
                "window_id": request.window_id,
                "region": list(region) if region is not None else None,
                "toplevel": request.toplevel,
            })
        except Exception as exc:  # noqa: BLE001 - business failure
            steps.append(_step("hiWindowSaveImage", False, str(exc)))
            return Result(False, steps, f"{type(exc).__name__}: {exc}")
        finally:
            if remote_png is not None:
                try:
                    self.middle.run_command(
                        f"rm -f {remote_png}", timeout=10, token=request.token,
                    )
                except Exception:
                    pass

    # -- read_history ----------------------------------------------------------

    def read_history(self, request: ReadHistoryRequest) -> Result:
        _require_text(request.token, "token")
        _require_text(request.library, "library")
        _require_text(request.cell, "cell")
        _require_text(request.view, "view")
        _require_timeout(request.timeout)
        if request.history is not None:
            _require_history_name(request.history)

        steps: list[dict[str, Any]] = []
        result: Result | None = None
        session: str | None = None
        created = False
        try:
            session, created = self._open_session(
                request.library, request.cell, request.view,
                request.token, request.timeout,
            )
            steps.append(_step(
                "open_session", True,
                {"session": session, "created": created},
            ))
            names = self._history_names(
                session, request.library, request.cell, request.view,
                request.token, request.timeout,
            )
            current = self._current_history(session, request.token, request.timeout)
            steps.append(_step("histories", True, names))

            if request.history is None:
                histories: list[dict[str, Any]] = []
                for name in names:
                    lock_flag = self._history_lock_flag(
                        session, name, request.token, request.timeout,
                    )
                    status = self._run_status(
                        session, name, request.token, request.timeout,
                    )
                    histories.append({
                        "name": name,
                        "status": status["status"],
                        "points_done": status["done"],
                        "points_total": status["total"],
                        "lock_flag": lock_flag,
                        "current": name == current,
                    })
                result = Result(True, steps, None, {
                    "history": None,
                    "current_history": current,
                    "histories": histories,
                })
            else:
                name = request.history
                lock_flag = self._history_lock_flag(
                    session, name, request.token, request.timeout,
                )
                points = self._run_status(
                    session, name, request.token, request.timeout,
                )
                tests = self._run_status(
                    session, name, request.token, request.timeout,
                    option="tests",
                )
                corners = self._run_status(
                    session, name, request.token, request.timeout,
                    option="corners",
                )
                results_dir = self._results_dir_for_history(
                    session, name, request.token, request.timeout,
                )
                overwrite_target = None
                try:
                    raw = self._q(
                        "axlGetOverwriteHistoryName("
                        f"axlGetActiveSetup({self._main_setup_db_expr(session)}))",
                        request.token,
                        request.timeout,
                    )
                    overwrite_target = unquote(raw)
                    if overwrite_target in ("", "nil"):
                        overwrite_target = None
                except Exception:
                    overwrite_target = None
                result = Result(True, steps, None, {
                    "history": {
                        "name": name,
                        "status": points["status"],
                        "points_done": points["done"],
                        "points_total": points["total"],
                        "tests_done": tests["done"],
                        "tests_total": tests["total"],
                        "corners_done": corners["done"],
                        "corners_total": corners["total"],
                        "lock_flag": lock_flag,
                        "results_dir": results_dir,
                        "overwrite_target": overwrite_target,
                        "current": name == current,
                    },
                    "current_history": current,
                })
        except Exception as exc:  # noqa: BLE001
            result = Result(False, steps, f"{type(exc).__name__}: {exc}")
        finally:
            self._close_if_created(
                session, created, request.token, request.timeout, steps,
            )
        return result or Result(False, steps, "read_history failed")

    # -- write_history ---------------------------------------------------------

    def write_history(self, request: WriteHistoryRequest) -> Result:
        _require_text(request.token, "token")
        _require_text(request.library, "library")
        _require_text(request.cell, "cell")
        _require_text(request.view, "view")
        _require_timeout(request.timeout)
        if not isinstance(request.commands, list) or not request.commands:
            raise ValueError("commands must be a non-empty list")

        steps: list[dict[str, Any]] = []
        result: Result | None = None
        session: str | None = None
        created = False
        try:
            session, created = self._open_session(
                request.library, request.cell, request.view,
                request.token, request.timeout,
            )
            steps.append(_step(
                "open_session", True,
                {"session": session, "created": created},
            ))
            if not self._ensure_session_editable(
                session, request.token, request.timeout, steps,
            ):
                result = Result(False, steps, "session is not editable")
                raise RuntimeError("session is not editable")
            for index, command in enumerate(request.commands):
                op = command.get("op") if isinstance(command, dict) else None
                try:
                    exprs = self._command_exprs(command, session)
                except Exception as exc:  # noqa: BLE001
                    result = Result(
                        False, steps,
                        f"command {index} invalid: {exc}",
                    )
                    break
                history = command.get("history")
                if op in ("delete", "delete_results", "rename", "lock", "unlock"):
                    try:
                        lock_flag = self._history_lock_flag(
                            session, history, request.token, request.timeout,
                        )
                    except Exception:
                        lock_flag = None
                    if op in ("delete", "delete_results", "rename") and lock_flag:
                        result = Result(
                            False, steps,
                            f"history {history!r} is locked (flag={lock_flag})",
                        )
                        break
                failed = False
                for expr in exprs:
                    run = self.middle.execute_skill(
                        expr, timeout=request.timeout, token=request.token,
                    )
                    steps.append(_step(f"history:{op}", run.ok, run))
                    if not run.ok:
                        result = Result(
                            False, steps,
                            "; ".join(run.errors) or f"history {op} failed",
                        )
                        failed = True
                        break
                if failed:
                    break
                # Persist + verify every mutation before moving to the next.
                try:
                    if op == "delete":
                        saved = self._save_setup(
                            request.library, request.cell, request.view,
                            session, request.token, request.timeout,
                        )
                        steps.append(_step("save_setup", True, saved))
                        if self._history_in_sdb(
                            session, history, request.token, request.timeout,
                        ):
                            explorer_expr = (
                                f"maeDeleteExplorerHistory({q(session)} {q(history)})"
                            )
                            explorer = self.middle.execute_skill(
                                explorer_expr,
                                timeout=request.timeout,
                                token=request.token,
                            )
                            steps.append(_step("delete_explorer", explorer.ok, explorer))
                            saved = self._save_setup(
                                request.library, request.cell, request.view,
                                session, request.token, request.timeout,
                            )
                            steps.append(_step("save_setup_retry", True, saved))
                        if self._history_in_sdb(
                            session, history, request.token, request.timeout,
                        ):
                            raise RuntimeError(f"history {history!r} still exists")
                    elif op == "rename":
                        new_name = command.get("new_name")
                        saved = self._save_setup(
                            request.library, request.cell, request.view,
                            session, request.token, request.timeout,
                        )
                        steps.append(_step("save_setup", True, saved))
                        if not self._history_in_sdb(
                            session, new_name, request.token, request.timeout,
                        ):
                            raise RuntimeError(
                                f"renamed history {new_name!r} is not visible"
                            )
                    else:
                        saved = self._save_setup(
                            request.library, request.cell, request.view,
                            session, request.token, request.timeout,
                        )
                        steps.append(_step("save_setup", True, saved))
                        if op in ("lock", "unlock") and history:
                            flag = self._history_lock_flag(
                                session, history, request.token, request.timeout,
                            )
                            if op == "lock" and flag != 1:
                                raise RuntimeError(
                                    f"lock verification returned flag={flag}"
                                )
                            if op == "unlock" and flag == 1:
                                raise RuntimeError(
                                    "unlock verification still reports user lock"
                                )
                except Exception as exc:  # noqa: BLE001
                    result = Result(
                        False, steps,
                        f"history {op} verification failed: {exc}",
                    )
                    break
            else:
                if result is None:
                    result = Result(
                        True, steps, None,
                        {"applied": len(request.commands), "session": session},
                    )
        except Exception as exc:  # noqa: BLE001
            result = Result(False, steps, f"{type(exc).__name__}: {exc}")
        finally:
            self._close_if_created(
                session, created, request.token, request.timeout, steps,
            )
        return result or Result(False, steps, "write_history failed")

    # -- GUI open / close ------------------------------------------------------

    def open_gui(self, request: OpenGuiRequest) -> Result:
        _require_text(request.token, "token")
        _require_text(request.library, "library")
        _require_text(request.cell, "cell")
        _require_text(request.view, "view")
        _require_timeout(request.timeout)
        if request.history is not None:
            _require_history_name(request.history)

        steps: list[dict[str, Any]] = []
        try:
            window = self._ensure_gui_session(
                request.library, request.cell, request.view,
                request.token, request.timeout,
            )
            steps.append(_step("ensure_gui_session", True, window))
            if request.history:
                run = self.middle.execute_skill(
                    f"maeRestoreHistory({q(request.history)}"
                    f"{_session_kw(window['session'])})",
                    timeout=request.timeout,
                    token=request.token,
                )
                steps.append(_step("restore_history", run.ok, run))
                if not run.ok:
                    return Result(False, steps, "; ".join(run.errors))
                self._save_setup(
                    request.library, request.cell, request.view,
                    window["session"], request.token, request.timeout,
                )
            return Result(True, steps, None, {
                "session": window["session"],
                "window": window["window"],
                "title": window["title"],
                "mode": "editing",
            })
        except Exception as exc:  # noqa: BLE001
            return Result(False, steps, f"{type(exc).__name__}: {exc}")

    def close_gui(self, request: CloseGuiRequest) -> Result:
        _require_text(request.token, "token")
        _require_text(request.library, "library")
        _require_text(request.cell, "cell")
        _require_text(request.view, "view")
        _require_timeout(request.timeout)

        steps: list[dict[str, Any]] = []
        try:
            window = self._find_gui_session(
                request.library, request.cell, request.view,
                request.token, request.timeout,
            )
            if window is None:
                return Result(True, steps, None, {
                    "session": None,
                    "closed": False,
                    "note": "no GUI session was open",
                })
            saved = self._save_setup(
                request.library, request.cell, request.view,
                window["session"], request.token, request.timeout,
            )
            steps.append(_step("save_setup", True, saved))
            close_expr = (
                "let((w) "
                "foreach(win hiGetWindowList() "
                f"  when(win~>windowNum == {window['window']} w = win)) "
                "when(w hiCloseWindow(w)))"
            )
            closed = self.middle.execute_skill(
                close_expr, timeout=request.timeout, token=request.token,
            )
            steps.append(_step("close_window", closed.ok, closed))
            session_closed = self.middle.execute_skill(
                f"maeCloseSession(?session {q(window['session'])} ?forceClose t)",
                timeout=request.timeout,
                token=request.token,
            )
            steps.append(_step("close_session", session_closed.ok, session_closed))
            purge = self._purge_cellview(
                request.library, request.cell, request.view,
                request.token, request.timeout,
            )
            steps.append(_step("purge", purge.ok, purge))
            remaining = self._find_gui_session(
                request.library, request.cell, request.view,
                request.token, request.timeout,
            )
            if remaining is not None:
                return Result(False, steps, "GUI session is still open")
            return Result(True, steps, None, {
                "session": window["session"],
                "window": window["window"],
                "closed": True,
            })
        except Exception as exc:  # noqa: BLE001
            return Result(False, steps, f"{type(exc).__name__}: {exc}")

    # -- run -------------------------------------------------------------------

    def _dismiss_update_dialogs(
        self,
        token: str,
        timeout: int | float | None,
    ) -> list[dict[str, Any]]:
        """Dismiss ADE ``Update and Run`` modals through the GUI channel.

        ``maeRunSimulation`` can block on a modal dialog before it returns.
        While the Skill channel is blocked, the GUI interface is still
        usable; pressing Enter accepts the default "update and run" action.
        """
        try:
            gui = gui_pkg.Package(self.middle)
            listed = gui.list_windows(gui_pkg.ListWindowsRequest(
                token=token, timeout=timeout or 10,
            ))
        except Exception:
            return []
        if not listed.ok:
            return []
        dismissed: list[dict[str, Any]] = []
        for window in listed.windows:
            title = str(window.get("title", ""))
            # Only the known safe "Update and Run" modal is handled here.
            # Other modal dialogs must not be dismissed with an arbitrary key.
            if "Update and Run" not in title:
                continue
            try:
                sent = gui.send_key(gui_pkg.SendKeyRequest(
                    token=token,
                    window_id=window["window_id"],
                    key="enter",
                    timeout=timeout or 10,
                ))
                dismissed.append({
                    "window_id": window["window_id"],
                    "title": title,
                    "ok": sent.ok,
                })
            except Exception as exc:  # noqa: BLE001 - watchdog is best-effort
                dismissed.append({
                    "window_id": window["window_id"],
                    "title": title,
                    "ok": False,
                    "error": str(exc),
                })
        return dismissed

    def _start_simulation_with_watchdog(
        self,
        session: str,
        token: str,
        timeout: int | float | None,
    ) -> tuple[VirtuosoResult | None, list[dict[str, Any]], str | None, int]:
        """Start ``maeRunSimulation``; only touch X11 if it is actually blocked.

        ``maeRunSimulation`` returns quickly when no modal is displayed.  The
        watchdog therefore waits a short grace period first, and only performs
        bounded window checks if the call is still pending.  If no known
        ``Update and Run`` dialog is found, it backs off completely instead of
        polling X11 for the whole simulation.
        """
        box: dict[str, Any] = {}

        def worker() -> None:
            try:
                box["result"] = self.middle.execute_skill(
                    f"maeRunSimulation({_session_kw(session)})",
                    timeout=timeout or 180,
                    token=token,
                )
            except Exception as exc:  # noqa: BLE001
                box["error"] = exc

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        started = time.monotonic()
        deadline = started + (float(timeout) if timeout else 180.0)
        dismissed: list[dict[str, Any]] = []
        window_checks = 0
        saw_dialog = False
        tail_deadline: float | None = None

        # Fast path: no dialog -> no X11 calls at all.
        grace = min(1.5, max(0.0, deadline - started))
        while thread.is_alive() and time.monotonic() - started < grace:
            time.sleep(0.1)

        while thread.is_alive() and time.monotonic() < deadline:
            now = time.monotonic()
            should_check = window_checks == 0
            if saw_dialog and tail_deadline is not None:
                should_check = now < tail_deadline
            if not should_check:
                break
            found = self._dismiss_update_dialogs(token, 10)
            window_checks += 1
            if found:
                saw_dialog = True
                dismissed.extend(found)
                tail_deadline = now + 10.0
                time.sleep(0.5)
                continue
            if not saw_dialog:
                # No known modal: stop touching X11 and let the run proceed.
                break
            if tail_deadline is not None and now >= tail_deadline:
                break
            time.sleep(0.5)
        thread.join(timeout=1.0)
        if thread.is_alive():
            return (
                None,
                dismissed,
                "maeRunSimulation did not return before timeout",
                window_checks,
            )
        if "error" in box:
            return None, dismissed, str(box["error"]), window_checks
        return box.get("result"), dismissed, None, window_checks

    def _diagnose_run_failure(
        self,
        token: str,
        timeout: int | float | None,
    ) -> dict[str, Any]:
        info: dict[str, Any] = {}
        try:
            info["current_form"] = unquote(self._q(
                "let((f) f = hiGetCurrentForm() when(f f~>name))",
                token, timeout,
            ))
        except Exception:
            info["current_form"] = None
        try:
            info["sessions"] = parse_skill_str_leaves(
                self._q("maeGetSessions()", token, timeout)
            )
        except Exception:
            info["sessions"] = []
        return info

    def run(self, request: RunRequest) -> Result:
        _require_text(request.token, "token")
        _require_text(request.library, "library")
        _require_text(request.cell, "cell")
        _require_text(request.view, "view")
        _require_timeout(request.timeout)
        if request.history is not None:
            _require_history_name(request.history)
        if request.poll_interval <= 0:
            raise ValueError("poll_interval must be positive")

        steps: list[dict[str, Any]] = []
        try:
            window = self._ensure_gui_session(
                request.library, request.cell, request.view,
                request.token, request.timeout,
            )
            session = window["session"]
            steps.append(_step("ensure_gui_session", True, window))
            mode = self.middle.execute_skill(
                f'maeSetJobControlMode("ICRP"{_session_kw(session)})',
                timeout=request.timeout,
                token=request.token,
            )
            steps.append(_step("job_control_mode", mode.ok, mode))
            if not mode.ok:
                return Result(False, steps, "; ".join(mode.errors))
            if request.history:
                overwrite = self.middle.execute_skill(
                    "let((sdb setup) "
                    f"sdb = axlGetMainSetupDB({q(session)}) "
                    "setup = axlGetActiveSetup(sdb) "
                    "axlSetOverwriteHistory(setup t) "
                    f"axlSetOverwriteHistoryName(setup {q(request.history)}))",
                    timeout=request.timeout,
                    token=request.token,
                )
                steps.append(_step("overwrite_target", overwrite.ok, overwrite))
                if not overwrite.ok:
                    return Result(False, steps, "; ".join(overwrite.errors))

            started, dismissed, start_error, window_checks = (
                self._start_simulation_with_watchdog(
                    session, request.token, request.timeout,
                )
            )
            if dismissed or window_checks:
                steps.append(_step("dialog_watchdog", True, {
                    "window_checks": window_checks,
                    "dismissed": dismissed,
                }))
            history = unquote(started.output or "") if started else ""
            if started is not None:
                steps.append(_step("run", started.ok, started))
            else:
                steps.append(_step("run", False, start_error))
            if started is None or not started.ok or not history or history == "nil":
                diagnosis = self._diagnose_run_failure(
                    request.token, request.timeout,
                )
                steps.append(_step("diagnosis", False, diagnosis))
                try:
                    self.middle.execute_skill(
                        "let((f) f = hiGetCurrentForm() "
                        "when(f hiFormDone(f)))",
                        timeout=request.timeout,
                        token=request.token,
                    )
                    retry, retry_dismissed, retry_error, retry_checks = (
                        self._start_simulation_with_watchdog(
                            session, request.token, request.timeout,
                        )
                    )
                    if retry_dismissed or retry_checks:
                        steps.append(_step(
                            "dialog_watchdog_retry", True, {
                                "window_checks": retry_checks,
                                "dismissed": retry_dismissed,
                            },
                        ))
                    retry_history = unquote(retry.output or "") if retry else ""
                    steps.append(_step(
                        "run_retry",
                        bool(retry and retry.ok),
                        retry if retry is not None else retry_error,
                    ))
                    if retry is not None and retry.ok and retry_history and retry_history != "nil":
                        history = retry_history
                    else:
                        return Result(
                            False, steps,
                            "maeRunSimulation returned nil; diagnosis: "
                            f"{diagnosis}",
                        )
                except Exception as exc:  # noqa: BLE001
                    return Result(
                        False, steps,
                        f"maeRunSimulation failed: {exc}; diagnosis: {diagnosis}",
                    )

            if not request.blocking:
                return Result(True, steps, None, {
                    "history": history,
                    "status": "started",
                    "session": session,
                })

            deadline = time.monotonic() + (request.timeout or 3600)
            last: dict[str, Any] = {}
            last_status: str | None = None
            while time.monotonic() < deadline:
                try:
                    last = self._run_status(
                        session, history, request.token, request.timeout,
                    )
                except Exception as exc:  # noqa: BLE001
                    last = {"status": "unknown", "error": str(exc)}
                if last.get("status") != last_status:
                    steps.append(_step("poll", True, last))
                    last_status = str(last.get("status"))
                if last.get("status") in ("done", "failed"):
                    return Result(
                        last.get("status") != "failed",
                        steps,
                        None if last.get("status") != "failed" else "simulation failed",
                        {
                            "history": history,
                            "status": last.get("status"),
                            "session": session,
                            "progress": last,
                        },
                    )
                time.sleep(request.poll_interval)
            return Result(False, steps, "simulation did not finish before timeout", {
                "history": history,
                "status": "timeout",
                "session": session,
                "progress": last,
            })
        except Exception as exc:  # noqa: BLE001
            return Result(False, steps, f"{type(exc).__name__}: {exc}")

    # -- waveform GUI ----------------------------------------------------------

    def open_waveform_gui(self, request: OpenWaveformRequest) -> Result:
        _require_text(request.token, "token")
        _require_text(request.library, "library")
        _require_text(request.cell, "cell")
        _require_text(request.view, "view")
        _require_history_name(request.history)
        _require_timeout(request.timeout)
        if not isinstance(request.signals, list) or not request.signals:
            raise ValueError("signals must be a non-empty list")
        signals = [str(item) for item in request.signals]
        steps: list[dict[str, Any]] = []
        session: str | None = None
        session_created = False
        try:
            before_sessions = set(self._session_list(
                request.token, request.timeout,
            ))
            session_raw = self._q(
                f"maeOpenSetup({q(request.library)} {q(request.cell)} "
                f"{q(request.view)} ?mode \"r\")",
                request.token,
                request.timeout,
            )
            session = unquote(session_raw)
            if not session or session in ("nil", "t"):
                raise RuntimeError("maeOpenSetup read-only session failed")
            session_created = session not in before_sessions
            history_dir = self._results_dir_for_history(
                session, request.history, request.token, request.timeout,
            )
            if not history_dir:
                raise RuntimeError("could not determine results directory")
            psf_dir = self._find_psf_dir(
                history_dir, request.test, request.analysis or request.test,
                request.token, request.timeout,
            )
            if not psf_dir:
                raise RuntimeError(f"no PSF logFile found under {history_dir}")
            signal_blocks = []
            for signal in signals:
                fallback = ""
                if request.test:
                    fallback = (
                        "unless(w "
                        f"  r = errset(maeGetOutputValue({q(signal)} "
                        f"{q(request.test)}) nil) "
                        "  w = if(r car(r) nil)) "
                    )
                signal_blocks.append(
                    "let((w r) "
                    "w = nil "
                    f"r = errset(v({q(signal)}) nil) "
                    "w = if(r car(r) nil) "
                    + fallback
                    + f"unless(w error(strcat(\"missing waveform: \" "
                    f"{q(signal)}))) "
                    "waves = append(waves list(w)))"
                )
            skill = (
                "let((win waves vbPlotted) "
                f"openResults({q(psf_dir)}) "
                + (
                    f"selectResults({q(request.analysis)}) "
                    if request.analysis else ""
                )
                +
                "waves = nil "
                + " ".join(signal_blocks)
                + " win = car(errset(awvCreatePlotWindow() nil)) "
                "unless(win error(\"create waveform window failed\")) "
                "vbPlotted = errset(awvPlotWaveform(win waves ?expr "
                f"list({', '.join(q(s) for s in signals)})) "
                "nil) "
                "unless(vbPlotted && car(vbPlotted) "
                "progn(when(win hiCloseWindow(win)) "
                "error(\"plot waveform failed\"))) "
                "list(\"opened\" win))"
            )
            raw = self._q(skill, request.token, request.timeout or 60)
            parsed = parse_sexpr(raw.strip())
            if not isinstance(parsed, list) or len(parsed) < 2:
                raise RuntimeError(f"unexpected waveform result: {raw}")
            steps.append(_step("open_waveform", True, raw))
            return Result(True, steps, None, {
                "session": session,
                "session_created": session_created,
                "window": parsed[1],
                "signals": signals,
            })
        except Exception as exc:  # noqa: BLE001
            return Result(False, steps, f"{type(exc).__name__}: {exc}")

    def close_waveform_gui(self, request: CloseWaveformRequest) -> Result:
        _require_text(request.token, "token")
        _require_timeout(request.timeout)
        if not request.session and not request.window:
            raise ValueError("session or window is required")
        window_ref = "nil"
        window_num: int | None = None
        if request.window:
            text = str(request.window).strip()
            match = re.search(r"(\d+)", text)
            if match:
                window_num = int(match.group(1))
                window_ref = f"window({window_num})"
        session_ref = q(request.session) if request.session else "nil"
        skill = (
            "let((win sess) "
            f"win = {window_ref} "
            f"sess = {session_ref} "
            "when(win hiCloseWindow(win)) "
            "when(sess maeCloseSession(?session sess ?forceClose t)) "
            "list(\"closed\" sess win))"
        )
        steps: list[dict[str, Any]] = []
        try:
            raw = self._q(skill, request.token, request.timeout)
            steps.append(_step("close_waveform", True, raw))
            session_check = (
                f"member({q(request.session)} maeGetSessions())"
                if request.session else "nil"
            )
            window_check = (
                "let((found) found = nil "
                "foreach(w hiGetWindowList() "
                f"  when(w~>windowNum == {window_num} found = t)) found)"
                if window_num is not None else "nil"
            )
            verify_raw = self._q(
                f"list({session_check} {window_check})",
                request.token,
                request.timeout,
            )
            verified = parse_sexpr(verify_raw.strip())
            still_session = bool(
                isinstance(verified, list) and len(verified) > 0 and verified[0]
            )
            still_window = bool(
                isinstance(verified, list) and len(verified) > 1 and verified[1]
            )
            steps.append(_step("verify", not (still_session or still_window), {
                "session_present": still_session,
                "window_present": still_window,
            }))
            if still_session or still_window:
                return Result(
                    False, steps,
                    "waveform window/session is still present after close",
                )
            return Result(True, steps, None, {
                "session": request.session,
                "window": request.window,
                "closed": True,
            })
        except Exception as exc:  # noqa: BLE001
            return Result(False, steps, f"{type(exc).__name__}: {exc}")


#: spec 上层 §4.2: package-level self-description
OPERATIONS = (
    ("virtuoso.maestro.read_config", "read_config", ReadConfigRequest, Result),
    ("virtuoso.maestro.write", "write", WriteRequest, Result),
    ("virtuoso.maestro.read_results", "read_results", ReadResultsRequest, Result),
    ("virtuoso.maestro.export", "export", ExportRequest, Result),
    ("virtuoso.maestro.read_history", "read_history", ReadHistoryRequest, Result),
    ("virtuoso.maestro.write_history", "write_history", WriteHistoryRequest, Result),
    ("virtuoso.maestro.open_gui", "open_gui", OpenGuiRequest, Result),
    ("virtuoso.maestro.close_gui", "close_gui", CloseGuiRequest, Result),
    ("virtuoso.maestro.run", "run", RunRequest, Result),
    ("virtuoso.maestro.open_waveform_gui", "open_waveform_gui",
     OpenWaveformRequest, Result),
    ("virtuoso.maestro.close_waveform_gui", "close_waveform_gui",
     CloseWaveformRequest, Result),
)

OPERATION_NAMES = tuple(operation for operation, *_ in OPERATIONS)

__all__ = [
    "CloseGuiRequest",
    "CloseWaveformRequest",
    "ExportRequest",
    "OpenGuiRequest",
    "OpenWaveformRequest",
    "OPERATIONS",
    "OPERATION_NAMES",
    "Package",
    "ReadConfigRequest",
    "ReadHistoryRequest",
    "ReadResultsRequest",
    "Result",
    "RunRequest",
    "WriteHistoryRequest",
    "WriteRequest",
]
