"""``calibre`` business package: DRC / LVS / PEX（物理验证三件套）。

设计口径见 ``spec/design-concepts/上层/12-calibre.md``：

* run 类操作默认**非阻塞**（后台启动 + `job_id`），`calibre.status` 轮询，`calibre.read_results` 出结构化结论；
* 用户只给"版图 + 顶层名 + deck"；deck 目录整份 stage（解决相对 include），占位符按白名单改写；
* 全部落盘都在 run dir，不改共享配置（插件化）；全部走 command role 的 C/D/U 接口。
"""
from __future__ import annotations

import hashlib
import json
import math
import posixpath
import re
import shlex
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common.paths import artifact_dir
from pyapi.models import ExecutionStatus, Middle
from pyapi.packages import _calibre_util as cu

OPERATION_NAMES = (
    "calibre.check_env",
    "calibre.drc",
    "calibre.lvs",
    "calibre.pex",
    "calibre.status",
    "calibre.read_results",
    "calibre.export",
)

_KINDS = ("drc", "lvs", "pex")
_DEFAULT_POLL = 5.0
_LOG_TAIL_DEFAULT = 40

#: 工具事实来自注册表的 per-role 用户组（spec 中层配置文档 §2.3：中层不探测、原样透传）
_FACT_GROUP = "calibre"
_MISSING_FACTS = (
    "缺少 calibre 工具事实：请在注册表 role.command.calibre 下配置 bin"
    "（例如 {\"role\":{\"command\":{\"calibre\":{\"bin\":\"/opt/eda/mentor/.../bin/calibre\"}}}}）；"
    "本包不做探测、也不回退到 PATH"
)

#: export 的预定义条目 -> run dir 下的相对路径/glob
_EXPORT_ITEMS: dict[str, tuple[str, ...]] = {
    "summary": ("DRC.rep", "lvs.rep", "lvs.rep.ext", "calibre_erc.sum"),
    "results_db": ("DRC_RES.db",),
    "netlist": ("svdb",),
    "log": ("drc.log", "lvs.log", "pex.stage1.log", "pex.stage2.log", "pex.stage3.log"),
}


# ------------------------------------------------------------------ 请求模型 --
@dataclass(frozen=True)
class CheckEnvRequest:
    token: str
    calibre_bin: str | None = None
    deck: str | None = None
    timeout: int | None = None

    def __post_init__(self) -> None:
        _require_token(self.token)
        _opt_text(self.calibre_bin, "calibre_bin")
        _opt_text(self.deck, "deck")
        _opt_timeout(self.timeout)


@dataclass(frozen=True)
class RunRequest:
    """DRC / LVS / PEX 共用请求（kind 由操作决定）。"""

    token: str
    gds: str
    top: str
    deck: str
    cdl: str | None = None
    lvs_run_dir: str | None = None
    job_id: str | None = None
    run_dir: str | None = None
    calibre_bin: str | None = None
    turbo: int = 4
    hier: bool = True
    fmt: str = "none"
    power: str | None = None
    ground: str | None = None
    blocking: bool = False
    poll_interval: float = _DEFAULT_POLL
    timeout: int | None = None

    def __post_init__(self) -> None:
        _require_token(self.token)
        _require_text(self.gds, "gds")
        _require_text(self.top, "top")
        _require_text(self.deck, "deck")
        _opt_text(self.cdl, "cdl")
        _opt_text(self.lvs_run_dir, "lvs_run_dir")
        _opt_text(self.job_id, "job_id")
        _opt_text(self.run_dir, "run_dir")
        _opt_text(self.calibre_bin, "calibre_bin")
        _opt_text(self.power, "power")
        _opt_text(self.ground, "ground")
        if isinstance(self.turbo, bool) or not isinstance(self.turbo, int) or not 1 <= self.turbo <= 64:
            raise ValueError("turbo must be an integer in [1, 64]")
        _require_bool(self.hier, "hier")
        _require_bool(self.blocking, "blocking")
        if self.fmt not in ("none", "spice", "simple"):
            raise ValueError("fmt must be none/spice/simple")
        if not isinstance(self.poll_interval, (int, float)) or not math.isfinite(self.poll_interval) \
                or self.poll_interval <= 0:
            raise ValueError("poll_interval must be a positive finite number")
        _opt_timeout(self.timeout)


@dataclass(frozen=True)
class StatusRequest:
    token: str
    job_id: str | None = None
    run_dir: str | None = None
    kind: str = "drc"
    timeout: int | None = None

    def __post_init__(self) -> None:
        _require_token(self.token)
        _opt_text(self.job_id, "job_id")
        _opt_text(self.run_dir, "run_dir")
        if self.job_id is None and self.run_dir is None:
            raise ValueError("status needs job_id or run_dir")
        if self.kind not in _KINDS:
            raise ValueError("kind must be drc/lvs/pex")
        _opt_timeout(self.timeout)


@dataclass(frozen=True)
class ReadResultsRequest:
    token: str
    job_id: str | None = None
    run_dir: str | None = None
    kind: str | None = None
    limit: int = 20
    log_lines: int = _LOG_TAIL_DEFAULT
    timeout: int | None = None

    def __post_init__(self) -> None:
        _require_token(self.token)
        _opt_text(self.job_id, "job_id")
        _opt_text(self.run_dir, "run_dir")
        if self.job_id is None and self.run_dir is None:
            raise ValueError("read_results needs job_id or run_dir")
        if self.kind is not None and self.kind not in _KINDS:
            raise ValueError("kind must be drc/lvs/pex")
        if isinstance(self.limit, bool) or not isinstance(self.limit, int) or not 1 <= self.limit <= 500:
            raise ValueError("limit must be an integer in [1, 500]")
        if isinstance(self.log_lines, bool) or not isinstance(self.log_lines, int) \
                or not 0 <= self.log_lines <= 500:
            raise ValueError("log_lines must be an integer in [0, 500]")
        _opt_timeout(self.timeout)


@dataclass(frozen=True)
class ExportRequest:
    token: str
    job_id: str | None = None
    run_dir: str | None = None
    kind: str | None = None
    items: tuple[str, ...] = ("summary",)
    local_dir: str | None = None
    timeout: int | None = None

    def __post_init__(self) -> None:
        _require_token(self.token)
        _opt_text(self.job_id, "job_id")
        _opt_text(self.run_dir, "run_dir")
        if self.job_id is None and self.run_dir is None:
            raise ValueError("export needs job_id or run_dir")
        if self.kind is not None and self.kind not in _KINDS:
            raise ValueError("kind must be drc/lvs/pex")
        if not isinstance(self.items, (list, tuple)) or not self.items:
            raise ValueError("items must be a non-empty list")
        for item in self.items:
            if item not in _EXPORT_ITEMS and item != "all_small":
                raise ValueError(f"unknown export item: {item}")
        _opt_text(self.local_dir, "local_dir")
        _opt_timeout(self.timeout)


@dataclass
class Result:
    ok: bool
    steps: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    value: Any = None


# -------------------------------------------------------------------- 校验器 --
def _require_token(token: Any) -> str:
    if not isinstance(token, str) or not token:
        raise ValueError("token must be a non-empty string")
    return token


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _opt_text(value: Any, name: str) -> None:
    if value is None:
        return
    _require_text(value, name)
    if "\x00" in value:
        raise ValueError(f"{name} must not contain NUL")


def _require_bool(value: Any, name: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")


def _opt_timeout(value: Any) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) or value <= 0:
        raise ValueError("timeout must be a positive finite number or None")


class Package:
    """Calibre 物理验证包（构造只接受 ``Middle``）。"""

    def __init__(self, middle: Middle) -> None:
        self.middle = middle

    # ------------------------------------------------------------- check_env --
    def check_env(self, request: CheckEnvRequest) -> Result:
        steps: list[dict[str, Any]] = []
        binary = self._calibre_bin(request.token, request.calibre_bin, steps)
        if binary is None:
            return Result(False, steps, _MISSING_FACTS, None)
        cmd = (
            f"CAL=$(command -v {shlex.quote(binary)} 2>/dev/null || true); "
            "echo \"###PATH\"; echo \"$CAL\"; "
            "echo \"###VERSION\"; [ -n \"$CAL\" ] && timeout 60 $CAL -version 2>&1 | head -3; "
            "echo \"###DECK\"; "
            + (f"test -f {shlex.quote(request.deck)} && echo deck_file_ok || echo deck_file_missing; "
               f"test -d {shlex.quote(posixpath.dirname(request.deck))}/DFM && echo dfm_ok || echo dfm_missing; "
               if request.deck else "echo not_requested; ")
            + "true"
        )
        outcome = self.middle.run_command(cmd, timeout=request.timeout, token=request.token)
        steps.append({"name": "check", "ok": outcome.returncode == 0,
                      "detail": {"kind": outcome.kind, "stderr": (outcome.stderr or "")[:200]}})
        if outcome.returncode != 0:
            return Result(False, steps, _command_error("check_env", outcome), None)
        sections = _sections(outcome.stdout or "")
        path = sections.get("PATH", "").strip().splitlines()
        cpath = path[0].strip() if path and path[0].strip() and path[0].strip() != "NOTFOUND" else None
        value = {
            "calibre_path": cpath,
            "version": (sections.get("VERSION") or "").strip().splitlines()[:1],
            "deck_ok": None if "not_requested" in (sections.get("DECK") or "")
            else ("deck_file_missing" not in (sections.get("DECK") or "")),
            "deck_detail": (sections.get("DECK") or "").strip().splitlines(),
        }
        ok = _c_path_ok(value)
        return Result(ok, steps, None if ok else "calibre not found on PATH", value)

    # ------------------------------------------------------------------- run --
    def drc(self, request: RunRequest) -> Result:
        return self._run("drc", request)

    def lvs(self, request: RunRequest) -> Result:
        if not request.cdl:
            return Result(False, [], "lvs requires cdl (schematic source netlist)", None)
        return self._run("lvs", request)

    def pex(self, request: RunRequest) -> Result:
        if not request.cdl:
            return Result(False, [], "pex requires cdl (LVS source netlist)", None)
        if not request.lvs_run_dir:
            return Result(False, [], "pex requires lvs_run_dir (LVS results with svdb/)", None)
        return self._run("pex", request)

    def _run(self, kind: str, request: RunRequest) -> Result:
        started = time.monotonic()
        steps: list[dict[str, Any]] = []
        root = self._command_root(request.token, steps)
        if root is None:
            return Result(False, steps, "command role root unavailable", None)
        job_id = request.job_id or f"{kind}_{_slug(request.top)}"
        run_dir = request.run_dir or posixpath.join(root, "calibre", job_id)
        binary = self._calibre_bin(request.token, request.calibre_bin, steps)
        if binary is None:
            return Result(False, steps, _MISSING_FACTS, None)

        existing = self._status_snapshot(kind, run_dir, request.token, request.timeout)
        if existing and existing.process_alive:
            return Result(False, steps,
                          f"job already running in {run_dir}; use a new job_id or check status", None)

        deck_dir = posixpath.dirname(request.deck)
        stage_cmd = (
            f"rm -rf {shlex.quote(run_dir)} && mkdir -p {shlex.quote(run_dir)} && "
            f"cp -r {shlex.quote(deck_dir)}/. {shlex.quote(run_dir)}/"
        )
        # 拷贝 deck 目录（rcx 带 20 MB rules）可能超过默认 30 s，给足预算
        stage_timeout = request.timeout or 120
        stage = self.middle.run_command(stage_cmd, timeout=stage_timeout, token=request.token)
        if stage.kind == "unknown-effect":
            # 纯拷贝、幂等，可安全重试一次（对比 calibre 本体：绝不自作主张重试）
            steps.append({"name": "stage-deck-retry", "ok": True,
                          "detail": {"reason": "unknown-effect on idempotent copy"}})
            stage = self.middle.run_command(stage_cmd, timeout=stage_timeout, token=request.token)
        steps.append({"name": "stage-deck", "ok": stage.returncode == 0,
                      "detail": {"run_dir": run_dir, "deck_dir": deck_dir,
                                 "kind": stage.kind}})
        if stage.returncode != 0:
            return Result(False, steps, _command_error("stage deck", stage), None)

        if kind == "pex":
            svdb = posixpath.join(request.lvs_run_dir or "", "svdb")
            copy_svdb = self.middle.run_command(
                f"test -d {shlex.quote(svdb)} && cp -r {shlex.quote(svdb)} "
                f"{shlex.quote(run_dir)}/svdb",
                timeout=stage_timeout, token=request.token,
            )
            steps.append({"name": "stage-svdb", "ok": copy_svdb.returncode == 0,
                          "detail": {"from": svdb, "kind": copy_svdb.kind,
                                     "stderr": (copy_svdb.stderr or "")[:200]}})
            if copy_svdb.returncode != 0:
                return Result(False, steps,
                              f"pex needs LVS results: {svdb} not found/copyable", None)

        rewritten = self._rewrite_deck(request, kind, steps)
        if rewritten is None:
            return Result(False, steps, "deck rewrite failed", None)
        deck_text, changes = rewritten
        deck_remote = posixpath.join(run_dir, f"run_{kind}.cal")
        uploaded_deck = self._upload_text(deck_text, deck_remote, request.token, request.timeout)
        steps.append({"name": "upload-deck", "ok": uploaded_deck.returncode == 0,
                      "detail": {"remote": deck_remote, "kind": uploaded_deck.kind,
                                 "stderr": (uploaded_deck.stderr or "")[:200]}})
        if uploaded_deck.returncode != 0:
            return Result(False, steps, _command_error("upload deck", uploaded_deck), None)
        argv_list = _argv_for(kind, request, binary, run_dir, deck_text)
        meta = {
            "kind": kind, "run_dir": run_dir, "top": request.top, "gds": request.gds,
            "cdl": request.cdl, "deck": request.deck, "deck_sha256": cu.deck_sha256(deck_text),
            "deck_changes": changes, "turbo": request.turbo, "fmt": request.fmt,
        }
        launcher = cu.build_launcher(
            kind=kind, run_dir=run_dir, argv=argv_list[0],
            stages=argv_list if len(argv_list) > 1 else None,
            timeout=request.timeout, job_meta=meta,
        )
        uploaded = self._upload_text(launcher, posixpath.join(run_dir, "launch.sh"),
                                    request.token, request.timeout)
        steps.append({"name": "upload-launcher", "ok": uploaded.returncode == 0,
                      "detail": {"kind": uploaded.kind, "stderr": (uploaded.stderr or "")[:200]}})
        if uploaded.returncode != 0:
            return Result(False, steps, _command_error("upload launcher", uploaded), None)

        launched = self.middle.run_command(
            f"cd {shlex.quote(run_dir)} && chmod +x launch.sh && ./launch.sh >/dev/null 2>&1; "
            f"sleep 1; echo '###PID'; cat job.pid 2>/dev/null; echo '###PROC'; "
            f"pgrep -f {shlex.quote(run_dir)} | head -3",
            timeout=request.timeout, token=request.token,
        )
        steps.append({"name": "launch", "ok": launched.returncode == 0,
                      "detail": {"kind": launched.kind, "stdout": (launched.stdout or "")[:200]}})
        sections = _sections(launched.stdout or "")
        pid = (sections.get("PID") or "").strip().splitlines()
        alive = bool((sections.get("PROC") or "").strip())
        value = {"job_id": job_id, "run_dir": run_dir, "kind": kind,
                 "pid": int(pid[0]) if pid and pid[0].strip().isdigit() else None,
                 "status": "started" if alive else "unknown",
                 "deck_changes": changes, "elapsed_ms": int((time.monotonic() - started) * 1000)}
        if not request.blocking:
            return Result(True, steps, None, value)

        deadline = time.monotonic() + (request.timeout or 3600)
        last: dict[str, Any] = {}
        last_status = None
        while time.monotonic() < deadline:
            snapshot = self._status_snapshot(kind, run_dir, request.token, request.timeout)
            if snapshot is None:
                last = {"status": "unknown", "error": "status probe failed"}
            else:
                state = cu.job_state(kind, process_alive=snapshot.process_alive,
                                     log_tail=snapshot.log_tail, artifacts=snapshot.artifacts)
                last = {"status": state.status, "failure_kind": state.failure_kind,
                        "detail": state.detail, "log_tail": snapshot.log_tail[-800:]}
            if last.get("status") != last_status:
                steps.append({"name": "poll", "ok": True, "detail": last})
                last_status = last.get("status")
            if last.get("status") in ("completed", "failed"):
                break
            time.sleep(float(request.poll_interval))
        value.update({"status": last.get("status", "timeout"), "progress": last,
                      "elapsed_ms": int((time.monotonic() - started) * 1000)})
        ok = last.get("status") == "completed"
        error = None if ok else (f"{kind} did not complete: {last.get('status')} "
                                 f"{last.get('failure_kind') or ''}".strip())
        return Result(ok, steps, error, value)

    # ---------------------------------------------------------------- status --
    def status(self, request: StatusRequest) -> Result:
        steps: list[dict[str, Any]] = []
        run_dir = request.run_dir or self._run_dir_for(request.token, request.kind, request.job_id, steps)
        if run_dir is None:
            return Result(False, steps, "run_dir not resolvable", None)
        snapshot = self._status_snapshot(request.kind, run_dir, request.token, request.timeout)
        if snapshot is None:
            return Result(False, steps, f"cannot read job state in {run_dir}", None)
        state = cu.job_state(request.kind, process_alive=snapshot.process_alive,
                             log_tail=snapshot.log_tail, artifacts=snapshot.artifacts)
        steps.append({"name": "status", "ok": True,
                      "detail": {"status": state.status, "failure_kind": state.failure_kind}})
        value = {"run_dir": run_dir, "job_id": snapshot.job_json.get("job_id") or request.job_id,
                 "kind": request.kind, "status": state.status, "failure_kind": state.failure_kind,
                 "pid": snapshot.pid, "process_alive": snapshot.process_alive,
                 "artifacts": snapshot.artifacts, "log_tail": snapshot.log_tail[-800:]}
        return Result(True, steps, None, value)

    # ---------------------------------------------------------- read_results --
    def read_results(self, request: ReadResultsRequest) -> Result:
        steps: list[dict[str, Any]] = []
        kind = request.kind
        if kind is None:
            kind = self._detect_kind(request, steps)
        run_dir = request.run_dir or self._run_dir_for(request.token, kind, request.job_id, steps)
        if run_dir is None:
            return Result(False, steps, "run_dir not resolvable", None)

        report_rel = {"drc": ("DRC.rep",), "lvs": ("lvs.rep",),
                      "pex": ("pex.stage3.log", "pex.stage2.log",
                              "pex.stage1.log")}.get(kind, ())
        summary: dict[str, Any] = {}
        report_used: str | None = None
        for rel in report_rel:
            text = self._download_text(posixpath.join(run_dir, rel), request.token, request.timeout)
            if text is None:
                continue
            report_used = rel
            if kind == "drc":
                summary = cu.parse_drc_report(text, limit=request.limit)
            elif kind == "lvs":
                summary = cu.parse_lvs_report(text, limit=request.limit)
            else:
                summary = cu.parse_pex_log(text)
            break
        steps.append({"name": "parse", "ok": report_used is not None,
                      "detail": {"report": report_used, "kind": kind}})
        tail = self._log_tail(run_dir, request.token, request.log_lines, request.timeout)
        counters_text = self._log_counters(run_dir, request.token, request.timeout)
        counters = cu.parse_log_counters(counters_text)
        if kind == "drc":
            summary.setdefault("rules_checked", counters.get("rules_checked"))
            summary.setdefault("total_results", counters.get("total_results"))
            if summary.get("rules_checked") is None:
                summary["rules_checked"] = counters.get("rules_checked")
            if summary.get("total_results") is None:
                summary["total_results"] = counters.get("total_results")
        elif kind == "lvs" and counters.get("lvs_status"):
            summary["status"] = counters["lvs_status"]
        elif kind == "pex":
            if counters.get("pex_errors") is not None:
                summary["errors"] = counters["pex_errors"]
            if counters.get("pex_warnings") is not None:
                summary["warnings"] = counters["pex_warnings"]
        artifacts = self._list_artifacts(run_dir, request.token, request.timeout)
        value = {"kind": kind, "run_dir": run_dir, "summary": summary,
                 "report_used": report_used, "log_counters": counters,
                 "log_tail": tail, "artifacts": artifacts}
        if kind == "pex":
            if re.search(r"stage\d_failed", tail):
                return Result(False, steps, "pex stage failed", value)
            job_text = self._download_text(
                posixpath.join(run_dir, "job.json"),
                request.token, request.timeout,
            )
            if job_text:
                try:
                    job_meta = json.loads(job_text)
                except ValueError:
                    job_meta = {}
                fmt = job_meta.get("fmt")
                if fmt in ("spice", "simple") and not summary.get("netlist_files"):
                    return Result(False, steps,
                                  f"pex {fmt} produced no netlist file", value)
        if report_used is None:
            return Result(False, steps, f"no report found in {run_dir} for kind={kind}", value)
        return Result(True, steps, None, value)

    # ---------------------------------------------------------------- export --
    def export(self, request: ExportRequest) -> Result:
        steps: list[dict[str, Any]] = []
        kind = request.kind or self._detect_kind(request, steps)
        run_dir = request.run_dir or self._run_dir_for(request.token, kind, request.job_id, steps)
        if run_dir is None:
            return Result(False, steps, "run_dir not resolvable", None)
        target = Path(request.local_dir) if request.local_dir else artifact_dir() / "calibre"
        target.mkdir(parents=True, exist_ok=True)
        items = list(request.items)
        if "all_small" in items:
            items = ["summary", "results_db", "log"]
        downloaded: list[dict[str, Any]] = []
        for item in items:
            for rel in _EXPORT_ITEMS.get(item, ()):
                local = target / Path(rel).name
                outcome = self.middle.download_file(
                    posixpath.join(run_dir, rel), local, timeout=request.timeout,
                    token=request.token, recursive=rel.endswith("/") or rel == "svdb",
                )
                ok = outcome.returncode == 0
                steps.append({"name": f"download:{rel}", "ok": ok,
                              "detail": {"kind": outcome.kind, "stderr": (outcome.stderr or "")[:160]}})
                if ok:
                    downloaded.append({"item": item, "remote": rel, "local": str(local),
                                       "bytes": local.stat().st_size if local.is_file() else None})
        value = {"run_dir": run_dir, "local_dir": str(target), "downloaded": downloaded}
        return Result(bool(downloaded), steps, None if downloaded else "nothing downloaded", value)

    # ------------------------------------------------------------- 内部工具 --
    def _calibre_bin(self, token: str, override: str | None,
                     steps: list[dict[str, Any]]) -> str | None:
        """取 calibre 二进制：请求显式给 > 注册表 role.command.calibre.bin。**不探测、不回退**。"""
        if override:
            steps.append({"name": "calibre-bin", "ok": True,
                          "detail": {"source": "request", "bin": override}})
            return override
        try:
            query = self.middle.query(token=token)
        except Exception as exc:  # noqa: BLE001
            steps.append({"name": "calibre-bin", "ok": False, "detail": f"{type(exc).__name__}: {exc}"})
            return None
        role = (getattr(query, "roles", {}) or {}).get("command")
        group = _extra(role, _FACT_GROUP)
        bin_value = None
        if isinstance(group, dict):
            candidate = group.get("bin")
            bin_value = candidate if isinstance(candidate, str) and candidate.strip() else None
        steps.append({"name": "calibre-bin", "ok": bin_value is not None,
                      "detail": {"source": f"registry.role.command.{_FACT_GROUP}",
                                 "bin": bin_value}})
        return bin_value

    def _command_root(self, token: str, steps: list[dict[str, Any]]) -> str | None:
        try:
            query = self.middle.query(token=token)
        except Exception as exc:  # noqa: BLE001
            steps.append({"name": "query", "ok": False, "detail": f"{type(exc).__name__}: {exc}"})
            return None
        roles = getattr(query, "roles", {}) or {}
        command = roles.get("command")
        root = getattr(command, "root", None)
        steps.append({"name": "query", "ok": bool(root),
                      "detail": {"command_root": root,
                                 "calibre_bin": getattr(command, "bin", None)}})
        return root

    def _run_dir_for(self, token: str, kind: str, job_id: str | None,
                     steps: list[dict[str, Any]]) -> str | None:
        if not job_id:
            return None
        root = self._command_root(token, steps)
        if root is None:
            return None
        return posixpath.join(root, "calibre", job_id)

    def _rewrite_deck(self, request: RunRequest, kind: str,
                      steps: list[dict[str, Any]]) -> tuple[str, list[str]] | None:
        text = self._download_text(request.deck, request.token, request.timeout)
        if text is None:
            steps.append({"name": "read-deck", "ok": False, "detail": request.deck})
            return None
        rewritten, changes = cu.deck_rewrite(
            text, gds=request.gds, top=request.top, cdl=request.cdl
        )
        steps.append({"name": "rewrite-deck", "ok": True,
                      "detail": {"changes": changes, "sha256": cu.deck_sha256(rewritten)[:16]}})
        return rewritten, changes

    def _download_text(self, remote: str, token: str, timeout: int | None) -> str | None:
        exists = self.middle.run_command(
            f"test -f {shlex.quote(remote)} && echo yes || echo no", timeout=timeout, token=token
        )
        if "yes" not in (exists.stdout or ""):
            return None
        digest = hashlib.sha1(remote.encode("utf-8")).hexdigest()[:12]
        local = _staging_dir() / f"{digest}-{Path(remote).name}"
        outcome = self.middle.download_file(remote, local, timeout=timeout, token=token)
        if outcome.returncode != 0 or not local.is_file():
            return None
        return local.read_text(encoding="utf-8", errors="replace")

    def _upload_text(self, text: str, remote: str, token: str, timeout: int | None):
        local = _staging_dir() / Path(remote).name
        # 关键：Linux 侧脚本必须 LF 换行；Windows 默认写出 CRLF 会让 bash 报 $'\r'
        with open(local, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        return self.middle.upload_file(local, remote, timeout=timeout, token=token)

    def _status_snapshot(self, kind: str, run_dir: str, token: str,
                         timeout: int | None) -> cu.StatusSnapshot | None:
        cmd = (
            f"cd {shlex.quote(run_dir)} 2>/dev/null || exit 4; "
            "echo '###JOB'; cat job.json 2>/dev/null; "
            "echo '###PID'; cat job.pid 2>/dev/null; "
            "echo '###ALIVE'; pgrep -f " + shlex.quote(run_dir) + " | head -3; "
            "echo '###LOGS'; for f in *.log; do [ -f \"$f\" ] && { echo \"== $f\"; tail -n 40 \"$f\"; }; done; "
            "echo '###FILES'; ls -1 2>/dev/null | head -60; true"
        )
        outcome = self.middle.run_command(cmd, timeout=timeout, token=token)
        if outcome.returncode not in (0, 4) and outcome.kind != "command":
            return None
        sections = _sections(outcome.stdout or "")
        if not sections:
            return None
        pid_lines = (sections.get("PID") or "").strip().splitlines()
        artifacts = [line.strip() for line in (sections.get("FILES") or "").splitlines() if line.strip()]
        logs = sections.get("LOGS") or ""
        return cu.StatusSnapshot(
            job_json=cu.parse_job_json(sections.get("JOB") or ""),
            pid=int(pid_lines[0]) if pid_lines and pid_lines[0].strip().isdigit() else None,
            process_alive=bool((sections.get("ALIVE") or "").strip()),
            log_tail=logs[-4000:],
            artifacts=artifacts,
        )

    def _log_tail(self, run_dir: str, token: str, lines: int, timeout: int | None) -> str:
        if lines <= 0:
            return ""
        outcome = self.middle.run_command(
            f"cd {shlex.quote(run_dir)} 2>/dev/null && tail -n {int(lines)} *.log 2>/dev/null; true",
            timeout=timeout, token=token,
        )
        return (outcome.stdout or "")[-4000:]

    def _log_counters(self, run_dir: str, token: str, timeout: int | None) -> str:
        """只回传计数行（日志是 MB 级，不整份下载）。"""
        outcome = self.middle.run_command(
            f"cd {shlex.quote(run_dir)} 2>/dev/null && "
            "grep -hE 'TOTAL RULECHECKS EXECUTED|TOTAL RESULTS GENERATED|LVS completed\\.|"
            "xRC Errors|xRC Warnings' *.log 2>/dev/null | tail -10; true",
            timeout=timeout, token=token,
        )
        return outcome.stdout or ""

    def _list_artifacts(self, run_dir: str, token: str, timeout: int | None) -> list[str]:
        outcome = self.middle.run_command(
            f"cd {shlex.quote(run_dir)} 2>/dev/null && ls -1 2>/dev/null | head -60; true",
            timeout=timeout, token=token,
        )
        return [line.strip() for line in (outcome.stdout or "").splitlines() if line.strip()]

    def _detect_kind(self, request: Any, steps: list[dict[str, Any]]) -> str:
        run_dir = request.run_dir
        if run_dir:
            outcome = self.middle.run_command(
                f"cd {shlex.quote(run_dir)} 2>/dev/null && "
                "if [ -f lvs.rep ]; then echo lvs; elif [ -f DRC.rep ]; then echo drc; "
                "elif [ -f job.json ]; then head -c 200 job.json; fi; true",
                timeout=request.timeout, token=request.token,
            )
            text = (outcome.stdout or "").strip()
            if text in _KINDS:
                steps.append({"name": "detect-kind", "ok": True, "detail": text})
                return text
            for kind in _KINDS:
                if f'"{kind}"' in text:
                    steps.append({"name": "detect-kind", "ok": True, "detail": kind})
                    return kind
        steps.append({"name": "detect-kind", "ok": False, "detail": "assume drc"})
        return "drc"


def _argv_for(kind: str, request: RunRequest, binary: str, run_dir: str,
              deck_text: str) -> list[list[str]]:
    deck_path = posixpath.join(run_dir, f"run_{kind}.cal")
    flags = [binary, f"-{kind}"]
    if request.hier and kind == "drc":
        flags.append("-hier")
    if request.hier and kind == "lvs":
        flags.append("-hier")
    flags += ["-turbo", str(request.turbo)]
    if kind == "drc":
        return [flags + [deck_path]]
    if kind == "lvs":
        return [flags + [deck_path]]
    # pex：三阶段
    stage1 = [binary, "-xrc", "-phdb", "-turbo", str(request.turbo), deck_path]
    stage2 = [binary, "-xrc", "-pdb", "-rc", deck_path, "-turbo", str(request.turbo)]
    stages = [stage1, stage2]
    if request.fmt in ("spice", "simple"):
        stages.append([binary, "-xrc", "-fmt", request.fmt, deck_path])
    return stages


def _sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("###"):
            current = line[3:].strip()
            sections[current] = []
            continue
        if current is not None:
            sections[current].append(line)
    return {name: "\n".join(lines) for name, lines in sections.items()}


def _command_error(label: str, outcome: Any) -> str:
    detail = (getattr(outcome, "stderr", "") or "").strip()
    return f"{label} failed (kind={getattr(outcome, 'kind', '?')}, " \
           f"rc={getattr(outcome, 'returncode', '?')}): {detail[:300] or 'no stderr'}"


def _slug(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in text)
    return cleaned.strip("_") or "cell"


def _c_path_ok(value: dict[str, Any]) -> bool:
    return bool(value.get("calibre_path"))


def _extra(role: Any, name: str) -> Any:
    """从 query 的 role 事实里取用户组（pydantic extra="allow" 存 model_extra）。"""
    if role is None:
        return None
    value = getattr(role, name, None)
    if value is not None:
        return value
    extra = getattr(role, "model_extra", None) or {}
    return extra.get(name)


def _staging_dir() -> Path:
    """本地 staging：不用 TemporaryDirectory（实测该路径下 U/D 会报 VB-PATH-NOT-VISIBLE）。"""
    stage = artifact_dir() / "calibre" / "_stage"
    stage.mkdir(parents=True, exist_ok=True)
    return stage


OPERATIONS = (
    ("calibre.check_env", "check_env", CheckEnvRequest, Result),
    ("calibre.drc", "drc", RunRequest, Result),
    ("calibre.lvs", "lvs", RunRequest, Result),
    ("calibre.pex", "pex", RunRequest, Result),
    ("calibre.status", "status", StatusRequest, Result),
    ("calibre.read_results", "read_results", ReadResultsRequest, Result),
    ("calibre.export", "export", ExportRequest, Result),
)

__all__ = [
    "CheckEnvRequest",
    "ExportRequest",
    "OPERATION_NAMES",
    "OPERATIONS",
    "Package",
    "ReadResultsRequest",
    "Result",
    "RunRequest",
    "StatusRequest",
]
