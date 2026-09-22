"""Parsing/search helpers for the ``skillref`` package (stdlib only).

纯解析层：.fnd 词条、.tgf 主题表、HTML 抽取与 Markdown 化、正文层打分。
不 import 任何 transport/中层/业务代码，便于单元测试与本地/远端两种模式复用。
口径来源：``tools/skill_doc_server.py``（8123）与
``src_bak/virtuoso_bridge/virtuoso/skill_finder/``。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Sequence

FINDER_TAIL = ("finder", "SKILL")
TGF_REL = ("api_more_info", "api_more_info.tgf")
BODY_SUFFIXES = (".html", ".htm", ".txt", ".xml")
MODES = ("fuzzy", "prefix", "suffix", "exact", "regex")

# 打分权重（spec 9-skillref §4.4）
NAME_SCORE = {"exact": 100, "prefix": 80, "substring": 60}
ENTRY_SYNTAX_SCORE = 20
ENTRY_DESC_SCORE = 10
TOPIC_EXACT_SCORE = 90
TOPIC_SUB_SCORE = 70
TOPIC_FILE_SCORE = 10
BODY_TITLE_SCORE = 40
BODY_PATH_SCORE = 30
BODY_TEXT_SCORE = 20
BODY_EXTRA_TERM_SCORE = 5


# --------------------------------------------------------------------- .fnd --
@dataclass(frozen=True)
class SkillEntry:
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


_FND_ENTRY = re.compile(
    r'\("([^"]+)"\s*\n\s*"((?:[^"\\]|\\.)*)"\s*\n\s*"((?:[^"\\]|\\.)*)"\s*\)',
    re.DOTALL,
)


def parse_fnd_file(path: Path) -> list[SkillEntry]:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = [line for line in content.splitlines() if not line.startswith(";")]
    normalized = "\n".join(lines)
    entries: list[SkillEntry] = []
    for match in _FND_ENTRY.finditer(normalized):
        name = match.group(1).strip()
        syntax = match.group(2).strip()
        description = match.group(3).strip()
        if name and syntax:
            entries.append(SkillEntry(name, syntax, description, path.name))
    return entries


def parse_fnd_directory(root: Path) -> list[SkillEntry]:
    """解析 root 下全部 .fnd；同名函数按首次出现者胜。"""
    seen: set[str] = set()
    entries: list[SkillEntry] = []
    if not root.is_dir():
        return entries
    for fnd_file in sorted(root.rglob("*.fnd")):
        for entry in parse_fnd_file(fnd_file):
            if entry.name not in seen:
                seen.add(entry.name)
                entries.append(entry)
    return entries


# ------------------------------------------------------------ 名称/词条匹配 --
def name_matches(name: str, query: str, mode: str) -> bool:
    if mode == "exact":
        return name == query
    if mode == "prefix":
        return name.startswith(query)
    if mode == "suffix":
        return name.endswith(query)
    if mode == "regex":
        try:
            return re.search(query, name, re.IGNORECASE) is not None
        except re.error:
            return False
    return query.lower() in name.lower()


def name_score(name: str, query: str, mode: str) -> int:
    """命中形状 -> 分数；未命中 0（spec §4.4）。"""
    if mode == "exact":
        return NAME_SCORE["exact"] if name == query else 0
    if mode == "prefix":
        return NAME_SCORE["prefix"] if name.startswith(query) else 0
    if mode == "suffix":
        return NAME_SCORE["substring"] if name.endswith(query) else 0
    if mode == "regex":
        try:
            return NAME_SCORE["substring"] if re.search(query, name, re.IGNORECASE) else 0
        except re.error:
            return 0
    lowered = name.lower()
    if lowered == query.lower():
        return NAME_SCORE["exact"]
    if lowered.startswith(query.lower()):
        return NAME_SCORE["prefix"]
    return NAME_SCORE["substring"] if query.lower() in lowered else 0


def search_entries(
    entries: Iterable[SkillEntry],
    query: str,
    *,
    mode: str = "fuzzy",
    search_in: str = "name",
) -> list[dict]:
    """在词条层匹配；``search_in="entry"`` 时并入语法与一行描述。"""
    include_deep = search_in in ("entry", "topic", "body")
    lowered = query.lower()
    hits: list[dict] = []
    for entry in entries:
        score = name_score(entry.name, query, mode)
        why: list[str] = []
        layer = "name"
        if score:
            why.append("name")
        elif include_deep:
            if lowered and lowered in entry.syntax.lower():
                score += ENTRY_SYNTAX_SCORE
                why.append("syntax")
            if lowered and lowered in entry.description.lower():
                score += ENTRY_DESC_SCORE
                why.append("description")
            if why:
                layer = "entry"
        if not score or not why:
            continue
        record = entry.to_dict()
        record.update({"layer": layer, "score": score, "why": why})
        hits.append(record)
    return hits


# --------------------------------------------------------------------- .tgf --
@dataclass(frozen=True)
class TopicEntry:
    func_name: str
    file_path: str
    topic: str | None
    fmt: str


_TGF_QUOTED = re.compile(r'^(\S+)\s+(\S+)\s+"([^"]+)"\s+(\S+)$')
_TGF_NULL = re.compile(r"^(\S+)\s+(\S+)\s+(NULL)\s+(\S+)$", re.IGNORECASE)


def parse_tgf_index(tgf_path: Path) -> dict[str, TopicEntry]:
    entries: dict[str, TopicEntry] = {}
    try:
        content = tgf_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return entries
    for raw in content.splitlines():
        line = raw.strip().strip("\r")
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        match = _TGF_QUOTED.match(line) or _TGF_NULL.match(line)
        if not match:
            continue
        func_name, file_path, topic, fmt = match.groups()
        key = func_name.lower()
        if key in entries:
            continue
        entries[key] = TopicEntry(
            func_name=func_name,
            file_path=file_path,
            topic=None if topic.upper() == "NULL" else topic,
            fmt=fmt,
        )
    return entries


def lookup_topic(entries: dict[str, TopicEntry], name: str) -> TopicEntry | None:
    """小写键查表；OCEAN/ViVA 函数自动尝试 ``_ocean`` / ``_viva_skill`` 后缀。"""
    key = name.lower()
    entry = entries.get(key)
    if entry is not None:
        return entry
    for suffix in ("_ocean", "_viva_skill"):
        entry = entries.get(key + suffix)
        if entry is not None:
            return entry
    return None


def resolve_doc_path(tgf_path: Path, relative_path: str) -> Path:
    """``$skdfref/cvio.html`` -> ``<doc_root>/skdfref/cvio.html``。"""
    return tgf_path.parent.parent / relative_path.lstrip("$")


def topic_matches(entry: TopicEntry, query: str, mode: str = "fuzzy") -> tuple[int, list[str]]:
    """主题层匹配：表键函数名 / topic 名（exact/substring）+ 目标文件名。"""
    score = 0
    why: list[str] = []
    lowered = query.lower()
    names = [name for name in (entry.func_name, entry.topic) if name]
    for name in names:
        if name == query or name.lower() == lowered:
            score += TOPIC_EXACT_SCORE
            why.append("topic")
            break
        if lowered in name.lower():
            score += TOPIC_SUB_SCORE
            why.append("topic")
            break
    if not score and lowered and lowered in Path(entry.file_path).name.lower():
        score += TOPIC_SUB_SCORE + TOPIC_FILE_SCORE
        why.extend(["topic", "file"])
    return score, why


# -------------------------------------------------------------------- html ---
_TOPIC_START = re.compile(r"<!--\s*\[TOPIC_START_OPEN\](.*?)-->", re.DOTALL)
_TOPIC_TEXT = re.compile(r"\[TOPIC_START_ATTR\]text=([^\n]+)", re.IGNORECASE)
_TOPIC_END = "<!-- [TOPIC_END] -->"
_HEADING_OPEN = re.compile(r"<h([1-6])(?=[\s>])", re.IGNORECASE)
_HEADING_BLOCK = re.compile(r"<h([1-6])[^>]*>(.*?)</h\1>", re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_WS_RUN = re.compile(r"\s+")
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.DOTALL | re.IGNORECASE)


def extract_topic_from_html(html_content: str, topic_name: str) -> str | None:
    """现代 More Info：``[TOPIC_START_OPEN]`` … ``[TOPIC_END]``。"""
    for match in _TOPIC_START.finditer(html_content):
        text_match = _TOPIC_TEXT.search(match.group(1))
        if not text_match or text_match.group(1).strip() != topic_name:
            continue
        end_pos = html_content.find(_TOPIC_END, match.start())
        if end_pos == -1:
            continue
        tag_end = html_content.find("-->", match.start())
        return html_content[tag_end + 3:end_pos].strip()
    return None


def _plain_heading_text(fragment: str) -> str:
    return _WS_RUN.sub(" ", _TAG.sub("", fragment)).strip()


def _section_block(html_content: str, start_match: re.Match) -> str | None:
    level = int(start_match.group(1))
    for match in _HEADING_OPEN.finditer(html_content, start_match.end()):
        if int(match.group(1)) <= level:
            return html_content[start_match.start():match.start()]
    return html_content[start_match.start():]


def _heading_before(html_content: str, pos: int) -> re.Match | None:
    found = None
    for match in _HEADING_OPEN.finditer(html_content, 0, pos):
        found = match
    return found


def extract_topic_from_html_legacy(html_content: str, topic_name: str) -> str | None:
    """legacy webflare：``<a id|name>`` 锚点或标题文本定位。"""
    match = re.search(rf'<a (?:id|name)="{re.escape(topic_name)}"', html_content)
    if match:
        heading = _heading_before(html_content, match.start())
        if heading is not None:
            block = _section_block(html_content, heading)
            if block:
                return block
    for match in _HEADING_BLOCK.finditer(html_content):
        if _plain_heading_text(match.group(2)) == topic_name:
            block = _section_block(html_content, match)
            if block:
                return block
    return None


def extract_doc_section(
    html_content: str,
    topic_name: str,
    *,
    fallback_whole_file: bool = False,
) -> str | None:
    block = extract_topic_from_html(html_content, topic_name)
    if block is not None:
        return block
    block = extract_topic_from_html_legacy(html_content, topic_name)
    if block is not None:
        return block
    if fallback_whole_file:
        return html_content.strip()
    return None


class _MarkdownConverter(HTMLParser):
    """HTML -> 轻量 Markdown（标题/段落/代码块/行内代码/粗斜体/链接/表格/列表）。"""

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
        self._strip_leading = False

    def _blank(self) -> None:
        if self.parts and self.parts[-1] and not self.parts[-1].endswith("\n\n"):
            self.parts.append("\n\n")

    def _append(self, text: str) -> None:
        if self.cell is not None:
            self.cell.append(text)
        else:
            self.parts.append(text)

    def handle_starttag(self, tag, attrs) -> None:  # noqa: D102
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
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._blank()
            self.parts.append("#" * int(tag[1]) + " ")
            self._strip_leading = True
        elif tag == "p":
            self._blank()
        elif tag == "br":
            self._append("  \n")
        elif tag in ("ul", "ol"):
            self._blank()
            self.list_stack.append(tag)
            self.ol_counters.append(0)
        elif tag == "li":
            self._blank()
            if self.list_stack and self.list_stack[-1] == "ol":
                self.ol_counters[-1] += 1
                self.parts.append(f"{self.ol_counters[-1]}. ")
            else:
                self.parts.append("- ")
            self._strip_leading = True
        elif tag == "table":
            self._blank()
            self.table = []
        elif tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.cell = []
        elif tag in ("b", "strong"):
            self._append("**")
        elif tag in ("i", "em"):
            self._append("_")
        elif tag == "code":
            self._append("`")
        elif tag == "a":
            href = dict(attrs).get("href", "")
            if href:
                self.anchor_href = href
                self._append("[")
        elif tag == "hr":
            self._blank()
            self.parts.append("---\n\n")

    def handle_endtag(self, tag) -> None:  # noqa: D102
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
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            if self.parts and not self.parts[-1].endswith("\n"):
                self.parts.append("\n")
        elif tag in ("td", "th"):
            if self.cell is not None and self.row is not None:
                text = " ".join("".join(self.cell).split())
                self.row.append(text.replace("|", "\\|"))
            self.cell = None
        elif tag == "tr":
            if self.table is not None and self.row is not None:
                self.table.append(self.row)
            self.row = None
        elif tag == "table":
            self._flush_table()
        elif tag in ("b", "strong"):
            self._append("**")
        elif tag in ("i", "em"):
            self._append("_")
        elif tag == "code":
            self._append("`")
        elif tag == "a" and self.anchor_href:
            self._append(f"]({self.anchor_href})")
            self.anchor_href = None

    def _flush_table(self) -> None:
        if not self.table:
            self.table = None
            return
        rows = [row for row in self.table if row]
        if rows:
            self.parts.append("| " + " | ".join(rows[0]) + " |\n")
            self.parts.append("|" + "---|" * len(rows[0]) + "\n")
            for row in rows[1:]:
                self.parts.append("| " + " | ".join(row) + " |\n")
        self.parts.append("\n")
        self.table = None

    def handle_data(self, data: str) -> None:  # noqa: D102
        if self.skip_depth:
            return
        if self.pre_depth:
            self.parts.append(data)
            return
        if not data:
            return
        if self._strip_leading:
            stripped = data.lstrip(" \t\r\n")
            if not stripped:
                return
            self._strip_leading = False
            data = stripped
        self._append(data)


def html_to_markdown(html: str) -> str:
    """HTML -> 轻量 Markdown（stdlib only，替代 markdownify）。"""
    if not html or not html.strip():
        return ""
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", html)
    html = re.sub(r"(?i)<code[^>]*/>", "", html)
    html = re.sub(r"(?i)<code[^>]*></code>", "", html)
    converter = _MarkdownConverter()
    converter.feed(html)
    converter.close()
    text = "".join(converter.parts)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def html_title(html: str) -> str:
    match = _TITLE.search(html)
    return _WS_RUN.sub(" ", _TAG.sub("", match.group(1))).strip() if match else ""


def html_to_text(html: str) -> str:
    """正文层打分用：去脚本样式与标签，压平空白。"""
    if not html:
        return ""
    text = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", html)
    text = _TAG.sub(" ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    return _WS_RUN.sub(" ", text).strip()


# ------------------------------------------------------------- 正文层辅助 ----
def query_terms(query: str) -> list[str]:
    """查询词：按空白切分、小写、去重（保留顺序）。多词按 AND 处理。"""
    terms: list[str] = []
    for raw in query.split():
        term = raw.strip().lower()
        if term and term not in terms:
            terms.append(term)
    return terms


def read_text(path: Path) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except (OSError, UnicodeError):
            continue
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def iter_body_files(
    doc_root: Path,
    under: Sequence[str] | None,
    max_files: int,
) -> tuple[list[Path], bool]:
    """列出正文层候选文件；返回 (files, truncated)。"""
    roots: list[Path] = []
    if under:
        for rel in under:
            candidate = doc_root / rel
            if candidate.is_dir():
                roots.append(candidate)
    if not roots:
        roots = [doc_root]
    files: list[Path] = []
    truncated = False
    for root in roots:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in BODY_SUFFIXES:
                continue
            if len(files) >= max_files:
                truncated = True
                return files, truncated
            files.append(path)
    return files, truncated


def matches_all_terms(text: str, terms: Sequence[str]) -> bool:
    lowered = text.lower()
    return all(term in lowered for term in terms)


def make_snippet(text: str, terms: Sequence[str], radius: int = 90) -> str:
    if not text or not terms:
        return ""
    lowered = text.lower()
    position = -1
    for term in terms:
        found = lowered.find(term)
        if found != -1 and (position == -1 or found < position):
            position = found
    if position == -1:
        return ""
    start = max(0, position - radius)
    end = min(len(text), position + radius)
    prefix = "..." if start else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"


def body_score(title: str, relative_path: str, text: str, terms: Sequence[str]) -> int:
    score = 0
    lowered_title = title.lower()
    lowered_path = relative_path.lower()
    lowered_text = text.lower()
    if any(term in lowered_title for term in terms):
        score += BODY_TITLE_SCORE
    if any(term in lowered_path for term in terms):
        score += BODY_PATH_SCORE
    if any(term in lowered_text for term in terms):
        score += BODY_TEXT_SCORE
    hits = sum(1 for term in terms if term in lowered_title or term in lowered_text)
    if hits > 1:
        score += BODY_EXTRA_TERM_SCORE * (hits - 1)
    return score


def first_match_line(text: str, terms: Sequence[str]) -> int | None:
    lowered_terms = [term.lower() for term in terms]
    for number, line in enumerate(text.splitlines(), 1):
        lowered = line.lower()
        if any(term in lowered for term in lowered_terms):
            return number
    return None


__all__ = [
    "BODY_SUFFIXES",
    "FINDER_TAIL",
    "MODES",
    "TGF_REL",
    "SkillEntry",
    "TopicEntry",
    "body_score",
    "extract_doc_section",
    "extract_topic_from_html",
    "extract_topic_from_html_legacy",
    "first_match_line",
    "html_title",
    "html_to_markdown",
    "html_to_text",
    "iter_body_files",
    "lookup_topic",
    "make_snippet",
    "matches_all_terms",
    "name_matches",
    "name_score",
    "parse_fnd_directory",
    "parse_fnd_file",
    "parse_tgf_index",
    "query_terms",
    "read_text",
    "resolve_doc_path",
    "search_entries",
    "topic_matches",
]
