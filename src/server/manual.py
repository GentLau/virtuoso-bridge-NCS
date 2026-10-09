"""Read-only manual access for the ``/help`` endpoint family.

Spec: ``spec/design-concepts/顶层/add-帮助体系.md`` (Normative).  The manual
ships with the service under ``skills/virtuoso-bridge/manual/`` and is
read-only: missing files degrade the help endpoints (schema/doc only), never
the business endpoints.  Paths exposed to callers are always relative to the
manual root (no absolute paths, hostnames or registry content).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


def default_manual_root() -> Path:
    """Repo-relative default, falling back to ``./manual`` outside a checkout."""
    repo_manual = (Path(__file__).resolve().parents[2]
                   / "skills" / "virtuoso-bridge" / "manual")
    if repo_manual.is_dir():
        return repo_manual
    cwd_manual = Path.cwd() / "manual"
    return cwd_manual if cwd_manual.is_dir() else repo_manual


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_EM_DASH = "\u2014"

#: Whole-file texts for the two ``/help`` roots.  Dedicated files win; the
#: current manual layout is the fallback.
_QUICKSTART_FILES = ("quickstart.md", "01-快速开始.md")
_REGISTRATION_FILES = ("registration.md", "注册流程.md")


@dataclass(frozen=True)
class ManualSection:
    file: str        # relative to the manual root
    title: str       # heading text without the leading '#'
    body: str        # raw section body (heading line excluded)
    level: int       # number of '#' characters


def _split_sections(rel: str, text: str) -> list[ManualSection]:
    lines = text.splitlines()
    headings: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if match:
            headings.append((index, len(match.group(1)), match.group(2).strip()))
    sections: list[ManualSection] = []
    for pos, (start, level, title) in enumerate(headings):
        end = len(lines)
        for next_start, next_level, _next_title in headings[pos + 1:]:
            if next_level <= level:
                end = next_start
                break
        body = "\n".join(lines[start + 1:end]).strip("\n")
        sections.append(ManualSection(rel, title, body, level))
    return sections


class Manual:
    """Lazy, read-only view over one manual root."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root).expanduser() if root is not None else default_manual_root()
        self._texts: dict[str, str | None] = {}
        self._sections: dict[str, list[ManualSection]] = {}

    # -- raw files ---------------------------------------------------------
    def _text(self, rel: str) -> str | None:
        if rel not in self._texts:
            try:
                self._texts[rel] = (self.root / rel).read_text(encoding="utf-8")
            except OSError:
                self._texts[rel] = None
        return self._texts[rel]

    def sections(self, rel: str) -> list[ManualSection]:
        if rel not in self._sections:
            text = self._text(rel)
            self._sections[rel] = _split_sections(rel, text) if text else []
        return self._sections[rel]

    def quickstart(self) -> str | None:
        """Business ``/help`` text: whole quickstart file, raw."""
        return self._first_text(_QUICKSTART_FILES)

    def registration(self) -> str | None:
        """Control ``/help`` text: whole registration file, else its section."""
        whole = self._first_text(_REGISTRATION_FILES)
        if whole is not None:
            return whole
        for rel, needle in (("02-参考手册.md", "注册与用户"),
                            ("01-快速开始.md", "注册")):
            section = self.section_by_title(rel, needle)
            if section is not None:
                return _render_section(section)
        return None

    def _first_text(self, names: tuple[str, ...]) -> str | None:
        for name in names:
            text = self._text(name)
            if text is not None and text.strip():
                return text.strip()
        return None

    # -- sections ----------------------------------------------------------
    def section_by_title(self, rel: str, needle: str) -> ManualSection | None:
        matches = [s for s in self.sections(rel) if needle in s.title]
        if not matches:
            return None
        return min(matches, key=lambda s: s.level)

    def common(self) -> ManualSection | None:
        """The ``common.md`` 「公共约定」 section (deepest exact match)."""
        exact = [
            section for section in self.sections("common.md")
            if section.title.strip().strip("`") == "公共约定"
        ]
        if exact:
            return max(exact, key=lambda s: s.level)
        return self.section_by_title("common.md", "公共约定")

    def operation_section(self, package: str, operation: str) -> ManualSection | None:
        """Section whose title contains the operation name in backticks."""
        rel = f"packages/{package}.md"
        for section in self.sections(rel):
            if operation in _BACKTICK_RE.findall(section.title):
                return section
        return None

    @staticmethod
    def summary(section: ManualSection | None) -> str | None:
        """Short title after the em dash; ``None`` when absent."""
        if section is None:
            return None
        _prefix, separator, suffix = section.title.partition(_EM_DASH)
        if not separator:
            return None
        return suffix.strip() or None

    def unavailable_reason(self, rel: str) -> str:
        """Short reason for ``content_unavailable`` (no paths leak)."""
        return "manual file not found" if self._text(rel) is None else "manual section not found"


def _render_section(section: ManualSection) -> str:
    heading = "#" * section.level + " " + section.title
    return f"{heading}\n\n{section.body}".strip()


__all__ = [
    "Manual",
    "ManualSection",
    "default_manual_root",
]
