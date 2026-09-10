# -*- coding: utf-8 -*-
"""SKILL 函数离线查询 Web 服务 — 自包含实现(stdlib only)。

不依赖 virtuoso_bridge 包 / Virtuoso daemon / SSH,只读本地 Cadence 文档树:
  doc/
    finder/SKILL/...     .fnd 函数索引(名称/语法/描述)
    api_more_info/...    More Info 索引(.tgf) + HTML 详细文档

本文件内联了 virtuoso_bridge 中用到的最小依赖子集:
  - skill_finder.parser     -> .fnd 解析(下文 "parser" 节)
  - skill_finder            -> SKILLFinder 搜索(下文 "finder" 节)
  - skill_finder.more_info  -> .tgf 索引 + HTML topic 抽取(下文 "more-info" 节)
  - markdownify(第三方库)    -> 用 stdlib HTMLParser 重写的轻量 HTML->Markdown

用法:
    python skill_doc_server.py [--doc <doc root>] [--host 127.0.0.1] [--port 8123]
浏览器打开 http://127.0.0.1:<port> 即可查询。

API 说明见 GET /api/help。
"""
from __future__ import annotations

import argparse
import json
import re
import threading
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DEFAULT_DOC = Path(r"C:\Users\user\Desktop\doc")
MODES = ("fuzzy", "prefix", "suffix", "exact", "regex")
LOG_LOCK = threading.Lock()

# ==========================================================================
# 后端(内联自 virtuoso_bridge 的最小依赖子集)
# ==========================================================================

# -------------------------------------------------------------- .fnd 解析 --
# 原: virtuoso_bridge/virtuoso/skill_finder/parser.py
# 文件格式(每个条目 3 行):
#   ("functionName"
#   "syntaxString"
#   "Description.")
# 以 ``;`` 开头的行是注释。

_ENTRY_PATTERN = re.compile(
    r'\("([^"]+)"\s*\n\s*"((?:[^"\\]|\\.)*)"\s*\n\s*"((?:[^"\\]|\\.)*)"\s*\)',
    re.DOTALL,
)


@dataclass
class SkillEntry:
    """单条 SKILL API 条目(解析自 .fnd 文件)。"""

    name: str
    syntax: str
    description: str
    source_file: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "syntax": self.syntax,
            "description": self.description,
            "source_file": self.source_file,
        }


def parse_fnd_file(path: Path) -> list[SkillEntry]:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    lines = [line for line in content.splitlines() if not line.startswith(";")]
    normalized = "\n".join(lines)

    entries: list[SkillEntry] = []
    for m in _ENTRY_PATTERN.finditer(normalized):
        name = m.group(1).strip()
        syntax = m.group(2).strip()
        description = m.group(3).strip()
        if name and syntax:
            entries.append(
                SkillEntry(
                    name=name,
                    syntax=syntax,
                    description=description,
                    source_file=path.name,
                )
            )
    return entries


def parse_fnd_directory(root: Path) -> list[SkillEntry]:
    """递归解析 root 下所有 .fnd,按函数名去重(先出现者胜)。"""
    all_entries: list[SkillEntry] = []
    seen: set[str] = set()
    if not root.exists():
        return []
    for fnd_file in root.rglob("*.fnd"):
        for entry in parse_fnd_file(fnd_file):
            if entry.name not in seen:
                seen.add(entry.name)
                all_entries.append(entry)
    return all_entries


# ------------------------------------------------------------- 搜索逻辑 ----
# 原: virtuoso_bridge/virtuoso/skill_finder/__init__.py 的 search() 部分

class SKILLFinder:
    """基于 .fnd 文件的 SKILL 函数搜索(仅本地加载 + 搜索子集)。"""

    def __init__(self) -> None:
        self.entries: list[SkillEntry] = []
        self.loaded = False

    def load(self, source_dir: Path | str) -> None:
        self.entries = parse_fnd_directory(Path(source_dir))
        self.loaded = True

    def search(
        self,
        query: str,
        *,
        mode: str = "fuzzy",
        limit: int = 50,
        include_desc: bool = False,
    ) -> list[SkillEntry]:
        if not self.loaded:
            return []
        if mode not in MODES:
            mode = "fuzzy"

        if mode == "exact":
            results = [e for e in self.entries if e.name == query]
        elif mode == "prefix":
            ql = query.lower()
            results = [e for e in self.entries
                       if e.name.startswith(query)
                       or (include_desc and ql in e.description.lower())]
        elif mode == "suffix":
            ql = query.lower()
            results = [e for e in self.entries
                       if e.name.endswith(query)
                       or (include_desc and ql in e.description.lower())]
        elif mode == "regex":
            try:
                pattern = re.compile(query, re.IGNORECASE)
            except re.error:
                return []
            results = [e for e in self.entries
                       if pattern.search(e.name)
                       or (include_desc and pattern.search(e.description))]
        else:  # fuzzy
            q = query.lower()
            results = [e for e in self.entries
                       if q in e.name.lower()
                       or (include_desc and q in e.description.lower())]

        return sorted(results, key=lambda e: e.name)[:limit]


# ----------------------------------------------------- More Info 索引/抽取 --
# 原: virtuoso_bridge/virtuoso/skill_finder/more_info.py
# More Info 系统 = api_more_info.tgf 索引 + 带 topic 标记的 HTML 文件。

_TGF_QUOTED = re.compile(r"^(\S+)\s+(\S+)\s+\"([^\"]+)\"\s+(\S+)$")
_TGF_NULL = re.compile(r"^(\S+)\s+(\S+)\s+(NULL)\s+(\S+)$", re.IGNORECASE)

_TOPIC_START = re.compile(r"<!--\s*\[TOPIC_START_OPEN\](.*?)-->", re.DOTALL)
_TOPIC_END = "<!-- [TOPIC_END] -->"
_TOPIC_TEXT = re.compile(r"\[TOPIC_START_ATTR\]text=([^\n]+)", re.IGNORECASE)

# Legacy(非 More Info 的 webflare HTML):每函数一个 <h1..h6> 小节。
_HEADING_OPEN = re.compile(r"<h([1-6])(?=[\s>])", re.IGNORECASE)
_HEADING_BLOCK = re.compile(
    r"<h([1-6])[^>]*>(.*?)</h\1>", re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_WS_RUN = re.compile(r"\s+")


@dataclass
class MoreInfoEntry:
    func_name: str
    file_path: str
    topic: str | None
    format: str


def parse_tgf_index(tgf_path: Path) -> dict[str, MoreInfoEntry]:
    entries: dict[str, MoreInfoEntry] = {}
    try:
        content = tgf_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return entries
    for line in content.splitlines():
        line = line.strip().strip("\r")
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        m = _TGF_QUOTED.match(line)
        if m:
            fn, fp, topic, fmt = m.group(1), m.group(2), m.group(3), m.group(4)
        else:
            m = _TGF_NULL.match(line)
            if not m:
                continue
            fn, fp, topic, fmt = m.group(1), m.group(2), m.group(3), m.group(4)
        if topic.upper() == "NULL":
            topic = None
        key = fn.lower()
        if key not in entries:
            entries[key] = MoreInfoEntry(
                func_name=fn, file_path=fp, topic=topic, format=fmt)
    return entries


def resolve_doc_path(tgf_path: Path, relative_path: str) -> Path:
    rel = relative_path.lstrip("$")
    return tgf_path.parent.parent / rel


def extract_topic_from_html(html_content: str, topic_name: str) -> str | None:
    """现代 More Info 文件:按 TOPIC_START_OPEN/TOPIC_END 标记抽取。"""
    for match in _TOPIC_START.finditer(html_content):
        block_start = match.start()
        text_match = _TOPIC_TEXT.search(match.group(1))
        if text_match and text_match.group(1).strip() == topic_name:
            end_pos = html_content.find(_TOPIC_END, block_start)
            if end_pos != -1:
                tag_end = html_content.find("-->", block_start)
                return html_content[tag_end + 3:end_pos].strip()
    return None


def _plain_heading_text(fragment: str) -> str:
    return _WS_RUN.sub(" ", _TAG.sub("", fragment)).strip()


def _section_block(html_content: str, start_match: re.Match) -> str | None:
    """从标题处开始的小节,到同级或更高级标题结束。"""
    level = int(start_match.group(1))
    start = start_match.start()
    for m in _HEADING_OPEN.finditer(html_content, start_match.end()):
        if int(m.group(1)) <= level:
            return html_content[start:m.start()]
    return html_content[start:]


def _heading_before(html_content: str, pos: int) -> re.Match | None:
    start_match = None
    for m in _HEADING_OPEN.finditer(html_content, 0, pos):
        start_match = m
    return start_match


def extract_topic_from_html_legacy(html_content: str, topic_name: str) -> str | None:
    """Legacy webflare HTML:按 <a id=func> 锚点或标题文本定位函数小节。"""
    m = re.search(rf'<a (?:id|name)="{re.escape(topic_name)}"', html_content)
    if m:
        heading = _heading_before(html_content, m.start())
        if heading is not None:
            block = _section_block(html_content, heading)
            if block:
                return block
    for m in _HEADING_BLOCK.finditer(html_content):
        if _plain_heading_text(m.group(2)) == topic_name:
            block = _section_block(html_content, m)
            if block:
                return block
    return None


def extract_doc_section(
    html_content: str,
    topic_name: str,
    *,
    fallback_whole_file: bool = False,
) -> str | None:
    """任意格式中抽取 topic 文档小节:现代标记 -> legacy 标题 -> 整文件兜底。"""
    block = extract_topic_from_html(html_content, topic_name)
    if block is not None:
        return block
    block = extract_topic_from_html_legacy(html_content, topic_name)
    if block is not None:
        return block
    if fallback_whole_file:
        return html_content.strip()
    return None


# ------------------------------------------------------ HTML -> Markdown ----
# 原实现依赖第三方库 markdownify;这里用 stdlib HTMLParser 重写轻量转换,
# 只覆盖前端 mdRender 需要的构造:标题 / 段落 / 代码块 / 行内代码 /
# 粗体斜体 / 链接 / 表格 / 列表。

class _MarkdownConverter(HTMLParser):
    _SKIP_TAGS = {"script", "style", "head", "title"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0
        self.pre_depth = 0
        self.list_stack: list[str] = []
        self.ol_counters: list[int] = []
        self.table: list[list[str]] | None = None
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.anchor_href: str | None = None
        self.heading_level: int | None = None
        self._strip_leading = False  # 剥离块级标记后第一个文本块的前导空白

    def _blank(self) -> None:
        if self.parts and self.parts[-1] and not self.parts[-1].endswith("\n\n"):
            self.parts.append("\n\n")

    def _append(self, s: str) -> None:
        if self.cell is not None:
            self.cell.append(s)
        else:
            self.parts.append(s)

    def handle_starttag(self, tag, attrs) -> None:
        if tag in self._SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if self.pre_depth:
            if tag == "pre":
                self.pre_depth += 1
            return
        if tag == "pre":
            self.pre_depth = 1
            self._blank()
            self.parts.append("```\n")
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._blank()
            self.parts.append("#" * int(tag[1]) + " ")
            self.heading_level = int(tag[1])
            self._strip_leading = True
            return
        if tag == "p":
            self._blank()
            return
        if tag == "br":
            self._append("  \n")
            return
        if tag in ("ul", "ol"):
            self._blank()
            self.list_stack.append(tag)
            self.ol_counters.append(0)
            return
        if tag == "li":
            self._blank()
            if self.list_stack and self.list_stack[-1] == "ol":
                self.ol_counters[-1] += 1
                self.parts.append(f"{self.ol_counters[-1]}. ")
            else:
                self.parts.append("- ")
            self._strip_leading = True
            return
        if tag == "table":
            self._blank()
            self.table = []
            return
        if tag == "tr":
            self.row = []
            return
        if tag in ("td", "th"):
            self.cell = []
            return
        if tag in ("b", "strong"):
            self._append("**")
            return
        if tag in ("i", "em"):
            self._append("_")
            return
        if tag == "code":
            self._append("`")
            return
        if tag == "a":
            href = dict(attrs).get("href", "")
            if href:
                self.anchor_href = href
                self._append("[")
            return
        if tag == "hr":
            self._blank()
            self.parts.append("---\n\n")

    def handle_endtag(self, tag) -> None:
        if tag in self._SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if self.pre_depth:
            if tag == "pre":
                self.pre_depth -= 1
                if self.pre_depth == 0:
                    self.parts.append("\n```\n\n")
            return
        if tag in ("ul", "ol"):
            if self.list_stack:
                self.list_stack.pop()
            if self.ol_counters:
                self.ol_counters.pop()
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.heading_level = None
            if self.parts and not self.parts[-1].endswith("\n"):
                self.parts.append("\n")
            return
        if tag in ("td", "th"):
            if self.cell is not None and self.row is not None:
                text = " ".join("".join(self.cell).split())
                self.row.append(text.replace("|", "\\|"))
            self.cell = None
            return
        if tag == "tr":
            if self.table is not None and self.row is not None:
                self.table.append(self.row)
            self.row = None
            return
        if tag == "table":
            self._flush_table()
            return
        if tag in ("b", "strong"):
            self._append("**")
            return
        if tag in ("i", "em"):
            self._append("_")
            return
        if tag == "code":
            self._append("`")
            return
        if tag == "a":
            if self.anchor_href:
                self._append(f"]({self.anchor_href})")
                self.anchor_href = None

    def _flush_table(self) -> None:
        if not self.table:
            self.table = None
            return
        rows = [r for r in self.table if r]
        if rows:
            head = rows[0]
            self.parts.append("| " + " | ".join(head) + " |\n")
            self.parts.append("|" + "---|" * len(head) + "\n")
            for r in rows[1:]:
                self.parts.append("| " + " | ".join(r) + " |\n")
        self.parts.append("\n")
        self.table = None

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        if self.pre_depth:
            self.parts.append(data)
            return
        if not data:
            return
        if self._strip_leading:
            # 块级标记(标题/列表项)后的首个文本块往往以换行开头,
            # 不剥离会导致 "###" 与标题文字被拆成两行。
            stripped = data.lstrip(" \t\r\n")
            if stripped:
                self._strip_leading = False
                data = stripped
            else:
                return  # 纯空白块,继续等下个文本块
        self._append(data)


def html_to_plain_text(html: str) -> str:
    """HTML -> 轻量 Markdown(替代 markdownify,stdlib only)。"""
    if not html or not html.strip():
        return ""
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", html)
    # Cadence HTML 里常见空 code 标签,会产生孤立反引号,先清掉。
    html = re.sub(r"(?i)<code[^>]*/>", "", html)
    html = re.sub(r"(?i)<code[^>]*></code>", "", html)
    conv = _MarkdownConverter()
    conv.feed(html)
    conv.close()
    md = "".join(conv.parts)
    md = re.sub(r"[ \t]+\n", "\n", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


# ---------------------------------------------------------- 组装(后端入口) -
_tgf_cache: dict[str, tuple[float, dict[str, MoreInfoEntry]]] = {}
_tgf_cache_lock = threading.Lock()


def _load_tgf(tgf_path: Path) -> dict[str, MoreInfoEntry]:
    """按 mtime 缓存的 .tgf 索引加载。"""
    key = str(tgf_path)
    try:
        mtime = tgf_path.stat().st_mtime
    except OSError:
        return {}
    with _tgf_cache_lock:
        cached = _tgf_cache.get(key)
        if cached and cached[0] == mtime:
            return cached[1]
        entries = parse_tgf_index(tgf_path)
        _tgf_cache[key] = (mtime, entries)
        return entries


def get_more_info(func_name: str, doc_root: Path) -> dict | None:
    """本地 More Info 查询(原 VirtuosoClient.get_skill_more_info 的本地分支)。

    返回 dict(func_name/file_path/topic/raw_html/plain_text) 或 None。
    OCEAN/ViVA 函数自动尝试 _ocean/_viva_skill 后缀。
    """
    tgf_path = doc_root / "api_more_info" / "api_more_info.tgf"
    entries = _load_tgf(tgf_path)

    key = func_name.lower()
    entry = entries.get(key)
    if entry is None:
        for suffix in ("_ocean", "_viva_skill"):
            entry = entries.get(key + suffix)
            if entry is not None:
                break
    if entry is None:
        return None

    html_path = resolve_doc_path(tgf_path, entry.file_path)
    if not html_path.exists():
        return None
    try:
        html_content = html_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    if entry.topic or entry.func_name:
        # 先精确抽取 topic 小节,找不到且文件只索引一个函数时退回整文件。
        single_func_file = (
            sum(1 for e in entries.values() if e.file_path == entry.file_path)
            == 1
        )
        raw_html = extract_doc_section(
            html_content,
            entry.topic or entry.func_name,
            fallback_whole_file=entry.topic is None or single_func_file,
        )
    else:
        raw_html = html_content
    if raw_html is None:
        return None

    return {
        "func_name": entry.func_name,
        "file_path": entry.file_path,
        "topic": entry.topic,
        "raw_html": raw_html,
        "plain_text": html_to_plain_text(raw_html),
    }


_finder: SKILLFinder | None = None
_doc_root: Path | None = None


def init_backend(doc_root: Path) -> None:
    """启动时一次性加载 .fnd 数据库(内存),More Info 按需惰性读取。"""
    global _finder, _doc_root
    _doc_root = Path(doc_root)
    finder_root = _doc_root / "finder" / "SKILL"
    if not finder_root.is_dir():
        raise SystemExit(f"finder/SKILL not found under: {_doc_root}")
    _finder = SKILLFinder()
    t0 = time.perf_counter()
    _finder.load(finder_root)
    print(f"[server] loaded {len(_finder.entries)} SKILL entries "
          f"in {(time.perf_counter() - t0) * 1000:.0f} ms from {finder_root}")


def search(query: str, mode: str, limit: int, include_desc: bool) -> list[dict]:
    assert _finder is not None
    return [e.to_dict() for e in _finder.search(
        query, mode=mode, limit=limit, include_desc=include_desc
    )]


def more_info(func_name: str) -> dict | None:
    assert _doc_root is not None
    return get_more_info(func_name, _doc_root)


# ------------------------------------------------------------------- http --
def _log(msg: str) -> None:
    with LOG_LOCK:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


HELP_DOC = {
    "service": "SKILL 函数离线查询服务 — 只读本地 Cadence 文档树",
    "endpoints": {
        "/api/find": {
            "desc": "按名称搜索 SKILL 函数(基于 finder/SKILL/*.fnd 索引)",
            "params": {
                "q": "必填。搜索关键字,如 dbOpenCellView;regex 模式下可写 ^db.*",
                "mode": f"可选,默认 fuzzy。取值: {', '.join(MODES)}",
                "limit": "可选,默认 50,范围 1-200",
                "include_desc": "可选,0/1(默认 0)。为 1 时同时在描述字段中搜索",
            },
            "example": "/api/find?q=hiGetCurrentWindow&mode=fuzzy&limit=10",
            "returns": '{"results": [{name, syntax, description, source_file}]}',
        },
        "/api/info": {
            "desc": "查询单个函数的 More Info 详细文档(基于 api_more_info/.tgf + HTML)",
            "params": {
                "name": "必填。函数名;OCEAN/ViVA 函数自动回退 _ocean/_viva_skill 后缀",
            },
            "example": "/api/info?name=ocnPrint",
            "returns": "{\"found\": true, func_name, file_path, topic, raw_html, plain_text}",
        },
        "/api/stats": {
            "desc": "服务统计:文档根目录与已加载函数总数",
            "example": "/api/stats",
            "returns": '{"doc_root": ..., "total": 9503}',
        },
    },
}


class Handler(BaseHTTPRequestHandler):
    server_version = "SkillDocServer/1.0"

    def log_message(self, fmt, *args):  # 走自己的日志
        pass

    def _send_json(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path, params = parsed.path, parse_qs(parsed.query)

        def one(name: str, default=None):
            v = params.get(name)
            return v[0] if v else default

        try:
            if path == "/":
                self._send_html(INDEX_HTML)
                return
            if path == "/api/help":
                self._send_json(HELP_DOC)
                return
            if path == "/api/stats":
                self._send_json({
                    "doc_root": str(_doc_root),
                    "total": len(_finder.entries),
                })
                return
            if path == "/api/find":
                q = (one("q") or "").strip()
                if not q:
                    self._send_json({"error": "query required"}, 400)
                    return
                mode = one("mode", "fuzzy")
                if mode not in MODES:
                    self._send_json({"error": f"mode must be one of {MODES}"}, 400)
                    return
                try:
                    limit = min(max(int(one("limit", 50)), 1), 200)
                except ValueError:
                    limit = 50
                include_desc = one("include_desc", "0") in ("1", "true", "on")
                t0 = time.perf_counter()
                results = search(q, mode, limit, include_desc)
                _log(f"find q={q!r} mode={mode} -> {len(results)} hits "
                     f"({(time.perf_counter() - t0) * 1000:.0f} ms)")
                self._send_json({"results": results})
                return
            if path == "/api/info":
                fn = (one("name") or "").strip()
                if not fn:
                    self._send_json({"error": "name required"}, 400)
                    return
                t0 = time.perf_counter()
                info = more_info(fn)
                _log(f"info {fn!r} -> {'found' if info else 'NOT FOUND'} "
                     f"({(time.perf_counter() - t0) * 1000:.0f} ms)")
                if info is None:
                    self._send_json({"found": False, "name": fn})
                else:
                    self._send_json({"found": True, **info})
                return
            self._send_json({"error": f"unknown path {path}"}, 404)
        except Exception as exc:  # noqa: BLE001 — 前端显示
            _log(f"ERROR {path}: {exc!r}")
            self._send_json({"error": str(exc)}, 500)


# ---------------------------------------------------------------- frontend --
INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>SKILL 函数查询</title>
<style>
  :root { --bg:#f6f7f9; --panel:#fff; --line:#e3e6ea; --text:#24292f;
          --dim:#6a737d; --accent:#0969da; --accent-soft:#ddf4ff; --code:#f6f8fa; }
  * { box-sizing:border-box; }
  body { margin:0; font:14px/1.6 "Segoe UI", system-ui, sans-serif; background:var(--bg); color:var(--text); }
  header { background:var(--panel); border-bottom:1px solid var(--line); padding:14px 24px; }
  header h1 { margin:0; font-size:18px; }
  header .sub { color:var(--dim); font-size:12px; margin-top:2px; }
  main { max-width:1180px; margin:0 auto; padding:18px 24px 60px; }
  .bar { display:flex; gap:8px; flex-wrap:wrap; align-items:center; background:var(--panel);
         border:1px solid var(--line); border-radius:8px; padding:10px 12px; margin-bottom:10px; }
  .bar input[type=text] { flex:1 1 260px; min-width:200px; padding:7px 10px; font-size:14px;
         border:1px solid var(--line); border-radius:6px; outline:none; }
  .bar input[type=text]:focus { border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-soft); }
  select, .bar input[type=number] { padding:6px 8px; border:1px solid var(--line); border-radius:6px; background:#fff; }
  .chips { display:flex; gap:6px; flex-wrap:wrap; margin-bottom:12px; }
  .chip { border:1px solid var(--line); background:var(--panel); border-radius:14px; padding:2px 10px;
          font-size:12px; color:var(--dim); cursor:pointer; }
  .chip:hover { border-color:var(--accent); color:var(--accent); }
  button { padding:7px 18px; border:0; border-radius:6px; background:var(--accent); color:#fff;
           font-size:14px; cursor:pointer; }
  button:hover { filter:brightness(1.08); }
  .status { color:var(--dim); font-size:12px; margin:0 0 10px 2px; }
  .layout { display:grid; grid-template-columns: minmax(0, 46%) 1fr; gap:14px; align-items:start; }
  @media (max-width:640px) { .layout { grid-template-columns:1fr; } }
  .panel { background:var(--panel); border:1px solid var(--line); border-radius:8px; overflow:hidden; }
  .item { padding:9px 12px; border-bottom:1px solid var(--line); cursor:pointer; }
  .item:last-child { border-bottom:0; }
  .item:hover { background:#f0f6ff; }
  .item.active { background:var(--accent-soft); border-left:3px solid var(--accent); }
  .item .name { font-family:Consolas, monospace; font-size:13px; color:var(--accent); font-weight:600; }
  .item .src { font-size:11px; color:var(--dim); margin-left:8px; }
  .item .syn { font-family:Consolas, monospace; font-size:11px; color:var(--dim);
               white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .item .desc { font-size:12px; color:var(--dim); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .empty { padding:30px; text-align:center; color:var(--dim); }
  #detail { position:sticky; top:14px; max-height:calc(100vh - 40px); overflow:auto; }
  .dhead { padding:10px 14px; border-bottom:1px solid var(--line); background:#fafbfc; }
  .dhead .fname { font-family:Consolas, monospace; font-weight:700; font-size:15px; }
  .dhead .meta { font-size:11px; color:var(--dim); }
  .dbody { padding:12px 16px; }
  .dbody h1,.dbody h2,.dbody h3,.dbody h4,.dbody h5 { margin:14px 0 6px; }
  .dbody h3 { font-size:15px; } .dbody h4 { font-size:13px; color:#57606a; text-transform:uppercase; }
  .dbody p { margin:6px 0; }
  .dbody code { background:var(--code); padding:1px 5px; border-radius:4px;
                font-family:Consolas, monospace; font-size:12px; }
  .dbody pre { background:var(--code); border:1px solid var(--line); border-radius:6px;
               padding:10px; overflow-x:auto; font-size:12px; line-height:1.5; }
  .dbody table { border-collapse:collapse; margin:8px 0; width:100%; font-size:12.5px; }
  .dbody th,.dbody td { border:1px solid var(--line); padding:4px 9px; text-align:left; vertical-align:top; }
  .dbody th { background:#f2f4f6; font-weight:600; }
  .err { color:#cf222e; }
  .hint { font-size:12px; color:var(--dim); }
</style>
</head>
<body>
<header>
  <h1>SKILL 函数查询</h1>
  <div class="sub" id="stats"></div>
</header>
<main>
  <div class="bar">
    <input type="text" id="q" placeholder="函数名,如 dbOpenCellView 或 ^db.*(regex)" autofocus>
    <select id="mode" title="搜索模式">
      <option value="fuzzy">模糊</option>
      <option value="prefix">前缀</option>
      <option value="suffix">后缀</option>
      <option value="exact">精确</option>
      <option value="regex">正则</option>
    </select>
    <label class="hint"><input type="checkbox" id="desc"> 含描述</label>
    <input type="number" id="limit" value="50" min="1" max="200" style="width:70px" title="结果上限">
    <button id="go">查询</button>
  </div>
  <div class="chips">
    <span class="hint">示例:</span>
    <span class="chip">dbOpen</span><span class="chip">hiGetCurrentWindow</span>
    <span class="chip">leHiCreateRect</span><span class="chip" data-mode="regex">^rod.*</span>
    <span class="chip">axlDB</span><span class="chip">ocnPrint</span><span class="chip">printf</span>
  </div>
  <div class="status" id="status"></div>
  <div class="layout">
    <div class="panel" id="list"><div class="empty">输入关键字开始查询</div></div>
    <div class="panel" id="detail"><div class="empty">← 点击函数查看详细文档</div></div>
  </div>
</main>
<script>
"use strict";
const $ = (id) => document.getElementById(id);
const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const mono = (s) => esc(s);

function inline(s) {
  s = esc(s);
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\\*\\*([^*]+)\\*\\*/g, "<b>$1</b>");
  s = s.replace(/\\[([^\\]]+)\\]\\(([^)\\s]+)\\)/g, '<a href="$2">$1</a>');
  // _x_ → <i>,但跳过 <code> 内部;贪婪匹配到末尾 _ (允许 x 中嵌 _)
  s = s.replace(/(<code>[\\s\\S]*?<\\/code>)|_([\\s\\S]+?)_(?!\\w)/g,
    (m, code, ital) => code ? code : `<i>${ital}</i>`);
  return s;
}

function mdRender(md) {
  const lines = md.split(/\\r?\\n/);
  const out = []; let inCode = false, codeBuf = [], table = null;
  const flushTable = () => {
    if (!table) return;
    // Cadence 文档表格所有行地位平等(首行是参数名,不是表头),
    // 因此全部渲染为普通 <td>,不做 <thead>/<th> 染色加粗。
    const rows = table.head ? [table.head, ...table.rows] : table.rows;
    if (rows.length > 0) {
      const body = "<tbody>" + rows.map(r =>
        "<tr>" + r.map(c => "<td>" + inline(c) + "</td>").join("") + "</tr>").join("") + "</tbody>";
      out.push("<table>" + body + "</table>");
    }
    table = null;
  };
  const splitRow = (line) => {
    let c = line.trim().split("|");
    if (c.length && c[0] === "") c.shift();
    if (c.length && c[c.length - 1] === "") c.pop();
    return c.map(s => s.trim());
  };
  for (const line of lines) {
    if (line.trim().startsWith("```")) {
      flushTable();
      if (inCode) { out.push("<pre>" + mono(codeBuf.join("\\n")) + "</pre>"); codeBuf = []; }
      inCode = !inCode; continue;
    }
    if (inCode) { codeBuf.push(line); continue; }
    const t = line.trim();
    if (t === "") { flushTable(); continue; }
    const h = t.match(/^(#{1,6})\\s+(.*)$/);
    if (h) { flushTable(); out.push("<h" + h[1].length + ">" + inline(h[2]) + "</h" + h[1].length + ">"); continue; }
    if (t.startsWith("|")) {
      const cells = splitRow(t);
      if (/^[|:\\s-]+$/.test(t)) continue;            // 分隔行 |---|---|
      if (!table) table = { head: cells, rows: [] };
      else if (table.head === null) table.head = cells;
      else table.rows.push(cells);
      continue;
    }
    flushTable();
    if (/^[-*]\\s+/.test(t)) { out.push("<p>• " + inline(t.replace(/^[-*]\\s+/, "")) + "</p>"); continue; }
    if (/^\\d+\\.\\s+/.test(t)) { out.push("<p>" + inline(t) + "</p>"); continue; }
    out.push("<p>" + inline(line) + "</p>");
  }
  flushTable();
  if (inCode && codeBuf.length) out.push("<pre>" + mono(codeBuf.join("\\n")) + "</pre>");
  return out.join("\\n");
}

let activeName = null;
const listEl = $("list"), detailEl = $("detail");

async function doSearch() {
  const q = $("q").value.trim();
  if (!q) return;
  const mode = $("mode").value;
  const limit = parseInt($("limit").value || "50", 10);
  const include_desc = $("desc").checked ? 1 : 0;
  const t0 = performance.now();
  $("status").textContent = "查询中…";
  try {
    const r = await fetch(`/api/find?q=${encodeURIComponent(q)}&mode=${mode}&limit=${limit}&include_desc=${include_desc}`);
    const j = await r.json();
    const ms = Math.round(performance.now() - t0);
    if (j.error) { listEl.innerHTML = `<div class="empty err">${esc(j.error)}</div>`; return; }
    const items = j.results;
    $("status").textContent = `命中 ${items.length} 条 · ${ms} ms · 模式 ${mode}`;
    if (!items.length) { listEl.innerHTML = `<div class="empty">无匹配:${esc(q)}</div>`; detailEl.innerHTML = `<div class="empty">—</div>`; return; }
    listEl.innerHTML = items.map((it, i) =>
      `<div class="item" data-i="${i}">
         <div><span class="name">${mono(it.name)}</span><span class="src">${mono(it.source_file || "")}</span></div>
         <div class="syn">${mono(it.syntax || "")}</div>
         <div class="desc">${mono(it.description || "")}</div>
       </div>`).join("");
    listEl.querySelectorAll(".item").forEach(el => {
      el.onclick = () => {
        listEl.querySelectorAll(".item").forEach(x => x.classList.remove("active"));
        el.classList.add("active");
        showInfo(items[+el.dataset.i].name);
      };
    });
  } catch (e) {
    $("status").textContent = "请求失败:" + e;
  }
}

async function showInfo(name) {
  detailEl.innerHTML = `<div class="empty">加载 ${esc(name)} 文档…</div>`;
  try {
    const r = await fetch(`/api/info?name=${encodeURIComponent(name)}`);
    const j = await r.json();
    if (!j.found) {
      detailEl.innerHTML = `<div class="dhead"><span class="fname">${mono(name)}</span></div>
        <div class="dbody"><p class="err">该函数在 api_more_info 索引中无条目(可先用 find 查看语法)。</p></div>`;
      return;
    }
    const path = j.file_path ? " — " + esc(j.file_path) : "";
    const topic = j.topic ? " · topic " + esc(j.topic) : "";
    detailEl.innerHTML =
      `<div class="dhead"><span class="fname">${mono(j.func_name || name)}</span>
        <div class="meta">${path}${topic}</div></div>
       <div class="dbody">${mdRender(j.plain_text || "")}</div>`;
    detailEl.scrollTop = 0;
  } catch (e) {
    detailEl.innerHTML = `<div class="empty err">加载失败:${esc(String(e))}</div>`;
  }
}

$("go").onclick = doSearch;
$("q").addEventListener("keydown", e => { if (e.key === "Enter") doSearch(); });
document.querySelectorAll(".chip").forEach(c => c.onclick = () => {
  $("q").value = c.textContent;
  // 示例 chip 配套自己的模式:^rod.* -> regex,其余 -> fuzzy(避免残留上次模式)
  $("mode").value = c.dataset.mode || "fuzzy";
  doSearch();
});

(async () => {
  try {
    const s = await (await fetch("/api/stats")).json();
    $("stats").textContent = `${s.total} 个函数`;
  } catch (_) {}
})();
</script>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="SKILL 函数离线查询服务")
    ap.add_argument("--doc", type=Path, default=DEFAULT_DOC,
                    help=f"Cadence doc root (default {DEFAULT_DOC})")
    ap.add_argument("--port", type=int, default=8123, help="listen port (default 8123)")
    ap.add_argument("--host", default="127.0.0.1",
                    help="listen host (default 127.0.0.1)")
    args = ap.parse_args()

    init_backend(args.doc)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[server] running at http://{args.host}:{args.port} "
          f"(Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[server] stopped")


if __name__ == "__main__":
    main()
