"""``spectre`` business package.

Spec: ``spec/design-concepts/上层/7-spectre.md`` (Draft v3).

The package only calls the five middle interfaces plus the read-only
``query``.  It has no local/remote branch, no environment reads, and no
persistent state.  PSF parsing and metrics live in ``_spectre_util``.
"""
from __future__ import annotations

import csv
import json
import math
import posixpath
import re
import shlex
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common.paths import artifact_dir
from pyapi.models import Middle
from pyapi.packages._spectre_util import (
    compute_metric,
    detect_layout,
    list_result_files,
    parse_psf_directory,
    parse_psf_file,
    parse_sweep_directory,
)


_MODES = ("spectre", "aps", "x", "cx", "ax", "mx", "lx", "vx")
_MODE_ARGS = {
    "spectre": [],
    "aps": ["+aps"],
    "x": ["+x"],
    "cx": ["+preset=cx", "+mt"],
    "ax": ["+preset=ax", "+mt"],
    "mx": ["+preset=mx", "+mt"],
    "lx": ["+preset=lx", "+mt"],
    "vx": ["+preset=vx", "+mt"],
}
_ANALYSES = ("all", "tran", "dc", "ac", "info")


@dataclass
class Result:
    ok: bool
    steps: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    value: Any = None


@dataclass(frozen=True)
class CheckLicenseRequest:
    token: str
    spectre_bin: str | None = None
    timeout: int | None = None


@dataclass(frozen=True)
class RunRequest:
    token: str
    tasks: list[dict[str, Any]]
    max_workers: int = 4
    mode: str = "spectre"
    spectre_args: list[str] = field(default_factory=list)
    spectre_bin: str | None = None
    parse: str = "auto"
    download: bool = True
    output_root: str | None = None
    keep_run_dir: bool = False
    timeout: int | None = None


@dataclass(frozen=True)
class ReadResultsRequest:
    token: str
    source: str
    analysis: str = "all"
    output_dir: str | None = None
    timeout: int | None = None


@dataclass(frozen=True)
class MeasureRequest:
    token: str
    metrics: list[dict[str, Any]]
    data: dict[str, Any] | None = None
    source_path: str | None = None
    timeout: int | None = None


@dataclass(frozen=True)
class ExportRequest:
    token: str
    format: str
    output_path: str
    data: dict[str, Any] | None = None
    source_path: str | None = None
    columns: list[str] | None = None
    precision: int | None = None
    timeout: int | None = None


def _step(name: str, ok: bool, detail: Any) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail}


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_timeout(value: Any) -> None:
    if value is None:
        return
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError("timeout must be a positive finite number or None")


def _require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _require_job(value: Any, name: str = "job") -> str:
    text = _require_text(value, name)
    if "/" in text or "\\" in text or ".." in text:
        raise ValueError(f"{name} must not contain path separators or '..'")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", text):
        raise ValueError(f"{name} must match [A-Za-z0-9][A-Za-z0-9._-]*")
    return text


def _require_mode(value: Any, name: str = "mode") -> str:
    text = _require_text(value, name)
    if text not in _MODES:
        raise ValueError(f"{name} must be one of {', '.join(_MODES)}")
    return text


def _require_analysis(value: Any, name: str = "analysis") -> str:
    text = _require_text(value, name)
    if text not in _ANALYSES:
        raise ValueError(f"{name} must be one of {', '.join(_ANALYSES)}")
    return text


def _require_parse(value: Any) -> str:
    text = _require_text(value, "parse")
    if text not in ("auto", "none"):
        raise ValueError("parse must be 'auto' or 'none'")
    return text


def _safe_name(value: str, fallback: str = "result") -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_.-]+", "_", value or "").strip("_")
    return cleaned or fallback


def _split_bin(value: str) -> list[str]:
    try:
        parts = shlex.split(value.strip())
    except ValueError as exc:
        raise ValueError(f"spectre_bin is not valid shell syntax: {exc}") from exc
    return parts or ["spectre"]


def _task_defaults(request: RunRequest) -> dict[str, Any]:
    return {
        "token": request.token,
        "mode": _require_mode(request.mode),
        "spectre_args": list(request.spectre_args),
        "spectre_bin": request.spectre_bin,
        "parse": _require_parse(request.parse),
        "download": _require_bool(request.download, "download"),
        "output_root": request.output_root,
        "keep_run_dir": _require_bool(request.keep_run_dir, "keep_run_dir"),
        "timeout": request.timeout,
    }


def _normalize_tasks(request: RunRequest) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for index, raw in enumerate(request.tasks):
        if not isinstance(raw, dict):
            raise ValueError(f"tasks[{index}] must be an object")
        job = _require_job(raw.get("job"), f"tasks[{index}].job")
        netlist = _require_text(raw.get("netlist"), f"tasks[{index}].netlist")
        includes = raw.get("include_files", [])
        if includes is None:
            includes = []
        if not isinstance(includes, list) or not all(
            isinstance(item, str) and item for item in includes
        ):
            raise ValueError(f"tasks[{index}].include_files must be a list of paths")
        mode = raw.get("mode")
        if mode is not None:
            _require_mode(mode, f"tasks[{index}].mode")
        args = raw.get("spectre_args")
        if args is not None and (
            not isinstance(args, list)
            or not all(isinstance(item, str) and item.strip() for item in args)
        ):
            raise ValueError(
                f"tasks[{index}].spectre_args must be a list of non-empty flags"
            )
        tasks.append(
            {
                "job": job,
                "netlist": netlist,
                "include_files": list(includes),
                "mode": mode,
                "spectre_args": list(args) if args is not None else None,
            }
        )
    if len({task["job"] for task in tasks}) != len(tasks):
        raise ValueError("task job names must be unique")
    return tasks


def _command_result_detail(result: Any) -> Any:
    try:
        return result._asdict()
    except AttributeError:
        return {
            "returncode": getattr(result, "returncode", None),
            "stdout": getattr(result, "stdout", ""),
            "stderr": getattr(result, "stderr", ""),
            "kind": getattr(result, "kind", "command"),
        }


def _build_spectre_command(
    bin_text: str,
    run_dir: str,
    netlist_name: str,
    stem: str,
    user_args: list[str],
    mode: str,
) -> str:
    prefix = _split_bin(bin_text or "spectre")
    user_flags = [item for item in user_args if item.strip()]
    mode_args = list(_MODE_ARGS[mode])
    all_flags = set(prefix[1:]) | set(user_flags) | set(mode_args)
    log_path = posixpath.join(run_dir, "spectre.out")
    raw_dir = posixpath.join(run_dir, f"{stem}.raw")

    argv = list(prefix)
    if "-64" not in all_flags and "-32" not in all_flags:
        argv.append("-64")
    argv.append(netlist_name)
    argv.extend(["+escchars", "+log", log_path, "-format", "psfascii", "-raw", raw_dir])
    argv.extend(user_flags)
    argv.extend(mode_args)
    if "+lqtimeout" not in all_flags:
        argv.extend(["+lqtimeout", "900"])
    if "-maxw" not in all_flags:
        argv.extend(["-maxw", "5"])
    if "-maxn" not in all_flags:
        argv.extend(["-maxn", "5"])
    argv.append("+logstatus")

    command = " ".join(shlex.quote(part) for part in argv)
    return f"cd {shlex.quote(run_dir)} && {command}"


def _prepare_command(run_dir: str) -> str:
    quoted = shlex.quote(run_dir)
    return (
        f"mkdir -p {quoted} && "
        f"if find {quoted} -mindepth 1 -maxdepth 1 -print -quit | grep -q .; "
        f"then echo EXISTS; exit 9; fi; echo READY"
    )


def _has_fatal(output: str) -> bool:
    lower = output.lower()
    for line in lower.splitlines():
        if "0 errors" in line or "0 warnings" in line:
            continue
        if (
            "error reading" in line
            or "read-in failed" in line
            or ("license" in line and ("error" in line or "denied" in line))
            or "spcrtrf-15044" in line
            or "failed to converge" in line
            or "convergence failed" in line
            or "convergence failure" in line
            or "spectre terminated prematurely due to fatal error" in line
            or "fatal error" in line
            or bool(re.search(r"^\s*error\s*\(", line, re.IGNORECASE))
            or "segmentation" in line
            or "core dump" in line
        ):
            return True
    return False


def _classify_errors(output: str) -> list[str]:
    lower = output.lower()
    if "error reading" in lower or "read-in failed" in lower:
        return ["netlist read error (missing include or syntax)"]
    has_license_error = any(
        "license" in line and ("error" in line or "denied" in line)
        and "0 errors" not in line
        for line in lower.splitlines()
    )
    if has_license_error:
        return ["license error"]
    if _has_fatal(output):
        for marker in ("failed to converge", "convergence failed", "spcrtrf-15044"):
            if marker in lower:
                return ["convergence failure"]
        return ["spectre reported a fatal error"]
    return []


def _extract_warnings(output: str) -> list[str]:
    warnings: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if "warning" in lower and "0 warnings" not in lower:
            warnings.append(stripped)
    return warnings


def _load_data(data: dict[str, Any] | None, source_path: str | None) -> dict[str, Any]:
    if (data is None) == (source_path is None):
        raise ValueError("exactly one of data or source_path must be provided")
    if data is not None:
        if not isinstance(data, dict):
            raise ValueError("data must be an object")
        return data
    path = Path(source_path or "")
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read source_path: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"source_path is not valid JSON: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError("source_path JSON must contain an object")
    return loaded


class Package:
    """Spectre domain package."""

    def __init__(self, middle: Middle) -> None:
        self.middle = middle

    def _query(self, token: str) -> Any:
        facts = self.middle.query(token=token)
        if facts.status.value != "success":
            raise RuntimeError("; ".join(facts.errors) or "query failed")
        return facts

    def _spectre_facts(self, token: str) -> tuple[str, str]:
        facts = self._query(token)
        role = facts.roles.get("spectre")
        if role is None or not role.root:
            raise RuntimeError("spectre role root is not available")
        return role.root.rstrip("/"), role.bin or "spectre"

    # -- check_license --------------------------------------------------------

    def check_license(self, request: CheckLicenseRequest) -> Result:
        token = _require_text(request.token, "token")
        _require_timeout(request.timeout)
        steps: list[dict[str, Any]] = []
        try:
            facts = self._query(token)
            role = facts.roles.get("spectre")
            bin_text = request.spectre_bin or (role.bin if role else None) or "spectre"
            version_cmd = " ".join(shlex.quote(part) for part in _split_bin(bin_text) + ["-V"])
            version_result = self.middle.run_spectre_command(
                version_cmd, timeout=request.timeout, token=token
            )
            steps.append(
                _step("version", version_result.returncode == 0,
                      _command_result_detail(version_result))
            )

            version: str | None = None
            version_raw = (version_result.stdout or "") + "\n" + (version_result.stderr or "")
            for line in version_raw.splitlines():
                if line.strip().startswith("@(#)$CDS:"):
                    version = line.strip()
                    break

            lmstat_interface: str | None = None
            lmstat_raw = ""
            lmstat_error = ""
            licenses: list[str] = []
            lmstat = self.middle.run_command(
                "lmstat -a", timeout=request.timeout, token=token
            )
            steps.append(
                _step("lmstat_command", lmstat.returncode == 0,
                      _command_result_detail(lmstat))
            )
            if lmstat.returncode == 0 and (lmstat.stdout or "").strip():
                lmstat_interface = "command"
                lmstat_raw = lmstat.stdout
                lmstat_error = lmstat.stderr
            else:
                lmstat = self.middle.run_spectre_command(
                    "lmstat -a", timeout=request.timeout, token=token
                )
                steps.append(
                    _step("lmstat_spectre", lmstat.returncode == 0,
                          _command_result_detail(lmstat))
                )
                lmstat_interface = "spectre"
                lmstat_raw = lmstat.stdout
                lmstat_error = lmstat.stderr

            for line in lmstat_raw.splitlines():
                if "Users of" in line:
                    licenses.append(line.strip())
            if not licenses:
                for line in (lmstat_error or "").splitlines():
                    if "Error getting status" in line or "down or not responding" in line:
                        lmstat_error = line.strip()
                        break

            warnings = []
            if version and (not licenses or lmstat_error):
                warnings.append(
                    "license detail unavailable or shows no active users"
                )
            ok = version is not None
            value = {
                "bin": bin_text,
                "version": version,
                "version_raw": version_raw.strip() or None,
                "lmstat_interface": lmstat_interface,
                "lmstat_raw": lmstat_raw.strip() or None,
                "lmstat_error": lmstat_error.strip() or None,
                "licenses": licenses,
                "errors": [] if ok else _classify_errors(version_raw),
                "warnings": warnings,
            }
            return Result(
                ok,
                steps,
                None if ok else "spectre version check failed",
                value,
            )
        except Exception as exc:
            return Result(False, steps, f"{type(exc).__name__}: {exc}")

    # -- run ------------------------------------------------------------------

    def run(self, request: RunRequest) -> Result:
        token = _require_text(request.token, "token")
        _require_timeout(request.timeout)
        steps: list[dict[str, Any]] = []
        try:
            tasks = _normalize_tasks(request)
            defaults = _task_defaults(request)
            if defaults["parse"] == "auto" and not defaults["download"]:
                raise ValueError("parse='auto' requires download=true")
            if defaults["parse"] == "none" and not defaults["keep_run_dir"]:
                raise ValueError("parse='none' requires keep_run_dir=true")
            if isinstance(request.max_workers, bool) or not isinstance(request.max_workers, int) \
                    or request.max_workers < 1:
                raise ValueError("max_workers must be at least 1")
            if request.output_root is not None:
                _require_text(request.output_root, "output_root")

            root, bin_text = self._spectre_facts(token)
            if request.spectre_bin:
                bin_text = request.spectre_bin
            defaults["bin"] = bin_text
            defaults["root"] = root
            effective_workers = min(request.max_workers, len(tasks))
            steps.append(
                _step("validate", True, {
                    "tasks": len(tasks), "max_workers": effective_workers,
                })
            )

            runs: list[dict[str, Any] | None] = [None] * len(tasks)
            with ThreadPoolExecutor(max_workers=effective_workers) as executor:
                futures = [
                    (index, executor.submit(self._run_one, task, defaults))
                    for index, task in enumerate(tasks)
                ]
                for index, future in futures:
                    try:
                        runs[index] = future.result()
                    except Exception as exc:  # noqa: BLE001
                        runs[index] = {
                            "job": tasks[index]["job"],
                            "ok": False,
                            "error": f"{type(exc).__name__}: {exc}",
                            "steps": [],
                            "value": None,
                        }

            completed = [item for item in runs if item is not None]
            succeeded = sum(1 for item in completed if item.get("ok"))
            failed = len(completed) - succeeded
            ok = succeeded == len(tasks)
            steps.append(
                _step("batch", ok, {"succeeded": succeeded, "failed": failed})
            )
            return Result(
                ok,
                steps,
                None if ok else f"{failed}/{len(tasks)} tasks failed",
                {"runs": completed, "succeeded": succeeded, "failed": failed},
            )
        except Exception as exc:
            return Result(False, steps, f"{type(exc).__name__}: {exc}")

    def _run_one(
        self, task: dict[str, Any], defaults: dict[str, Any]
    ) -> dict[str, Any]:
        started = time.perf_counter()
        steps: list[dict[str, Any]] = []
        job = task["job"]
        run_dir = posixpath.join(defaults["root"], "spectre", job)
        output_dir: Path | None = None
        prepared_ok = False
        result: dict[str, Any] = {
            "job": job,
            "ok": False,
            "error": None,
            "steps": steps,
            "value": None,
        }
        try:
            prepared = self.middle.run_spectre_command(
                _prepare_command(run_dir),
                timeout=defaults["timeout"], token=defaults["token"],
            )
            steps.append(
                _step("prepare", prepared.returncode == 0,
                      _command_result_detail(prepared))
            )
            if prepared.returncode != 0:
                result["error"] = prepared.stderr.strip() or "run directory is not empty"
                result["value"] = self._empty_run_value(job, run_dir, "error")
                return result
            prepared_ok = True

            netlist_path = Path(task["netlist"])
            if not netlist_path.exists():
                raise FileNotFoundError(f"netlist not found: {netlist_path}")
            netlist_name = netlist_path.name
            stem = netlist_path.stem
            remote_netlist = posixpath.join(run_dir, netlist_name)

            uploaded = self.middle.upload_file(
                netlist_path, remote_netlist,
                timeout=defaults["timeout"], token=defaults["token"],
            )
            steps.append(
                _step("upload_netlist", uploaded.returncode == 0,
                      _command_result_detail(uploaded))
            )
            if uploaded.returncode != 0:
                result["error"] = uploaded.stderr.strip() or "netlist upload failed"
                result["value"] = self._empty_run_value(job, run_dir, "error")
                self._cleanup_run_dir(run_dir, steps, defaults)
                return result

            include_paths = [Path(item) for item in task["include_files"]]
            names = [netlist_name] + [item.name for item in include_paths]
            if len(set(names)) != len(names):
                raise ValueError("netlist and include basenames must be unique")
            for include_path in include_paths:
                if not include_path.exists():
                    raise FileNotFoundError(f"include file not found: {include_path}")
                remote_include = posixpath.join(run_dir, include_path.name)
                uploaded = self.middle.upload_file(
                    include_path, remote_include,
                    timeout=defaults["timeout"], token=defaults["token"],
                )
                steps.append(
                    _step(f"upload_include:{include_path.name}",
                          uploaded.returncode == 0,
                          _command_result_detail(uploaded))
                )
                if uploaded.returncode != 0:
                    result["error"] = uploaded.stderr.strip() or "include upload failed"
                    result["value"] = self._empty_run_value(job, run_dir, "error")
                    self._cleanup_run_dir(run_dir, steps, defaults)
                    return result

            mode = task["mode"] or defaults["mode"]
            user_args = task["spectre_args"] if task["spectre_args"] is not None \
                else defaults["spectre_args"]
            command = _build_spectre_command(
                defaults["bin"], run_dir, netlist_name, stem, user_args, mode
            )
            executed = self.middle.run_spectre_command(
                command, timeout=defaults["timeout"], token=defaults["token"],
            )
            steps.append(
                _step("execute", executed.returncode == 0,
                      _command_result_detail(executed))
            )

            status = "success"
            errors: list[str] = []
            warnings: list[str] = []
            combined = (executed.stdout or "") + "\n" + (executed.stderr or "")
            transport_kind = executed.kind
            raw_exists = False
            data: dict[str, Any] = {}
            points: dict[int, dict[str, Any]] = {}
            result_kind: str | None = None
            layout: str | None = None
            analyses: list[str] = []
            output_files: list[str] = []
            log_path: str | None = None

            if defaults["download"]:
                output_dir = (
                    Path(defaults["output_root"]) / job
                    if defaults["output_root"]
                    else Path(artifact_dir()) / "spectre" / job
                )
                output_dir.mkdir(parents=True, exist_ok=True)
                raw_remote = posixpath.join(run_dir, f"{stem}.raw")
                raw_local = output_dir / f"{stem}.raw"
                downloaded = self.middle.download_file(
                    raw_remote, raw_local, recursive=True,
                    timeout=defaults["timeout"], token=defaults["token"],
                )
                steps.append(
                    _step("download_raw", downloaded.returncode == 0,
                          _command_result_detail(downloaded))
                )
                if downloaded.returncode != 0:
                    self._download_aux_files(
                        run_dir, output_dir, steps, defaults,
                    )
                    result["error"] = downloaded.stderr.strip() or "raw download failed"
                    result["value"] = {
                        "job": job, "status": "error", "command": command,
                        "run_dir": run_dir, "netlist_path": remote_netlist,
                        "output_dir": str(output_dir), "log_path": None,
                        "returncode": executed.returncode,
                        "transport_kind": transport_kind,
                        "result_kind": None, "layout": None, "data": {},
                        "points": {}, "analyses": [], "output_files": [],
                        "errors": [downloaded.stderr.strip() or "raw download failed"],
                        "warnings": warnings, "duration": time.perf_counter() - started,
                    }
                    self._cleanup_run_dir(run_dir, steps, defaults)
                    return result
                raw_exists = raw_local.exists()
                log_path = self._download_aux_files(
                    run_dir, output_dir, steps, defaults,
                )
                output_files = sorted(
                    str(item)
                    for item in output_dir.rglob("*")
                    if item.is_file()
                )

            if transport_kind != "command":
                status = "error"
                errors = [
                    f"spectre transport failure ({transport_kind}): "
                    + (executed.stderr or "").strip()
                ]
            elif executed.returncode != 0 or _has_fatal(combined):
                status = "partial" if raw_exists else "failure"
                errors = _classify_errors(combined) or [
                    f"exit code {executed.returncode}"
                    if executed.returncode != 0
                    else "spectre reported a fatal error"
                ]
            elif defaults["download"] and not raw_exists:
                status = "error"
                errors = ["raw output directory is missing"]
            warnings.extend(_extract_warnings(combined))

            if defaults["parse"] == "auto" and raw_exists and transport_kind == "command":
                try:
                    raw_local = output_dir / f"{stem}.raw" if output_dir else None
                    if raw_local:
                        parsed = self._parse_local_results(raw_local)
                        result_kind = parsed["result_kind"]
                        layout = parsed.get("layout")
                        data = parsed.get("data", {})
                        points = parsed.get("points", {})
                        analyses = parsed.get("analyses", [])
                except Exception as exc:
                    if status == "success":
                        status = "partial"
                    errors.append(f"result parsing failed: {exc}")

            self._cleanup_run_dir(run_dir, steps, defaults, warnings=warnings)

            ok = status == "success"
            result["ok"] = ok
            result["error"] = None if ok else "; ".join(errors) or status
            result["value"] = {
                "job": job,
                "status": status,
                "command": command,
                "run_dir": run_dir,
                "netlist_path": remote_netlist,
                "output_dir": str(output_dir) if output_dir else None,
                "log_path": log_path,
                "returncode": executed.returncode,
                "transport_kind": transport_kind,
                "result_kind": result_kind,
                "layout": layout,
                "data": data,
                "points": points,
                "analyses": analyses,
                "output_files": output_files,
                "errors": errors,
                "warnings": warnings,
                "duration": time.perf_counter() - started,
            }
            return result
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
            result["value"] = self._empty_run_value(job, run_dir, "error")
            if prepared_ok:
                self._cleanup_run_dir(run_dir, steps, defaults)
            return result

    def _cleanup_run_dir(
        self,
        run_dir: str,
        steps: list[dict[str, Any]],
        defaults: dict[str, Any],
        warnings: list[str] | None = None,
    ) -> None:
        """Best-effort removal of a run directory created by this operation."""
        if defaults["keep_run_dir"]:
            return
        cleanup = self.middle.run_spectre_command(
            f"rm -rf {shlex.quote(run_dir)}",
            timeout=defaults["timeout"], token=defaults["token"],
        )
        steps.append(
            _step("cleanup", cleanup.returncode == 0,
                  _command_result_detail(cleanup))
        )
        if cleanup.returncode != 0:
            message = (cleanup.stderr or "").strip() or "run_dir cleanup failed"
            if warnings is not None:
                warnings.append(message)

    def _download_aux_files(
        self,
        run_dir: str,
        output_dir: Path,
        steps: list[dict[str, Any]],
        defaults: dict[str, Any],
    ) -> str | None:
        log_path: str | None = None
        for remote_name, local_name in (
            ("spectre.out", "spectre.out"),
            ("spectre.fc", "spectre.fc"),
            ("spectre.ic", "spectre.ic"),
        ):
            downloaded = self.middle.download_file(
                posixpath.join(run_dir, remote_name), output_dir / local_name,
                timeout=defaults["timeout"], token=defaults["token"],
            )
            steps.append(
                _step(f"download_{local_name}", downloaded.returncode == 0,
                      _command_result_detail(downloaded))
            )
            if downloaded.returncode == 0:
                path = str(output_dir / local_name)
                if remote_name == "spectre.out":
                    log_path = path
        return log_path

    def _parse_local_results(self, raw_dir: Path) -> dict[str, Any]:
        kind = detect_layout(raw_dir)
        if kind == "sweep":
            parsed = parse_sweep_directory(raw_dir)
            return {
                "result_kind": "sweep",
                "layout": parsed["layout"],
                "data": {},
                "points": parsed["points"],
                "analyses": [],
            }
        if kind == "raw":
            parsed = parse_psf_directory(raw_dir, "all")
            return {
                "result_kind": "raw",
                "layout": None,
                "data": parsed["data"],
                "points": {},
                "analyses": parsed["analyses"],
            }
        raise ValueError(f"unrecognized PSF layout: {raw_dir}")

    def _empty_run_value(
        self, job: str, run_dir: str, status: str
    ) -> dict[str, Any]:
        return {
            "job": job, "status": status, "command": None, "run_dir": run_dir,
            "netlist_path": None, "output_dir": None, "log_path": None,
            "returncode": None, "transport_kind": None, "result_kind": None,
            "layout": None, "data": {}, "points": {}, "analyses": [],
            "output_files": [], "errors": [], "warnings": [],
            "duration": 0.0,
        }

    # -- read_results ---------------------------------------------------------

    def read_results(self, request: ReadResultsRequest) -> Result:
        token = _require_text(request.token, "token")
        source = _require_text(request.source, "source")
        analysis = _require_analysis(request.analysis)
        _require_timeout(request.timeout)
        steps: list[dict[str, Any]] = []
        try:
            base = (
                Path(request.output_dir)
                if request.output_dir
                else Path(artifact_dir()) / "spectre" / "results"
                / _safe_name(Path(source).name)
            )
            base.parent.mkdir(parents=True, exist_ok=True)

            downloaded_dir = self.middle.download_file(
                source, base, recursive=True,
                timeout=request.timeout, token=token,
            )
            steps.append(
                _step("download_dir", downloaded_dir.returncode == 0,
                      _command_result_detail(downloaded_dir))
            )
            local: Path
            if downloaded_dir.returncode == 0:
                local = base
            else:
                local_file = base / _safe_name(Path(source).name, "result.psf")
                downloaded_file = self.middle.download_file(
                    source, local_file, recursive=False,
                    timeout=request.timeout, token=token,
                )
                steps.append(
                    _step("download_file", downloaded_file.returncode == 0,
                          _command_result_detail(downloaded_file))
                )
                if downloaded_file.returncode != 0:
                    detail = downloaded_file.stderr.strip() or downloaded_dir.stderr.strip()
                    return Result(False, steps, detail or "result download failed")
                local = local_file

            kind = detect_layout(local)
            steps.append(_step("detect", True, {"kind": kind, "local": str(local)}))

            if kind == "single":
                header, data = parse_psf_file(local)
                value = {
                    "kind": "single",
                    "source": source,
                    "output_dir": str(local),
                    "analysis": header.get("analysis type"),
                    "layout": None,
                    "point_count": 0,
                    "header": header,
                    "data": data,
                    "points": {},
                    "analyses": [],
                    "signals": sorted(data),
                    "files": [str(local)],
                }
            elif kind == "raw":
                parsed = parse_psf_directory(local, analysis)
                value = {
                    "kind": "raw",
                    "source": source,
                    "output_dir": str(local),
                    "analysis": analysis,
                    "layout": None,
                    "point_count": 0,
                    "header": None,
                    "data": parsed["data"],
                    "points": {},
                    "analyses": parsed["analyses"],
                    "signals": sorted(parsed["data"]),
                    "files": parsed["files"],
                }
            else:
                parsed = parse_sweep_directory(local)
                value = {
                    "kind": "sweep",
                    "source": source,
                    "output_dir": str(local),
                    "analysis": None,
                    "layout": parsed["layout"],
                    "point_count": parsed["point_count"],
                    "header": None,
                    "data": {},
                    "points": parsed["points"],
                    "analyses": [],
                    "signals": parsed["signals"],
                    "files": parsed["files"],
                }
            return Result(True, steps, None, value)
        except Exception as exc:
            return Result(False, steps, f"{type(exc).__name__}: {exc}")

    # -- measure --------------------------------------------------------------

    def measure(self, request: MeasureRequest) -> Result:
        token = _require_text(request.token, "token")
        _require_timeout(request.timeout)
        steps: list[dict[str, Any]] = []
        try:
            if not isinstance(request.metrics, list) or not request.metrics:
                raise ValueError("metrics must be a non-empty list")
            data = _load_data(request.data, request.source_path)
            evaluated: list[dict[str, Any]] = []
            for index, spec in enumerate(request.metrics):
                if not isinstance(spec, dict):
                    evaluated.append({
                        "type": "unknown", "ok": False, "value": None,
                        "unit": None, "detail": f"metrics[{index}] must be an object",
                    })
                    continue
                evaluated.append(compute_metric(data, spec))
            ok = all(item["ok"] for item in evaluated)
            steps.append(
                _step("metrics", ok, {
                    "requested": len(evaluated),
                    "passed": sum(1 for item in evaluated if item["ok"]),
                })
            )
            return Result(
                ok,
                steps,
                None if ok else "; ".join(
                    item["detail"] or item["type"] for item in evaluated if not item["ok"]
                ),
                {"metrics": evaluated,
                 "source": "inline" if request.data is not None else request.source_path},
            )
        except Exception as exc:
            return Result(False, steps, f"{type(exc).__name__}: {exc}")

    # -- export ---------------------------------------------------------------

    def export(self, request: ExportRequest) -> Result:
        token = _require_text(request.token, "token")
        fmt = _require_text(request.format, "format")
        output_path = _require_text(request.output_path, "output_path")
        _require_timeout(request.timeout)
        steps: list[dict[str, Any]] = []
        try:
            if fmt not in ("csv", "json"):
                raise ValueError("format must be 'csv' or 'json'")
            if request.columns is not None and (
                not isinstance(request.columns, list)
                or not all(isinstance(item, str) and item for item in request.columns)
            ):
                raise ValueError("columns must be a list of non-empty names")
            if request.precision is not None and (
                isinstance(request.precision, bool)
                or not isinstance(request.precision, int)
                or request.precision < 1
                or request.precision > 16
            ):
                raise ValueError("precision must be an integer between 1 and 16")
            data = _load_data(request.data, request.source_path)
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            if fmt == "csv":
                columns, rows = self._write_csv(
                    data, path, request.columns, request.precision
                )
            else:
                columns, rows = self._write_json(data, path)
            size = path.stat().st_size
            steps.append(
                _step("write", True, {"path": str(path), "bytes": size})
            )
            return Result(True, steps, None, {
                "output_path": str(path), "format": fmt,
                "columns": columns, "rows": rows, "bytes": size,
            })
        except Exception as exc:
            return Result(False, steps, f"{type(exc).__name__}: {exc}")

    def _write_csv(
        self,
        data: dict[str, Any],
        path: Path,
        requested_columns: list[str] | None,
        precision: int | None,
    ) -> tuple[list[str], int]:
        column_names: list[str] = []
        series: dict[str, list[Any]] = {}

        def add(name: str, value: list[Any]) -> None:
            if name not in column_names:
                column_names.append(name)
                series[name] = value

        if requested_columns:
            for name in requested_columns:
                if name not in data:
                    raise ValueError(f"column '{name}' is not present in data")
                value = data[name]
                if isinstance(value, dict) and "re" in value and "im" in value:
                    add(f"{name}.re", value["re"])
                    add(f"{name}.im", value["im"])
                elif isinstance(value, list):
                    add(name, value)
                else:
                    raise ValueError(f"column '{name}' is not a vector")
        else:
            priority = ("time", "freq", "sweep_var")
            for name in list(priority) + [
                key for key in data if key not in priority
            ]:
                value = data.get(name)
                if isinstance(value, dict) and "re" in value and "im" in value:
                    add(f"{name}.re", value["re"])
                    add(f"{name}.im", value["im"])
                elif isinstance(value, list):
                    add(name, value)

        rows = max((len(value) for value in series.values()), default=0)
        formatter = (lambda value: f"{value:.{precision}g}") if precision else str
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(column_names)
            for row_index in range(rows):
                row = []
                for name in column_names:
                    values = series[name]
                    value = values[row_index] if row_index < len(values) else ""
                    if isinstance(value, float) and precision:
                        row.append(formatter(value))
                    else:
                        row.append(value)
                writer.writerow(row)
        return column_names, rows

    def _write_json(
        self, data: dict[str, Any], path: Path
    ) -> tuple[list[str], int]:
        columns = [
            key for key, value in data.items()
            if isinstance(value, (list, dict))
        ]
        rows = max(
            (
                len(value["re"]) if isinstance(value, dict) else len(value)
                for value in data.values()
                if isinstance(value, (list, dict))
            ),
            default=0,
        )
        payload = {
            "format": "json",
            "metadata": {"columns": columns, "rows": rows},
            "data": data,
        }
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return columns, rows


OPERATIONS = (
    ("spectre.check_license", "check_license", CheckLicenseRequest, Result),
    ("spectre.run", "run", RunRequest, Result),
    ("spectre.read_results", "read_results", ReadResultsRequest, Result),
    ("spectre.measure", "measure", MeasureRequest, Result),
    ("spectre.export", "export", ExportRequest, Result),
)

OPERATION_NAMES = tuple(operation for operation, *_ in OPERATIONS)

__all__ = [
    "CheckLicenseRequest",
    "ExportRequest",
    "MeasureRequest",
    "OPERATIONS",
    "OPERATION_NAMES",
    "Package",
    "ReadResultsRequest",
    "Result",
    "RunRequest",
]
