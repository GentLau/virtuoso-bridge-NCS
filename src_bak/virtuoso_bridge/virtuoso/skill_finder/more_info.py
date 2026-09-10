"""Parser for Cadence More Info API documentation.

The More Info system consists of:
1. ``api_more_info.tgf`` — index mapping SKILL function names to (file, topic) pairs
2. HTML files containing the actual documentation, with topics delimited by
   ``<!-- [TOPIC_START_OPEN]... -->`` and ``<!-- [TOPIC_END] -->`` markers.
"""

from __future__ import annotations

import re
import markdownify
from dataclasses import dataclass
from pathlib import Path


# Pattern for .tgf index lines (whitespace-separated):
_TGF_QUOTED = re.compile(r"^(\S+)\s+(\S+)\s+\"([^\"]+)\"\s+(\S+)$")
_TGF_NULL = re.compile(r"^(\S+)\s+(\S+)\s+(NULL)\s+(\S+)$", re.IGNORECASE)

# Pattern for TOPIC_START block in HTML
_TOPIC_START = re.compile(r"<!--\s*\[TOPIC_START_OPEN\](.*?)-->", re.DOTALL)
_TOPIC_END = "<!-- [TOPIC_END] -->"
_TOPIC_TEXT = re.compile(r"\[TOPIC_START_ATTR\]text=([^\n]+)", re.IGNORECASE)

# Legacy (pre-More-Info) webflare HTML: one <h1..h6> section per function.
# No TOPIC_START markers; functions are located by an <a id=func> anchor or
# by the heading text itself (anchors may split the name, e.g.
# ``iqCreateDummy<a id="marker-..."></a>Cell``).
_HEADING_OPEN = re.compile(r"<h([1-6])(?=[\s>])", re.IGNORECASE)
_HEADING_BLOCK = re.compile(r"<h([1-6])[^>]*>(.*?)</h\1>", re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_WS_RUN = re.compile(r"\s+")


@dataclass
class MoreInfoEntry:
    func_name: str
    file_path: str
    topic: str | None
    format: str


@dataclass
class MoreInfoResult:
    func_name: str
    file_path: str
    topic: str | None
    raw_html: str
    plain_text: str


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
            entries[key] = MoreInfoEntry(func_name=fn, file_path=fp, topic=topic, format=fmt)
    return entries


def resolve_doc_path(tgf_path: Path, relative_path: str) -> Path:
    rel = relative_path.lstrip("$")
    return tgf_path.parent.parent / rel


def extract_topic_from_html(html_content: str, topic_name: str) -> str | None:
    """Extract the HTML block for *topic_name* from a modern More Info file.

    Modern files delimit each topic with ``<!-- [TOPIC_START_OPEN]... -->``
    and ``<!-- [TOPIC_END] -->`` markers.  Returns None when the markers
    are absent or the topic is not listed.
    """
    for match in _TOPIC_START.finditer(html_content):
        block_start = match.start()
        block_attrs = match.group(1)
        text_match = _TOPIC_TEXT.search(block_attrs)
        if text_match and text_match.group(1).strip() == topic_name:
            end_pos = html_content.find(_TOPIC_END, block_start)
            if end_pos != -1:
                tag_end = html_content.find("-->", block_start)
                return html_content[tag_end + 3:end_pos].strip()
    return None


def _plain_heading_text(fragment: str) -> str:
    """Collapse an HTML fragment to a single normalized text line."""
    return _WS_RUN.sub(" ", _TAG.sub("", fragment)).strip()


def _section_block(html_content: str, start_match: re.Match) -> str | None:
    """Return the section starting at heading *start_match*.

    Ends at the next heading of the same or a higher level (a sibling
    function), or at EOF.  Sub-sections (lower-level headings such as
    Arguments/Description) are kept inside the block.
    """
    level = int(start_match.group(1))
    start = start_match.start()
    for m in _HEADING_OPEN.finditer(html_content, start_match.end()):
        if int(m.group(1)) <= level:
            return html_content[start:m.start()]
    return html_content[start:]


def _heading_before(html_content: str, pos: int) -> re.Match | None:
    """The heading open tag immediately before *pos*, if any."""
    start_match = None
    for m in _HEADING_OPEN.finditer(html_content, 0, pos):
        start_match = m
    return start_match


def extract_topic_from_html_legacy(html_content: str, topic_name: str) -> str | None:
    """Extract a function section from legacy webflare HTML.

    Legacy Cadence SKILL reference files carry no TOPIC markers.  Functions
    are located either by an ``<a id="<func>">`` anchor (inside a heading
    that splits the name across the anchor) or by a heading whose plain text
    equals the function name.  Returns None when the function is not found.
    """
    # 1. Anchors: <a id="<topic>"> / <a name="<topic>">.
    m = re.search(rf'<a (?:id|name)="{re.escape(topic_name)}"', html_content)
    if m:
        heading = _heading_before(html_content, m.start())
        if heading is not None:
            block = _section_block(html_content, heading)
            if block:
                return block
    # 2. Heading text equal to the topic (anchors inside the heading are
    #    stripped, so split names like "iqCreateDummy...Cell" still match).
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
    """Extract the documentation section for *topic_name* from any format.

    Order of attempts:

    1. modern More Info markers (:func:`extract_topic_from_html`)
    2. legacy anchor/heading location (:func:`extract_topic_from_html_legacy`)
    3. the whole file when *fallback_whole_file* is set — appropriate for
       legacy files that index exactly one function, where the whole page
       is that function's documentation.
    """
    block = extract_topic_from_html(html_content, topic_name)
    if block is not None:
        return block
    block = extract_topic_from_html_legacy(html_content, topic_name)
    if block is not None:
        return block
    if fallback_whole_file:
        return html_content.strip()
    return None


def html_to_plain_text(html: str) -> str:
    """Convert HTML to clean markdown via markdownify.

    Pre-processing removes empty code tags that would otherwise produce
    orphaned backticks in the markdown output.
    """
    if not html or not html.strip():
        return ""

    # Remove empty/self-closing code tags BEFORE conversion.
    # The Cadence HTML has malformed structures like:
    #   [<code>ExtractShapeLimit</code><code></code>]
    # which would produce orphaned backticks.
    html = re.sub(r"<code[^>]*/>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<code[^>]*></code>", "", html, flags=re.IGNORECASE)

    return markdownify.markdownify(
        html,
        heading_style="ATX",
        code_language="",
        bold_symbol="**",
        italic_symbol="_",
    ).strip()


def get_all_indexed_files(tgf_entries: dict[str, MoreInfoEntry]) -> set[str]:
    return {entry.file_path for entry in tgf_entries.values()}
