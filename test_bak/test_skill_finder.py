from __future__ import annotations

import json

import virtuoso_bridge
from virtuoso_bridge.cli import main
from virtuoso_bridge.virtuoso.basic.bridge import VirtuosoClient
from virtuoso_bridge.virtuoso.skill_finder import SKILLFinder
from virtuoso_bridge.virtuoso.skill_finder.more_info import (
    extract_doc_section,
    html_to_plain_text,
)


class _FakeSkillClient:
    def __init__(self) -> None:
        self.find_calls: list[tuple[str, str, int, bool]] = []

    def find_skill(self, query: str, *, mode: str = "fuzzy", limit: int = 50, include_desc: bool = False):
        self.find_calls.append((query, mode, limit, include_desc))
        return [
            {
                "name": "dbOpenCellViewByType",
                "syntax": "dbOpenCellViewByType(lib cell view)",
                "description": "Open a cellview.",
                "source_file": "database.fnd",
            }
        ]

    def get_skill_more_info(self, func_name: str):
        return {
            "func_name": func_name,
            "file_path": "$database/db.html",
            "topic": func_name,
            "raw_html": "<h1>dbOpenCellViewByType</h1>",
            "plain_text": "# dbOpenCellViewByType",
        }


def _patch_cli_client(monkeypatch):
    fake = _FakeSkillClient()
    seen_profiles: list[str | None] = []

    class _FakeVirtuosoClient:
        @classmethod
        def from_env(cls, profile=None):
            seen_profiles.append(profile)
            return fake

    monkeypatch.setattr(virtuoso_bridge, "VirtuosoClient", _FakeVirtuosoClient)
    monkeypatch.setattr("virtuoso_bridge.cli._load_cli_env", lambda: None)
    monkeypatch.setattr("virtuoso_bridge.profile.resolve_profile", lambda explicit=None: explicit)
    return fake, seen_profiles


def test_skill_find_json_flag_emits_json(capsys, monkeypatch):
    fake, seen_profiles = _patch_cli_client(monkeypatch)

    rc = main(["skill-find", "dbOpen", "--json", "--mode", "prefix", "--limit", "3"])

    assert rc == 0
    assert fake.find_calls == [("dbOpen", "prefix", 3, False)]
    assert seen_profiles == [None]
    parsed = json.loads(capsys.readouterr().out)
    assert parsed[0]["name"] == "dbOpenCellViewByType"


def test_skill_find_passes_explicit_profile(capsys, monkeypatch):
    _fake, seen_profiles = _patch_cli_client(monkeypatch)

    rc = main(["skill-find", "dbOpen", "-p", "worker1", "--json"])

    assert rc == 0
    assert seen_profiles == ["worker1"]
    assert json.loads(capsys.readouterr().out)[0]["source_file"] == "database.fnd"


def test_skill_find_passes_include_desc_with_explicit_profile(capsys, monkeypatch):
    fake, seen_profiles = _patch_cli_client(monkeypatch)

    rc = main(["skill-find", "open.*cellview", "--mode", "regex", "-p", "worker1", "--json", "--include-desc"])

    assert rc == 0
    assert seen_profiles == ["worker1"]
    assert json.loads(capsys.readouterr().out)[0]["source_file"] == "database.fnd"


def test_skill_info_passes_explicit_profile(capsys, monkeypatch):
    _fake, seen_profiles = _patch_cli_client(monkeypatch)

    rc = main(["skill-info", "dbOpenCellViewByType", "-p", "worker1", "--json"])

    assert rc == 0
    assert seen_profiles == ["worker1"]
    assert json.loads(capsys.readouterr().out)["func_name"] == "dbOpenCellViewByType"


class _LocalTunnel:
    _ssh_runner = None
    _remote_host = "localhost"


def _write_finder_tree(tmp_path):
    doc_root = tmp_path / "ic" / "doc"
    skill_root = doc_root / "finder" / "SKILL" / "database"
    skill_root.mkdir(parents=True)
    (skill_root / "database.fnd").write_text(
        '("dbOpenCellViewByType"\n'
        '"dbOpenCellViewByType(lib cell view)"\n'
        '"Open a cellview.")\n',
        encoding="utf-8",
    )

    more_info_dir = doc_root / "api_more_info"
    more_info_dir.mkdir()
    (more_info_dir / "api_more_info.tgf").write_text(
        "dbOpenCellViewByType $database/db.html NULL HTML\n",
        encoding="utf-8",
    )
    html_dir = doc_root / "database"
    html_dir.mkdir()
    (html_dir / "db.html").write_text(
        "<html><body><h1>dbOpenCellViewByType</h1><p>Open a cellview.</p></body></html>",
        encoding="utf-8",
    )
    return skill_root.parent


def test_find_skill_uses_local_discovery_when_tunnel_has_no_ssh_runner(monkeypatch, tmp_path):
    skill_root = _write_finder_tree(tmp_path)

    def fake_discover(self, remote_runner=None, profile=None):
        assert remote_runner is None
        return skill_root

    monkeypatch.setattr(SKILLFinder, "discover", fake_discover)

    client = VirtuosoClient(tunnel=_LocalTunnel())
    results = client.find_skill("dbOpenCellViewByType", mode="exact")

    assert results == [
        {
            "name": "dbOpenCellViewByType",
            "syntax": "dbOpenCellViewByType(lib cell view)",
            "description": "Open a cellview.",
            "source_file": "database.fnd",
        }
    ]


def test_skill_more_info_uses_local_discovery_when_tunnel_has_no_ssh_runner(monkeypatch, tmp_path):
    skill_root = _write_finder_tree(tmp_path)

    def fake_discover(self, remote_runner=None, profile=None):
        assert remote_runner is None
        return skill_root

    monkeypatch.setattr(SKILLFinder, "discover", fake_discover)

    client = VirtuosoClient(tunnel=_LocalTunnel())
    result = client.get_skill_more_info("dbOpenCellViewByType", cache_dir=tmp_path / "cache")

    assert result is not None
    assert result["func_name"] == "dbOpenCellViewByType"
    assert "Open a cellview." in result["plain_text"]


def _write_legacy_finder_tree(tmp_path):
    """Legacy (webflare) docs: no TOPIC markers, one <h3> section per function.

    Mirrors real pre-More-Info Cadence SKILL reference HTML where a numeric
    page anchor and the function anchor are embedded inside the heading, and
    the name text is split across the anchor.
    """
    doc_root = tmp_path / "ic" / "doc"
    skill_root = doc_root / "finder" / "SKILL" / "database"
    skill_root.mkdir(parents=True)
    (skill_root / "database.fnd").write_text(
        '("dbOpenCellViewByType"\n'
        '"dbOpenCellViewByType(lib cell view)"\n'
        '"Open a cellview.")\n',
        encoding="utf-8",
    )

    more_info_dir = doc_root / "api_more_info"
    more_info_dir.mkdir()
    (more_info_dir / "api_more_info.tgf").write_text(
        'dbOpenCellViewByType $database/db.html "dbOpenCellViewByType" HTML\n'
        'dbSave $database/db.html "dbSave" HTML\n',
        encoding="utf-8",
    )
    html_dir = doc_root / "database"
    html_dir.mkdir()
    (html_dir / "db.html").write_text(
        "<html><body>"
        '<h1>Cellview IO Functions</h1>'
        '<h3><a id="pgfId-1"></a><a id="20044"></a>dbOpenCellView'
        '<a id="dbOpenCellViewByType"></a>ByType</h3>'
        "<p>Opens a cellview by type.</p>"
        '<h3><a id="pgfId-2"></a>dbSave</h3>'
        "<p>Saves a cellview.</p>"
        "</body></html>",
        encoding="utf-8",
    )
    return doc_root


def _legacy_finder_root(doc_root):
    return doc_root / "finder" / "SKILL"


def test_skill_more_info_legacy_html_section_split(monkeypatch, tmp_path):
    """Legacy webflare HTML without TOPIC markers must still resolve.

    The section is located via the <a id="func"> anchor inside the heading;
    a sibling function's <h3> must NOT leak into the result.
    """
    doc_root = _write_legacy_finder_tree(tmp_path)
    finder_root = _legacy_finder_root(doc_root)

    def fake_discover(self, remote_runner=None, profile=None):
        assert remote_runner is None
        return finder_root

    monkeypatch.setattr(SKILLFinder, "discover", fake_discover)

    client = VirtuosoClient(tunnel=_LocalTunnel())
    result = client.get_skill_more_info("dbOpenCellViewByType", cache_dir=tmp_path / "cache")

    assert result is not None
    assert result["func_name"] == "dbOpenCellViewByType"
    assert result["topic"] == "dbOpenCellViewByType"
    assert "Opens a cellview by type." in result["plain_text"]
    assert "Saves a cellview." not in result["plain_text"]  # sibling section excluded


def test_skill_more_info_legacy_html_heading_text_match(monkeypatch, tmp_path):
    """Legacy HTML with no id anchor must resolve via heading text equality."""
    doc_root = _write_legacy_finder_tree(tmp_path)
    finder_root = _legacy_finder_root(doc_root)
    # Second function has no id-anchor — only the heading text matches.
    (doc_root / "database" / "db.html").write_text(
        "<html><body>"
        '<h3><a id="pgfId-10"></a>dbSa<a id="marker-11"></a>ve</h3>'
        "<p>Saves a cellview.</p>"
        "</body></html>",
        encoding="utf-8",
    )

    def fake_discover(self, remote_runner=None, profile=None):
        assert remote_runner is None
        return finder_root

    monkeypatch.setattr(SKILLFinder, "discover", fake_discover)

    client = VirtuosoClient(tunnel=_LocalTunnel())
    result = client.get_skill_more_info("dbSave", cache_dir=tmp_path / "cache")

    assert result is not None
    assert result["func_name"] == "dbSave"
    assert "Saves a cellview." in result["plain_text"]


def test_skill_more_info_legacy_null_topic_whole_file(monkeypatch, tmp_path):
    """NULL topic in a legacy file means whole-file docs; a precise section
    match is preferred when the function heading exists, otherwise the whole
    file is returned."""
    doc_root = _write_legacy_finder_tree(tmp_path)
    finder_root = _legacy_finder_root(doc_root)
    tgf_path = doc_root / "api_more_info" / "api_more_info.tgf"
    tgf_path.write_text(
        "dbSave $database/db.html NULL HTML\n", encoding="utf-8"
    )

    def fake_discover(self, remote_runner=None, profile=None):
        assert remote_runner is None
        return finder_root

    monkeypatch.setattr(SKILLFinder, "discover", fake_discover)

    client = VirtuosoClient(tunnel=_LocalTunnel())
    result = client.get_skill_more_info("dbSave", cache_dir=tmp_path / "cache")

    assert result is not None
    assert result["topic"] is None
    # dbSave heading is locatable → precise section is preferred over the
    # whole-file fallback
    assert "Saves a cellview." in result["plain_text"]
    assert "Opens a cellview by type." not in result["plain_text"]


def test_extract_doc_section_modern_markers_first():
    """Modern TOPIC markers win over legacy fallbacks."""
    html = (
        "<html><body>"
        "<!-- [TOPIC_START_OPEN][TOPIC_START_ATTR]text=dbSave -->"
        "<h3>dbSave</h3><p>Modern save doc.</p>"
        "<!-- [TOPIC_END] -->"
        "<h3>dbClose</h3><p>Legacy close doc.</p>"
        "</body></html>"
    )
    block = extract_doc_section(html, "dbSave")
    assert block is not None
    assert "Modern save doc." in block
    assert "dbClose" not in block


def test_extract_doc_section_legacy_no_markers():
    """Legacy HTML without markers resolves via heading text."""
    html = (
        "<html><body>"
        '<h3><a id="pgfId-1"></a>dbSa<a id="marker-2"></a>ve</h3>'
        "<p>Saves legacy cellview.</p>"
        "</body></html>"
    )
    block = extract_doc_section(html, "dbSave")
    assert block is not None
    assert "Saves legacy cellview." in block


def test_extract_doc_section_whole_file_fallback():
    """Unknown topic falls back to the whole file only when allowed."""
    html = "<html><body><p>Whole page docs.</p></body></html>"
    # Not allowed → None
    assert extract_doc_section(html, "ghostFunc") is None
    # Allowed → whole file
    block = extract_doc_section(html, "ghostFunc", fallback_whole_file=True)
    assert block is not None
    assert html_to_plain_text(block) == "Whole page docs."
