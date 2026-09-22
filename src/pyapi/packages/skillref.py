"""``skillref`` business package: SKILL 参考查询（只读）。

两个业务操作（spec ``9-skillref.md`` Draft v9）：

* ``virtuoso.skillref.search`` —— 唯一搜索入口：一个 ``query`` + ``search_in``
  控制匹配范围（``name`` / ``entry`` / ``topic`` / ``body``，``all`` = ``body``）；
* ``virtuoso.skillref.info``   —— 按函数名取详细文档（tgf → 单个 HTML → Markdown）。

数据源由 ``source``（``local`` / ``remote``）+ ``doc_root`` 显式确定，不探测路径：

* 请求参数给的 ``source`` + ``doc_root`` 优先；
* 否则读 ``common.config`` 的进程级快照里的 ``skillref`` 段（``doc_token`` 只来自配置）；
* 都没有 -> 业务失败（不猜路径）。

本地模式直接读文件、不占用五个业务接口（仅一次只读 ``query`` 校验调用者 token）；
远端模式以配置的 ``doc_token`` 作为中层 token 执行 C/D。
"""
from __future__ import annotations

import hashlib
import math
import shlex
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common.paths import temp_dir
from pyapi.models import ExecutionStatus, Middle
from pyapi.packages import _skillref_docs as docs

#: spec 上层 §4.2：包级自描述
OPERATION_NAMES = (
    "virtuoso.skillref.search",
    "virtuoso.skillref.info",
)

_SEARCH_IN = ("name", "entry", "topic", "body")
_LAYER_ORDER = {"name": 0, "entry": 1, "topic": 2, "body": 3}
_BODY_TIMEOUT_DEFAULT = 120


# ---------------------------------------------------------------- 数据模型 --
@dataclass(frozen=True)
class SearchRequest:
    token: str
    query: str
    source: str | None = None
    doc_root: str | None = None
    search_in: str = "entry"
    mode: str = "fuzzy"
    under: list[str] | None = None
    limit: int = 20
    max_candidates: int = 50
    max_files: int = 5000
    snippet: bool = True
    timeout: int | None = None

    def __post_init__(self) -> None:
        _require_token(self.token)
        _require_text(self.query, "query")
        _require_choice(self.source, "source", ("local", "remote"))
        _require_text_or_none(self.doc_root, "doc_root")
        _require_choice(self.search_in, "search_in", _SEARCH_IN + ("all",))
        _require_choice(self.mode, "mode", docs.MODES)
        _require_under(self.under)
        _require_int_range(self.limit, "limit", 1, 200)
        _require_int_range(self.max_candidates, "max_candidates", 1, 500)
        _require_int_range(self.max_files, "max_files", 1, 200_000)
        _require_bool(self.snippet, "snippet")
        _require_timeout(self.timeout)


@dataclass(frozen=True)
class InfoRequest:
    token: str
    name: str
    source: str | None = None
    doc_root: str | None = None
    include_raw: bool = False
    timeout: int | None = None

    def __post_init__(self) -> None:
        _require_token(self.token)
        _require_text(self.name, "name")
        _require_choice(self.source, "source", ("local", "remote"))
        _require_text_or_none(self.doc_root, "doc_root")
        _require_bool(self.include_raw, "include_raw")
        _require_timeout(self.timeout)


@dataclass
class SearchResult:
    ok: bool
    steps: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    query: str = ""
    search_in: str = ""
    results: list[dict[str, Any]] = field(default_factory=list)
    layers_run: list[str] = field(default_factory=list)
    scanned_files: int = 0
    truncated: bool = False
    doc_root: str | None = None
    source: str | None = None
    elapsed_ms: int = 0


@dataclass
class InfoResult:
    ok: bool
    steps: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    found: bool = False
    func_name: str | None = None
    file_path: str | None = None
    topic: str | None = None
    plain_text: str = ""
    raw_html: str | None = None
    doc_root: str | None = None
    source: str | None = None


# ------------------------------------------------------------------ 校验器 --
def _require_token(token: Any) -> str:
    if not isinstance(token, str) or not token:
        raise ValueError("token must be a non-empty string")
    return token


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_text_or_none(value: Any, name: str) -> None:
    if value is None:
        return
    text = _require_text(value, name)
    if "\x00" in text:
        raise ValueError(f"{name} must not contain NUL")


def _require_choice(value: Any, name: str, allowed: tuple[str, ...]) -> None:
    if value is None:
        return
    if not isinstance(value, str) or value.lower() not in allowed:
        raise ValueError(f"{name} must be one of {allowed}")


def _require_under(value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, list) or not value:
        raise ValueError("under must be a non-empty list of relative directories")
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("under entries must be non-empty strings")
        if item.startswith(("/", "\\")) or ".." in Path(item).parts or "\x00" in item:
            raise ValueError(f"under entry must be a relative path without '..': {item!r}")


def _require_int_range(value: Any, name: str, low: int, high: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in [{low}, {high}]")


def _require_bool(value: Any, name: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")


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


# ------------------------------------------------------------ 配置表快照 --
def _config_snapshot() -> dict[str, Any] | None:
    """读顶层提供的进程级只读配置快照（``common.config``）。

    用 ``common.config.snapshot_dict()``；模块不可用时返回 ``None``
    （配置表路径在步骤痕迹里标注为不可用），
    此时只接受请求参数给出的 ``source`` + ``doc_root``。
    """
    try:
        from common.config import snapshot_dict
    except Exception:
        return None
    try:
        return dict(snapshot_dict())
    except Exception:
        return None


@dataclass(frozen=True)
class _Source:
    source: str
    doc_root: str
    doc_token: str | None
    origin: str


class Package:
    """skillref：只读查询包（构造只接受 ``Middle``）。"""

    def __init__(self, middle: Middle) -> None:
        self.middle = middle

    # -------------------------------------------------------------- search --
    def search(self, request: SearchRequest) -> SearchResult:
        started = time.monotonic()
        steps: list[dict[str, Any]] = []
        query = request.query.strip()
        search_in = "body" if request.search_in.lower() == "all" else request.search_in.lower()
        mode = request.mode.lower()
        # search_in 是累积的：topic 含词条层，body 含 topic 层（spec §4.2）
        layers = ["name", "entry", "topic", "body"][: _LAYER_ORDER[search_in] + 1]
        entry_scope = "name" if search_in == "name" else "entry"

        result = SearchResult(
            ok=False,
            query=query,
            search_in=search_in,
            layers_run=layers,
        )

        if not self._authorize(request.token, steps, result):
            return self._finish(result, steps, started)

        source = self._resolve_source(
            request.source, request.doc_root, steps, result, require_token_for="remote"
        )
        if source is None:
            return self._finish(result, steps, started)
        result.source = source.source
        result.doc_root = source.doc_root

        self._stage_reset(source)
        try:
            finder_root = self._ensure_finder(source, steps, result)
            if finder_root is None:
                return self._finish(result, steps, started)
            entries = docs.parse_fnd_directory(finder_root)
            if not entries:
                result.error = f"未在 {finder_root} 下解析到任何 .fnd 词条"
                steps.append({"name": "parse-fnd", "ok": False, "detail": result.error})
                return self._finish(result, steps, started)
            steps.append({"name": "parse-fnd", "ok": True,
                          "detail": {"entries": len(entries)}})

            hits: list[dict[str, Any]] = docs.search_entries(
                entries, query, mode=mode, search_in=entry_scope
            )

            if search_in in ("topic", "body"):
                topics, topic_hits = self._search_topics(source, query, mode, steps, result)
                if topics is None:
                    return self._finish(result, steps, started)
                hits.extend(topic_hits)

            if search_in == "body":
                body_hits, scanned, truncated = self._search_body(
                    source, query, request, steps, result
                )
                if body_hits is None:
                    return self._finish(result, steps, started)
                hits.extend(body_hits)
                result.scanned_files = scanned
                result.truncated = truncated

            ordered = _order_and_dedup(hits)
            trimmed = ordered[: request.limit]
            if not request.snippet:
                for hit in trimmed:
                    hit.pop("snippet", None)
            result.results = trimmed
            result.ok = True
            steps.append({"name": "match", "ok": True,
                          "detail": {"hits": len(ordered), "returned": len(trimmed)}})
        except Exception as exc:  # noqa: BLE001 - 单次请求隔离
            result.error = f"{type(exc).__name__}: {exc}"
            steps.append({"name": "search", "ok": False, "detail": result.error})
        return self._finish(result, steps, started)

    # ---------------------------------------------------------------- info --
    def info(self, request: InfoRequest) -> InfoResult:
        steps: list[dict[str, Any]] = []
        name = request.name.strip()
        result = InfoResult(ok=False)

        if not self._authorize(request.token, steps, result):
            return result

        source = self._resolve_source(
            request.source, request.doc_root, steps, result, require_token_for="remote"
        )
        if source is None:
            return result
        result.source = source.source
        result.doc_root = source.doc_root

        self._stage_reset(source)
        try:
            tgf_path = self._ensure_tgf(source, steps, result)
            if tgf_path is None:
                return result
            index = docs.parse_tgf_index(tgf_path)
            steps.append({"name": "parse-tgf", "ok": bool(index),
                          "detail": {"topics": len(index)}})
            if not index:
                result.error = f"{tgf_path} 未解析到任何主题条目"
                return result

            entry = docs.lookup_topic(index, name)
            if entry is None:
                result.ok = True
                result.found = False
                steps.append({"name": "lookup", "ok": True,
                              "detail": {"found": False, "name": name}})
                return result
            result.func_name = entry.func_name
            result.file_path = entry.file_path
            result.topic = entry.topic

            html_path = self._ensure_html(source, tgf_path, entry.file_path, steps, result)
            if html_path is None:
                return result
            content = docs.read_text(html_path)
            single_func_file = sum(
                1 for item in index.values() if item.file_path == entry.file_path
            ) == 1
            section = docs.extract_doc_section(
                content,
                entry.topic or entry.func_name,
                fallback_whole_file=entry.topic is None or single_func_file,
            )
            steps.append({"name": "extract", "ok": section is not None,
                          "detail": {"topic": entry.topic, "fallback": entry.topic is None}})
            if section is None:
                result.ok = True
                result.found = False
                steps.append({"name": "lookup", "ok": True,
                              "detail": {"found": False, "reason": "topic 未在目标 HTML 中定位"}})
                return result

            result.plain_text = docs.html_to_markdown(section)
            if request.include_raw:
                result.raw_html = section
            result.ok = True
            result.found = True
            steps.append({"name": "markdown", "ok": bool(result.plain_text),
                          "detail": {"chars": len(result.plain_text)}})
        except Exception as exc:  # noqa: BLE001 - 单次请求隔离
            result.error = f"{type(exc).__name__}: {exc}"
            steps.append({"name": "info", "ok": False, "detail": result.error})
        return result

    # ------------------------------------------------------- 步骤：鉴权等 ---
    def _authorize(self, token: str, steps: list[dict[str, Any]], result: Any) -> bool:
        try:
            query = self.middle.query(token=token)
        except Exception as exc:  # noqa: BLE001 - 单次请求隔离
            result.error = f"调用者 token 校验失败: {type(exc).__name__}: {exc}"
            steps.append({"name": "authorize", "ok": False, "detail": result.error})
            return False
        ok = getattr(query, "status", None) == ExecutionStatus.SUCCESS
        steps.append({"name": "authorize", "ok": ok,
                      "detail": {"status": getattr(query, "status", None)}})
        if not ok:
            errors = getattr(query, "errors", None) or []
            result.error = "invalid token: " + ("; ".join(errors) or "调用者 token 无效")
        return ok

    def _resolve_source(
        self,
        source: str | None,
        doc_root: str | None,
        steps: list[dict[str, Any]],
        result: Any,
        *,
        require_token_for: str,
    ) -> _Source | None:
        snapshot_available = True
        snapshot = _config_snapshot()
        if snapshot is None:
            snapshot_available = False
            snapshot = {}
        section = snapshot.get("skillref") or {}

        if source and doc_root:
            resolved = _Source(source.lower(), doc_root, section.get("doc_token"), "request")
        elif source or doc_root:
            result.error = "请求参数需同时给出 source 与 doc_root（或都留给配置表）"
            steps.append({"name": "resolve-source", "ok": False, "detail": result.error})
            return None
        elif section.get("source") and section.get("doc_root"):
            resolved = _Source(
                str(section["source"]).lower(),
                str(section["doc_root"]),
                section.get("doc_token"),
                "config",
            )
        else:
            hint = "" if snapshot_available else "（common.config 尚未落地，只能由请求参数给出）"
            result.error = (
                "skillref 数据源未配置：请在 config.json 的 skillref 段给出 "
                f"source + doc_root（remote 模式另需 doc_token），或由请求参数给出 source + doc_root{hint}"
            )
            steps.append({"name": "resolve-source", "ok": False, "detail": result.error})
            return None

        if resolved.source not in ("local", "remote"):
            result.error = f"source 必须是 local 或 remote，收到 {resolved.source!r}"
            steps.append({"name": "resolve-source", "ok": False, "detail": result.error})
            return None
        if not Path(resolved.doc_root).is_absolute() and _looks_like_windows_path(resolved.doc_root):
            pass  # Windows 绝对路径（C:\...）在非 Windows 上 Path 判定不同，这里放行
        if resolved.source == require_token_for and not resolved.doc_token:
            result.error = (
                "remote 模式需要查询代理账号：请在 config.json 的 "
                "skillref.doc_token 配置一个已注册 user 的 token"
            )
            steps.append({"name": "resolve-source", "ok": False, "detail": result.error})
            return None

        steps.append({"name": "resolve-source", "ok": True, "detail": {
            "source": resolved.source,
            "doc_root": resolved.doc_root,
            "origin": resolved.origin,
            "doc_token": "configured" if resolved.doc_token else None,
        }})
        return resolved

    # ------------------------------------------------------------ 取数：本地 --
    def _stage_reset(self, source: _Source) -> None:
        if source.source != "remote":
            return
        stage = _stage_dir(source.doc_root)
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)

    def _ensure_finder(
        self, source: _Source, steps: list[dict[str, Any]], result: Any
    ) -> Path | None:
        if source.source == "local":
            root = Path(source.doc_root).joinpath(*docs.FINDER_TAIL)
            if not root.is_dir():
                result.error = f"本地 doc_root 下未找到 finder/SKILL：{root}"
                steps.append({"name": "fetch-fnd", "ok": False, "detail": result.error})
                return None
            steps.append({"name": "fetch-fnd", "ok": True,
                          "detail": {"mode": "local", "root": str(root)}})
            return root
        remote_root = _posix_join(source.doc_root, *docs.FINDER_TAIL)
        local_root = _stage_dir(source.doc_root).joinpath(*docs.FINDER_TAIL)
        outcome = self.middle.download_file(
            remote_root, local_root, timeout=None, token=source.doc_token, recursive=True
        )
        if not self._transfer_ok(outcome, "fetch-fnd", steps, result, source):
            return None
        steps[-1]["detail"].update({"mode": "remote", "remote": remote_root})
        return local_root

    def _ensure_tgf(
        self, source: _Source, steps: list[dict[str, Any]], result: Any
    ) -> Path | None:
        if source.source == "local":
            path = Path(source.doc_root).joinpath(*docs.TGF_REL)
            if not path.is_file():
                result.error = f"本地 doc_root 下未找到 api_more_info.tgf：{path}"
                steps.append({"name": "fetch-tgf", "ok": False, "detail": result.error})
                return None
            steps.append({"name": "fetch-tgf", "ok": True,
                          "detail": {"mode": "local", "path": str(path)}})
            return path
        remote_path = _posix_join(source.doc_root, *docs.TGF_REL)
        local_path = _stage_dir(source.doc_root).joinpath(*docs.TGF_REL)
        outcome = self.middle.download_file(
            remote_path, local_path, timeout=None, token=source.doc_token
        )
        if not self._transfer_ok(outcome, "fetch-tgf", steps, result, source):
            return None
        steps[-1]["detail"].update({"mode": "remote", "remote": remote_path})
        return local_path

    def _ensure_html(
        self,
        source: _Source,
        tgf_path: Path,
        file_path: str,
        steps: list[dict[str, Any]],
        result: Any,
    ) -> Path | None:
        relative = file_path.lstrip("$")
        if source.source == "local":
            path = Path(source.doc_root) / relative
            if not path.is_file():
                result.error = f"主题指向的 HTML 不存在：{path}"
                steps.append({"name": "fetch-html", "ok": False, "detail": result.error})
                return None
            steps.append({"name": "fetch-html", "ok": True,
                          "detail": {"mode": "local", "path": str(path)}})
            return path
        remote_path = _posix_join(source.doc_root, relative)
        local_path = _stage_dir(source.doc_root) / relative
        outcome = self.middle.download_file(
            remote_path, local_path, timeout=None, token=source.doc_token
        )
        if not self._transfer_ok(outcome, "fetch-html", steps, result, source):
            return None
        steps[-1]["detail"].update({"mode": "remote", "remote": remote_path})
        return local_path

    def _transfer_ok(
        self,
        outcome: Any,
        step_name: str,
        steps: list[dict[str, Any]],
        result: Any,
        source: _Source,
    ) -> bool:
        returncode = getattr(outcome, "returncode", 1)
        kind = getattr(outcome, "kind", "command")
        stderr = (getattr(outcome, "stderr", "") or "").strip()
        steps.append({"name": step_name, "ok": returncode == 0, "detail": {
            "returncode": returncode, "kind": kind, "stderr": stderr[:400],
        }})
        if returncode == 0:
            return True
        if kind == "invalid-token":
            result.error = (
                "skillref.doc_token 无效或已删除（中层返回 kind=invalid-token）："
                "请在 config.json 的 skillref.doc_token 换成已注册 user 的 token"
            )
        else:
            result.error = f"{step_name} 失败（kind={kind}, rc={returncode}）：{stderr or 'no stderr'}"
        return False

    # ------------------------------------------------------------ 取数：主题 --
    def _search_topics(
        self,
        source: _Source,
        query: str,
        mode: str,
        steps: list[dict[str, Any]],
        result: Any,
    ) -> tuple[dict[str, docs.TopicEntry] | None, list[dict[str, Any]]]:
        tgf_path = self._ensure_tgf(source, steps, result)
        if tgf_path is None:
            return None, []
        index = docs.parse_tgf_index(tgf_path)
        steps.append({"name": "parse-tgf", "ok": bool(index),
                      "detail": {"topics": len(index)}})
        hits: list[dict[str, Any]] = []
        for entry in index.values():
            score, why = docs.topic_matches(entry, query, mode)
            if not score:
                continue
            hits.append({
                "layer": "topic",
                "score": score,
                "name": entry.func_name,
                "topic": entry.topic,
                "target_path": entry.file_path,
                "relative_path": entry.file_path.lstrip("$"),
                "why": why,
                "dedup_key": ("topic", entry.file_path, entry.topic),
            })
        return index, hits

    # ------------------------------------------------------------ 取数：正文 --
    def _search_body(
        self,
        source: _Source,
        query: str,
        request: SearchRequest,
        steps: list[dict[str, Any]],
        result: Any,
    ) -> tuple[list[dict[str, Any]] | None, int, bool]:
        terms = docs.query_terms(query)
        if not terms:
            return [], 0, False
        if source.source == "local":
            return self._search_body_local(source, terms, request, steps, result)
        return self._search_body_remote(source, terms, request, steps, result)

    def _search_body_local(
        self,
        source: _Source,
        terms: list[str],
        request: SearchRequest,
        steps: list[dict[str, Any]],
        result: Any,
    ) -> tuple[list[dict[str, Any]] | None, int, bool]:
        root = Path(source.doc_root)
        if not root.is_dir():
            result.error = f"本地 doc_root 不可见：{root}"
            steps.append({"name": "body-scan", "ok": False, "detail": result.error})
            return None, 0, False
        if not request.under:
            steps.append({"name": "body-scan-note", "ok": True, "detail": {
                "note": "未给 under：本地模式将整树扫描，受 max_files 限制"
                        f"（max_files={request.max_files}）",
            }})
        files, truncated = docs.iter_body_files(root, request.under, request.max_files)
        hits: list[dict[str, Any]] = []
        for path in files:
            raw = docs.read_text(path)
            if not raw:
                continue
            text = docs.html_to_text(raw) if path.suffix.lower() in (".html", ".htm") else raw
            if not docs.matches_all_terms(text, terms):
                continue
            relative = path.relative_to(root).as_posix()
            title = docs.html_title(raw) if path.suffix.lower() in (".html", ".htm") else path.stem
            hits.append({
                "layer": "body",
                "score": docs.body_score(title, relative, text, terms),
                "title": title,
                "relative_path": relative,
                "line": docs.first_match_line(text, terms),
                "snippet": docs.make_snippet(text, terms),
                "why": ["body"],
                "dedup_key": ("body", relative),
            })
        steps.append({"name": "body-scan", "ok": True, "detail": {
            "mode": "local", "files": len(files), "hits": len(hits), "truncated": truncated}})
        return hits, len(files), truncated

    def _search_body_remote(
        self,
        source: _Source,
        terms: list[str],
        request: SearchRequest,
        steps: list[dict[str, Any]],
        result: Any,
    ) -> tuple[list[dict[str, Any]] | None, int, bool]:
        command = _body_grep_command(source.doc_root, request.under, terms, request.max_candidates)
        timeout = request.timeout or _BODY_TIMEOUT_DEFAULT
        outcome = self.middle.run_command(command, timeout=timeout, token=source.doc_token)
        returncode = getattr(outcome, "returncode", 1)
        if returncode != 0:
            ok = self._transfer_ok(outcome, "body-grep", steps, result, source)
            return None if not ok else [], 0, False
        candidates = [
            line.strip().lstrip("./")
            for line in (getattr(outcome, "stdout", "") or "").splitlines()
            if line.strip()
        ]
        truncated = len(candidates) >= request.max_candidates
        steps.append({"name": "body-grep", "ok": True, "detail": {
            "mode": "remote", "candidates": len(candidates), "truncated": truncated}})

        hits: list[dict[str, Any]] = []
        download_cap = min(request.max_candidates, max(request.limit * 2, 1))
        for index, relative in enumerate(candidates[:download_cap], 1):
            remote_path = _posix_join(source.doc_root, relative)
            local_path = _stage_dir(source.doc_root) / "body" / f"{index:03d}-{Path(relative).name}"
            outcome_one = self.middle.download_file(
                remote_path, local_path, timeout=request.timeout, token=source.doc_token
            )
            if getattr(outcome_one, "returncode", 1) != 0:
                if not self._transfer_ok(outcome_one, "body-fetch", steps, result, source):
                    return None, 0, truncated
                continue
            raw = docs.read_text(local_path)
            text = docs.html_to_text(raw) if local_path.suffix.lower() in (".html", ".htm") else raw
            if not docs.matches_all_terms(text, terms):
                continue
            title = docs.html_title(raw) if local_path.suffix.lower() in (".html", ".htm") else local_path.stem
            hits.append({
                "layer": "body",
                "score": docs.body_score(title, relative, text, terms),
                "title": title,
                "relative_path": relative,
                "line": docs.first_match_line(text, terms),
                "snippet": docs.make_snippet(text, terms),
                "why": ["body"],
                "dedup_key": ("body", relative),
            })
            if len(hits) >= request.limit:
                break
        steps.append({"name": "body-fetch", "ok": True, "detail": {
            "downloaded": len(candidates[:download_cap]), "hits": len(hits)}})
        return hits, len(candidates), truncated

    # -------------------------------------------------------------- 收尾 --
    @staticmethod
    def _finish(result: Any, steps: list[dict[str, Any]], started: float) -> Any:
        result.steps = steps
        if hasattr(result, "elapsed_ms"):
            result.elapsed_ms = int((time.monotonic() - started) * 1000)
        if not result.ok and result.error is None:
            result.error = "skillref 操作失败"
        return result


# ------------------------------------------------------------------ 工具函数 --
def _stage_dir(doc_root: str) -> Path:
    digest = hashlib.sha1(doc_root.encode("utf-8")).hexdigest()[:12]
    return temp_dir() / "skillref" / digest


def _posix_join(*parts: str) -> str:
    cleaned = [part.strip("/") for part in parts if part]
    if not cleaned:
        return "/"
    head = parts[0]
    prefix = "/" if head.startswith("/") else ""
    return prefix + "/".join(cleaned)


def _looks_like_windows_path(path: str) -> bool:
    return len(path) > 2 and path[1] == ":" and path[2] in ("\\", "/")


def _body_grep_command(
    doc_root: str,
    under: list[str] | None,
    terms: list[str],
    max_candidates: int,
) -> str:
    """一次远端候选搜索：先按最长（通常最稀有）词过滤，再 AND 其余词。"""
    ordered = sorted(terms, key=len, reverse=True)
    includes = " ".join(
        f"--include={shlex.quote('*' + suffix)}" for suffix in docs.BODY_SUFFIXES
    )
    targets = " ".join(shlex.quote(f"./{item}") for item in under) if under else "."
    head_cap = max(max_candidates * 5, 50)
    pipeline = (
        f"grep -r -l -m1 -F -e {shlex.quote(ordered[0])} {includes} -- {targets} 2>/dev/null"
        f" | head -n {head_cap}"
    )
    if len(ordered) > 1:
        others = " ".join(f"-e {shlex.quote(term)}" for term in ordered[1:])
        pipeline += (
            f" | xargs -r -d '\\n' grep -l -F {others} 2>/dev/null"
            f" | head -n {max_candidates}"
        )
    else:
        pipeline += f" | head -n {max_candidates}"
    return f"cd {shlex.quote(doc_root)} && {pipeline}"


def _order_and_dedup(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """合并同一逻辑位置的多层命中，再按 层序 + 分数 + 名字/路径 排序。"""
    best: dict[Any, dict[str, Any]] = {}
    for hit in hits:
        key = hit.get("dedup_key") or (hit.get("layer"), hit.get("name") or hit.get("relative_path"))
        current = best.get(key)
        if current is None:
            best[key] = hit
            continue
        keep, other = (
            (current, hit)
            if _LAYER_ORDER[current["layer"]] <= _LAYER_ORDER[hit["layer"]]
            else (hit, current)
        )
        keep["score"] = max(keep.get("score", 0), other.get("score", 0))
        for reason in other.get("why", []):
            if reason not in keep.setdefault("why", []):
                keep["why"].append(reason)
        for field in ("snippet", "line", "title", "target_path", "relative_path"):
            if not keep.get(field) and other.get(field):
                keep[field] = other[field]
        best[key] = keep
    ordered = sorted(
        best.values(),
        key=lambda hit: (
            _LAYER_ORDER.get(hit.get("layer", "body"), 9),
            -int(hit.get("score", 0)),
            str(hit.get("name") or hit.get("relative_path") or ""),
        ),
    )
    for hit in ordered:
        hit.pop("dedup_key", None)
    return ordered


#: 操作名 -> (方法名, Request 模型, Result 模型)
OPERATIONS = (
    ("virtuoso.skillref.search", "search", SearchRequest, SearchResult),
    ("virtuoso.skillref.info", "info", InfoRequest, InfoResult),
)

__all__ = [
    "InfoRequest",
    "InfoResult",
    "OPERATION_NAMES",
    "OPERATIONS",
    "Package",
    "SearchRequest",
    "SearchResult",
]
