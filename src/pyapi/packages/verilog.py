"""``verilog`` business package: structural Verilog authoring/import/export.

Spec: ``spec/design-concepts/上层/8-verilog.md`` (Draft v6).

The package reads/writes Verilog *text views* (``text.v``, file ``verilog.v``)
like the veriloga package, and additionally orchestrates ``ihdl`` import and
``oa2verilog`` export for structural netlists.
"""
from __future__ import annotations

import hashlib
import posixpath
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common.paths import artifact_dir
from pyapi.models import Middle, VirtuosoResult
from pyapi.packages import basic


VIEW_TYPE = "text.v"
MAIN_FILE = "verilog.v"
MASTER_TAG = "-- Master.tag File, Rev:1.0\n"
_STRUCTURAL_VIEWS = (1, 2, 4, 5, 6)


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
    view: str = "verilog"
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
    view: str = "verilog"
    view_type: str = VIEW_TYPE
    timeout: int | None = None


@dataclass(frozen=True)
class ImportRequest:
    token: str
    library: str
    cell: str
    file_path: str
    file_is_local: bool = True
    ref_libs: list[str] = field(default_factory=list)
    structural_views: int = 4
    schematic_view: str = "schematic"
    functional_view: str = "functional"
    symbol_view: str = "symbol"
    power_net: str = "VDD"
    ground_net: str = "VSS"
    import_lib_cells: int = 0
    overwrite: bool = False
    timeout: float | None = None


@dataclass(frozen=True)
class ExportRequest:
    token: str
    library: str
    cell: str
    view: str = "schematic"
    output_path: str | None = None
    recursive: bool = False
    timeout: float | None = None


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
        path = artifact_dir() / "verilog"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _work_dir(self, request: Any) -> str:
        raw = self._q("getWorkingDir()", request.token, request.timeout).strip()
        work_dir = raw.strip('"').replace('\\"', '"').replace("\\\\", "\\")
        if not work_dir:
            raise RuntimeError("could not determine Virtuoso working directory")
        return work_dir

    def _install_dir(self, request: Any) -> str:
        raw = self._q("car(getInstallPath())", request.token, request.timeout).strip()
        parsed = basic.parse_sexpr(raw)
        if isinstance(parsed, list):
            parsed = parsed[0] if parsed else None
        install = (str(parsed).strip() if parsed else "") or raw.strip('"')
        if not install:
            raise RuntimeError("could not determine Cadence install directory")
        return install

    def _cadence_root(self, request: Any) -> str:
        """Install dir is ``<root>/tools.lnx86/dfII``; two dirname hops give
        the Cadence root used to build library search paths."""
        return posixpath.dirname(posixpath.dirname(self._install_dir(request)))

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
        with open(local, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        result = self.middle.upload_file(local, remote, timeout=request.timeout, token=request.token)
        if result.returncode != 0:
            raise RuntimeError(result.stderr or f"upload failed: {remote}")

    def _check_lock(self, view_dir: str, request: Any) -> None:
        result = self.middle.run_command(
            f"if ls -A {shlex.quote(view_dir)}/*.cdslck >/dev/null 2>&1; then echo LOCK; else echo OK; fi",
            timeout=60, token=request.token,
        )
        if result.returncode != 0 or (result.stdout or "").strip() == "LOCK":
            raise RuntimeError("view is locked by an open editor; close it first")

    # -- read -------------------------------------------------------------------

    def read(self, request: ReadRequest) -> Result:
        _require_text(request.token, "token")
        _require_timeout(request.timeout)
        if bool(request.library and request.cell) == bool(request.file_path):
            raise ValueError("provide either library+cell or file_path, not both/none")
        valid_focus = {"source", "views", "diagnostics"}
        if request.focus is not None:
            if not isinstance(request.focus, list) or not request.focus:
                raise ValueError("focus must be a non-empty list")
            unknown = set(request.focus) - valid_focus
            if unknown:
                raise ValueError(f"unknown focus values: {sorted(unknown)}")
        steps: list[dict[str, Any]] = []
        try:
            if request.file_path:
                path = Path(request.file_path)
                if request.file_is_local:
                    if not path.is_file():
                        raise RuntimeError(f"file not found: {path}")
                    text = path.read_text(encoding="utf-8", errors="replace")
                else:
                    text = self._read_remote(str(path), request)
                source_path = str(path)
                views: list[dict[str, Any]] = []
                diagnostics: dict[str, Any] = {}
            else:
                view_dir = self._view_dir(request)
                remote = self._remote_file(view_dir)
                text = self._read_remote(remote, request)
                source_path = remote
                views = self._read_views(request)
                diagnostics = self._read_diagnostics(request)
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
            if "views" in focus:
                value["views"] = views
            if "diagnostics" in focus:
                value["diagnostics"] = diagnostics
            return Result(True, steps, None, value)
        except Exception as exc:  # noqa: BLE001
            return Result(False, steps, f"{type(exc).__name__}: {exc}")

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
                if isinstance(file_entry, list) and len(file_entry) >= 4:
                    result.append({
                        "view": str(file_entry[0]),
                        "view_type": None if file_entry[1] is None else str(file_entry[1]),
                        "data_type": None if file_entry[2] is None else str(file_entry[2]),
                        "file": None if file_entry[3] is None else str(file_entry[3]),
                    })
        return result

    def _read_diagnostics(self, request: Any) -> dict[str, Any]:
        path = posixpath.join(
            self._work_dir(request), ".vb_verilog",
            f"{_safe_name(request.library)}__{_safe_name(request.cell)}",
            "verilogIn.batch.log",
        )
        try:
            text = self._read_remote(path, request)
        except Exception:  # noqa: BLE001
            return {"log_path": path, "status": "none", "error_count": 0, "errors": []}
        errors = [line.strip() for line in text.splitlines() if "ERROR (VERILOGIN" in line]
        return {
            "log_path": path,
            "status": "failed" if errors else "ok",
            "error_count": len(errors),
            "errors": errors[:20],
        }

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
            f"// Verilog for {request.library}, {request.cell}, {request.view}\n"
            "\n"
            f"module {_safe_name(request.cell)};\n"
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
                raise RuntimeError(f"sha256 mismatch: expected {expected}, actual {actual}")
        self._write_remote(remote, text, request)

    def _patch_source(self, remote: str, command: dict[str, Any], request: Any) -> None:
        edits = command.get("edits")
        if not isinstance(edits, list) or not edits:
            raise ValueError("command.edits must be a non-empty list")
        current = self._read_remote(remote, request)
        for edit in edits:
            if not isinstance(edit, dict):
                raise ValueError("each edit must be an object")
            if "old_text" in edit and "new_text" in edit:
                old = edit["old_text"]
                new = edit["new_text"]
                if not isinstance(old, str) or not isinstance(new, str):
                    raise ValueError("edit.old_text/new_text must be strings")
                count = current.count(old)
                if count == 0:
                    raise RuntimeError(f"old_text not found: {old!r}")
                if count != 1 and not command.get("all"):
                    raise RuntimeError(f"old_text matches {count} places, all=false")
                current = current.replace(old, new)
            elif {"start_line", "end_line", "new_text"} <= set(edit):
                start = int(edit["start_line"])
                end = int(edit["end_line"])
                current_lines = current.splitlines()
                if start < 1 or end < start or end > len(current_lines):
                    raise RuntimeError(
                        f"invalid line range {start}:{end} (file has {len(current_lines)} lines)"
                    )
                replacement = edit["new_text"]
                if not isinstance(replacement, str):
                    raise ValueError("edit.new_text must be a string")
                current_lines[start - 1:end] = replacement.splitlines()
                current = "\n".join(current_lines) + "\n"
            else:
                raise ValueError("edit must be old_text/new_text or start_line/end_line/new_text")
        self._write_remote(remote, current, request)

    # -- import -----------------------------------------------------------------

    def import_verilog(self, request: ImportRequest) -> Result:
        _require_text(request.token, "token")
        _require_text(request.library, "library")
        _require_text(request.cell, "cell")
        _require_text(request.file_path, "file_path")
        _require_bool(request.file_is_local, "file_is_local")
        _require_bool(request.overwrite, "overwrite")
        _require_timeout(request.timeout)
        if request.structural_views not in _STRUCTURAL_VIEWS:
            raise ValueError(f"structural_views must be one of {_STRUCTURAL_VIEWS}")
        steps: list[dict[str, Any]] = []
        try:
            timeout = float(request.timeout or 300)
            for name in [request.library, *request.ref_libs]:
                exists = self._q(
                    f"if(ddGetObj({basic.q(name)}) t nil)", request.token, timeout,
                ).strip()
                steps.append(_step(f"library:{name}", exists == "t", exists))
                if exists != "t":
                    return Result(False, steps, f"target_lib_missing: {name}")

            work_dir = self._work_dir(request)
            run_dir = posixpath.join(
                work_dir, ".vb_verilog",
                f"{_safe_name(request.library)}__{_safe_name(request.cell)}",
            )
            cdslib = posixpath.join(work_dir, "cds.lib")
            staged_cdslib = self.middle.run_command(
                f"test -s {shlex.quote(cdslib)} && "
                f"mkdir -p {shlex.quote(run_dir)} && "
                f"cp {shlex.quote(cdslib)} {shlex.quote(posixpath.join(run_dir, 'cds.lib'))}",
                timeout=60, token=request.token,
            )
            steps.append(_step("stage_cdslib", staged_cdslib.returncode == 0,
                               staged_cdslib))
            if staged_cdslib.returncode != 0:
                return Result(
                    False, steps,
                    f"cdslib_missing: {cdslib} not found — "
                    "start Virtuoso from a project dir that contains cds.lib",
                )

            source_name = _safe_name(Path(request.file_path).name, "design.v")
            remote_source = posixpath.join(run_dir, source_name)
            if request.file_is_local:
                staged = self.middle.upload_file(
                    Path(request.file_path), remote_source, timeout=timeout, token=request.token,
                )
            else:
                staged = self.middle.run_command(
                    f"cp {shlex.quote(request.file_path)} {shlex.quote(remote_source)}",
                    timeout=120, token=request.token,
                )
            steps.append(_step("stage", staged.returncode == 0, staged))
            if staged.returncode != 0:
                return Result(False, steps, staged.stderr or "source staging failed")

            ref_libs = request.ref_libs or ["basic"]
            param_content = (
                f"dest_sch_lib := {request.library}\n"
                f"ref_lib_list := {', '.join(ref_libs)}\n"
                f"import_if_exists := {1 if request.overwrite else 0}\n"
                "import_cells := 0\n"
                f"import_lib_cells := {request.import_lib_cells}\n"
                f"structural_views := {request.structural_views}\n"
                f"schematic_view_name := {request.schematic_view}\n"
                f"functional_view_name := {request.functional_view}\n"
                "netlist_view_name := netlist\n"
                f"symbol_view_name := {request.symbol_view}\n"
                f"overwrite_symbol := {1 if request.overwrite else 0}\n"
                "log_file_name := ./verilogIn.batch.log\n"
                "map_file_name := ./verilogIn.batch.map.table\n"
                "work_area := ./\n"
                f"power_net := {request.power_net}\n"
                f"ground_net := {request.ground_net}\n"
            )
            remote_param = posixpath.join(run_dir, "ihdl_param")
            self._write_remote(remote_param, param_content, request)
            self._write_remote(posixpath.join(run_dir, "ihdl.files"),
                               f"-param {remote_param}\n", request)

            root = self._cadence_root(request)
            ld_path = ":".join([
                f"{root}/tools.lnx86/lib/64bit/RHEL/RHEL8",
                f"{root}/tools.lnx86/lib/64bit",
                f"{root}/tools/lib/64bit",
            ])
            command = (
                f"cd {shlex.quote(run_dir)} && "
                f"LD_LIBRARY_PATH={shlex.quote(ld_path)}:$LD_LIBRARY_PATH "
                f"ihdl -cdslib {shlex.quote(posixpath.join(run_dir, 'cds.lib'))} "
                f"-f {shlex.quote(posixpath.join(run_dir, 'ihdl.files'))} "
                f"{shlex.quote(source_name)}"
            )
            run = self.middle.run_command(command, timeout=timeout, token=request.token)
            steps.append(_step("ihdl", run.returncode == 0, run))

            log_path = posixpath.join(run_dir, "verilogIn.batch.log")
            try:
                log_text = self._read_remote(log_path, request)
            except Exception:  # noqa: BLE001 - 失败时日志可能不存在
                log_text = ""
            failure = ""
            reason = ""
            if "ERROR (VERILOGIN-547)" in log_text:
                failure = "parse_failed"
                reason = "parse_failed"
            elif run.returncode != 0:
                reason = "ihdl_failed"
                failure = (run.stderr or "").strip() or f"rc={run.returncode}"
            elif "End of Logfile." not in log_text:
                failure = "incomplete_log"
                reason = "incomplete_log"
            if failure:
                xmvlog_text = ""
                try:
                    xmvlog_text = self._read_remote(posixpath.join(run_dir, "xmvlog.log"), request)
                except Exception:  # noqa: BLE001
                    pass
                diagnostics = [
                    line.strip() for line in xmvlog_text.splitlines()
                    if line.strip().startswith(("xmvlog: *E", "xmvlog: *W"))
                ][:20]
                return Result(False, steps, failure, {
                    "reason": reason or failure,
                    "log_path": log_path,
                    "diagnostics": diagnostics,
                })

            self._skill("ddUpdateLibList()", request.token, timeout)
            cells = _imported_cells(log_text)
            warnings = _import_warnings(log_text)
            verification = self._verify_import(request)
            return Result(True, steps, None, {
                "reason": "completed",
                "log_path": log_path,
                "cells": cells,
                "views": verification.get("views", []),
                "warnings": warnings,
                **{key: verification[key] for key in (
                    "instance_count", "net_count", "term_count", "bbox",
                ) if key in verification},
            })
        except Exception as exc:  # noqa: BLE001
            return Result(False, steps, f"{type(exc).__name__}: {exc}")

    def _verify_import(self, request: ImportRequest) -> dict[str, Any]:
        includes_schematic = request.structural_views in (1, 5)
        check_view = request.schematic_view if includes_schematic else request.functional_view
        raw = self._q(
            "let((cv) "
            f"cv = dbOpenCellViewByType({basic.q(request.library)} "
            f"{basic.q(request.cell)} {basic.q(check_view)} nil \"r\") "
            "if(cv "
            "let((out) out = list(length(cv~>instances) length(cv~>nets) "
            "length(cv~>terminals) "
            "list(list(xCoord(car(cv~>bBox)) yCoord(car(cv~>bBox))) "
            "list(xCoord(cadr(cv~>bBox)) yCoord(cadr(cv~>bBox))))) "
            "dbClose(cv) out) nil))",
            request.token,
            request.timeout,
        )
        parsed = basic.parse_sexpr(raw.strip()) if raw.strip() else None
        views = self._read_views(request)
        if not isinstance(parsed, list) or len(parsed) < 4:
            return {"views": views, "opened_view": None}
        return {
            "views": views,
            "opened_view": check_view,
            "instance_count": int(parsed[0]) if parsed[0] is not None else 0,
            "net_count": int(parsed[1]) if parsed[1] is not None else 0,
            "term_count": int(parsed[2]) if parsed[2] is not None else 0,
            "bbox": parsed[3],
        }

    # -- export -----------------------------------------------------------------

    def export(self, request: ExportRequest) -> Result:
        _require_text(request.token, "token")
        _require_text(request.library, "library")
        _require_text(request.cell, "cell")
        _require_text(request.view, "view")
        _require_bool(request.recursive, "recursive")
        _require_timeout(request.timeout)
        output = _require_text(request.output_path, "output_path")
        steps: list[dict[str, Any]] = []
        try:
            timeout = float(request.timeout or 300)
            work_dir = self._work_dir(request)
            remote_dir = posixpath.join(work_dir, ".vb_verilog_out")
            self.middle.run_command(
                f"mkdir -p {shlex.quote(remote_dir)}", timeout=60, token=request.token,
            )
            remote_out = posixpath.join(remote_dir, f"{_safe_name(request.cell)}.v")
            remote_log = posixpath.join(remote_dir, f"{_safe_name(request.cell)}.log")
            command = (
                f"cd {shlex.quote(work_dir)} && oa2verilog "
                f"-lib {shlex.quote(request.library)} "
                f"-cell {shlex.quote(request.cell)} "
                f"-view {shlex.quote(request.view)} "
                f"{'-recursive ' if request.recursive else ''}"
                f"-verilog {shlex.quote(remote_out)} "
                f"-logFile {shlex.quote(remote_log)}"
            )
            run = self.middle.run_command(command, timeout=timeout, token=request.token)
            steps.append(_step("oa2verilog", run.returncode == 0, run))
            if run.returncode != 0:
                return Result(False, steps, run.stderr or "oa2verilog failed")
            log_text = self._read_remote(remote_log, request)
            if "0 errors" not in log_text:
                return Result(False, steps, "oa2verilog reported errors",
                              {"log_path": remote_log})
            text = self._read_remote(remote_out, request)
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            local_log = output_path.with_suffix(".oa2verilog.log")
            local_log.write_text(log_text, encoding="utf-8")
            module_count = len(re.findall(r"^\s*module\s+(\w+)", text, re.MULTILINE))
            return Result(True, steps, None, {
                "verilog_path": str(output_path),
                "log_path": str(local_log),
                "module_count": module_count,
            })
        except Exception as exc:  # noqa: BLE001
            return Result(False, steps, f"{type(exc).__name__}: {exc}")


def _imported_cells(log_text: str) -> list[str]:
    cells: list[str] = []
    for line in log_text.splitlines():
        match = re.search(r"Checked[- ]in\s+(?:schematic|symbol|functional view)\s+(\S+)", line)
        if not match:
            continue
        cleaned = re.sub(r"[.,;:]$", "", match.group(1))
        if cleaned and cleaned not in cells:
            cells.append(cleaned)
    return cells


def _import_warnings(log_text: str) -> list[str]:
    return [
        line.strip() for line in log_text.splitlines()
        if re.search(r"WARNING \((VERILOGIN-(19|22|72|127|575))\)", line)
    ][:20]


#: spec 上层 §4.2: package-level self-description
OPERATIONS = (
    ("virtuoso.verilog.read", "read", ReadRequest, Result),
    ("virtuoso.verilog.write", "write", WriteRequest, Result),
    ("virtuoso.verilog.import", "import_verilog", ImportRequest, Result),
    ("virtuoso.verilog.export", "export", ExportRequest, Result),
)

OPERATION_NAMES = tuple(operation for operation, *_ in OPERATIONS)

__all__ = [
    "ExportRequest", "ImportRequest", "MAIN_FILE", "MASTER_TAG", "OPERATIONS",
    "OPERATION_NAMES", "Package", "ReadRequest", "Result", "VIEW_TYPE", "WriteRequest",
]
