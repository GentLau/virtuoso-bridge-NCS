"""skillref 业务包单元测试：本地/远端取数、四层匹配、错误口径。

用临时 doc 树 + 假 Middle（不碰真机），覆盖 spec ``9-skillref.md`` §4/§5 的主要分支。
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from common.paths import override_work_dir_for_tests
from pyapi.models import CommandResult, ExecutionStatus, QueryResult
from pyapi.packages import skillref as skillref_mod
from pyapi.packages.skillref import (
    InfoRequest,
    OPERATIONS,
    Package,
    SearchRequest,
)

FPX = "caller-token"
DOC_TOKEN = "doc-token"

FND_CORE = """;SKILL Language Functions
("fnAlpha"
"fnAlpha(
t_x
) => t / nil"
"Does alpha things.")
("fnBeta"
"fnBeta() => nil"
"Beta helper.")
("fnGamma"
"fnGamma() => t"
"Ground bounce calculator.")
"""

TGF = """fnAlpha $ref/modern.html "fnAlpha" HTML
fnBeta $ref/modern.html "fnBeta" HTML
fnLegacy $legacy/legacy.html NULL HTML
"""

MODERN_HTML = """<html><head><title>Modern Reference</title></head><body>
<!-- [TOPIC_START_OPEN] [TOPIC_START_ATTR]text=fnAlpha -->
<h3>fnAlpha</h3><p>Alpha does X.</p>
<!-- [TOPIC_END] -->
<!-- [TOPIC_START_OPEN] [TOPIC_START_ATTR]text=fnBeta -->
<h3>fnBeta</h3><p>Beta does Y.</p>
<!-- [TOPIC_END] -->
</body></html>
"""

LEGACY_HTML = """<html><body>
<h2><a name="fnLegacy"></a>fnLegacy</h2><p>Legacy body text.</p>
<h2>Unrelated</h2><p>other section</p>
</body></html>
"""

CPF_HTML = """<html><head><title>CPF Reference</title></head><body>
<p>Specifies the maximum allowed average ground bounce on the specified ground nets.</p>
</body></html>
"""


def build_doc_tree(root: Path) -> Path:
    (root / "finder" / "SKILL" / "Core_SKILL").mkdir(parents=True)
    (root / "finder" / "SKILL" / "Core_SKILL" / "core.fnd").write_text(
        FND_CORE, encoding="utf-8"
    )
    (root / "api_more_info").mkdir(parents=True)
    (root / "api_more_info" / "api_more_info.tgf").write_text(TGF, encoding="utf-8")
    (root / "ref").mkdir(parents=True)
    (root / "ref" / "modern.html").write_text(MODERN_HTML, encoding="utf-8")
    (root / "legacy").mkdir(parents=True)
    (root / "legacy" / "legacy.html").write_text(LEGACY_HTML, encoding="utf-8")
    (root / "cpf_ref").mkdir(parents=True)
    (root / "cpf_ref" / "reference.html").write_text(CPF_HTML, encoding="utf-8")
    (root / "other").mkdir(parents=True)
    (root / "other" / "notes.txt").write_text("nothing interesting here\n", encoding="utf-8")
    return root


class FakeMiddle:
    """假中层：query 校验 + C/D 用本地 fixture 模拟远端。"""

    def __init__(self, remote_root: Path | None = None) -> None:
        self.remote_root = remote_root
        self.calls: list[tuple] = []

    def query(self, *, token: str) -> QueryResult:
        self.calls.append(("query", token))
        if token == FPX:
            return QueryResult(status=ExecutionStatus.SUCCESS)
        return QueryResult(status=ExecutionStatus.ERROR, errors=["invalid token"])

    def run_command(self, cmd, timeout=None, *, token, parallel=False) -> CommandResult:
        self.calls.append(("run_command", token, cmd))
        return CommandResult(
            returncode=0, stdout="cpf_ref/reference.html\n", stderr="", kind="command"
        )

    def download_file(self, remote_path, local_path, timeout=None, *, token,
                      recursive=False) -> CommandResult:
        self.calls.append(("download_file", token, str(remote_path), recursive))
        if token != DOC_TOKEN:
            return CommandResult(
                returncode=1, stdout="", stderr="invalid token", kind="invalid-token"
            )
        if self.remote_root is None:
            return CommandResult(
                returncode=1, stdout="", stderr="path not visible", kind="path-not-visible"
            )
        relative = str(remote_path).replace(str(self.remote_root), "").strip("/")
        source = self.remote_root / relative
        target = Path(local_path)
        if recursive:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return CommandResult(returncode=0, stdout="", stderr="", kind="command")


class SkillrefBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="vb-skillref-"))
        override_work_dir_for_tests(self.tmp / "work")
        self.doc = build_doc_tree(self.tmp / "doc")
        self._orig_snapshot = skillref_mod._config_snapshot
        skillref_mod._config_snapshot = lambda: None

    def tearDown(self) -> None:
        skillref_mod._config_snapshot = self._orig_snapshot
        shutil.rmtree(self.tmp, ignore_errors=True)

    def config(self, section: dict | None) -> None:
        skillref_mod._config_snapshot = (
            lambda: ({} if section is None else {"skillref": section})
        )

    def local_search(self, middle: FakeMiddle, **fields):
        base = {"token": FPX, "query": "fnAlpha", "source": "local", "doc_root": str(self.doc)}
        base.update(fields)
        return Package(middle).search(SearchRequest(**base))


class TestSearchLocal(SkillrefBase):
    def test_operations_registered(self):
        self.assertEqual(
            {op[0] for op in OPERATIONS},
            {"virtuoso.skillref.search", "virtuoso.skillref.info"},
        )

    def test_name_layer_exact(self):
        middle = FakeMiddle()
        result = self.local_search(middle, search_in="name", mode="exact")
        self.assertTrue(result.ok, result.error)
        self.assertEqual([hit["name"] for hit in result.results], ["fnAlpha"])
        self.assertEqual(result.results[0]["layer"], "name")
        self.assertEqual(result.results[0]["score"], 100)
        self.assertFalse([call for call in middle.calls if call[0] == "download_file"])

    def test_entry_layer_matches_description(self):
        middle = FakeMiddle()
        result = self.local_search(middle, query="bounce", search_in="entry")
        self.assertTrue(result.ok, result.error)
        self.assertEqual([hit["name"] for hit in result.results], ["fnGamma"])
        self.assertIn("description", result.results[0]["why"])
        self.assertEqual(result.results[0]["layer"], "entry")

    def test_topic_layer_is_cumulative(self):
        middle = FakeMiddle()
        result = self.local_search(middle, query="fnLegacy", search_in="topic")
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.layers_run, ["name", "entry", "topic"])
        self.assertIn("topic", {hit["layer"] for hit in result.results})
        self.assertEqual(result.results[0]["target_path"], "$legacy/legacy.html")

    def test_body_layer_with_under(self):
        middle = FakeMiddle()
        result = self.local_search(
            middle, query="ground bounce", search_in="body", under=["cpf_ref"]
        )
        self.assertTrue(result.ok, result.error)
        body_hits = [hit for hit in result.results if hit["layer"] == "body"]
        self.assertEqual(len(body_hits), 1)
        hit = body_hits[0]
        self.assertEqual(hit["relative_path"], "cpf_ref/reference.html")
        self.assertIn("ground bounce", hit["snippet"])
        self.assertEqual(result.scanned_files, 1)
        self.assertFalse(result.truncated)
        # 词条层（fnGamma 描述含 "Ground bounce"）也在结果里 —— cumulative 语义
        self.assertIn("entry", {item["layer"] for item in result.results})

    def test_body_layer_truncates_without_under(self):
        middle = FakeMiddle()
        result = self.local_search(
            middle, query="ground bounce", search_in="body", max_files=1
        )
        self.assertTrue(result.ok, result.error)
        self.assertTrue(result.truncated)

    def test_limit_is_applied(self):
        middle = FakeMiddle()
        result = self.local_search(middle, query="fn", search_in="name", limit=1)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(len(result.results), 1)


class TestSourceResolution(SkillrefBase):
    def test_missing_source_is_business_failure(self):
        middle = FakeMiddle()
        result = Package(middle).search(SearchRequest(token=FPX, query="fnAlpha"))
        self.assertFalse(result.ok)
        self.assertIn("数据源未配置", result.error or "")

    def test_partial_request_source_is_business_failure(self):
        middle = FakeMiddle()
        result = Package(middle).search(
            SearchRequest(token=FPX, query="fnAlpha", source="local")
        )
        self.assertFalse(result.ok)
        self.assertIn("同时给出 source 与 doc_root", result.error or "")

    def test_source_from_config_snapshot(self):
        self.config({"source": "local", "doc_root": str(self.doc)})
        middle = FakeMiddle()
        result = Package(middle).search(SearchRequest(token=FPX, query="fnAlpha"))
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.source, "local")

    def test_remote_without_doc_token_fails(self):
        self.config({"source": "remote", "doc_root": "/remote/doc"})
        middle = FakeMiddle(remote_root=self.doc)
        result = Package(middle).search(SearchRequest(token=FPX, query="fnAlpha"))
        self.assertFalse(result.ok)
        self.assertIn("doc_token", result.error or "")

    def test_invalid_caller_token_fails(self):
        middle = FakeMiddle()
        result = Package(middle).search(
            SearchRequest(token="wrong", query="fnAlpha", source="local",
                          doc_root=str(self.doc))
        )
        self.assertFalse(result.ok)
        self.assertTrue((result.error or "").startswith("invalid token"))


class TestSearchRemote(SkillrefBase):
    def test_remote_search_uses_doc_token(self):
        self.config({"source": "remote", "doc_root": str(self.doc), "doc_token": DOC_TOKEN})
        middle = FakeMiddle(remote_root=self.doc)
        result = Package(middle).search(
            SearchRequest(token=FPX, query="fnAlpha", search_in="topic")
        )
        self.assertTrue(result.ok, result.error)
        downloads = [call for call in middle.calls if call[0] == "download_file"]
        self.assertTrue(downloads)
        self.assertTrue(all(call[1] == DOC_TOKEN for call in downloads))
        self.assertEqual(result.source, "remote")

    def test_remote_body_uses_grep_then_download(self):
        self.config({"source": "remote", "doc_root": str(self.doc), "doc_token": DOC_TOKEN})
        middle = FakeMiddle(remote_root=self.doc)
        result = Package(middle).search(SearchRequest(
            token=FPX, query="ground bounce", search_in="body", under=["cpf_ref"],
        ))
        self.assertTrue(result.ok, result.error)
        commands = [call for call in middle.calls if call[0] == "run_command"]
        self.assertEqual(len(commands), 1)
        self.assertIn("grep -r -l -m1 -F", commands[0][2])
        self.assertEqual(
            [hit["relative_path"] for hit in result.results if hit["layer"] == "body"],
            ["cpf_ref/reference.html"],
        )

    def test_invalid_doc_token_message(self):
        self.config({"source": "remote", "doc_root": str(self.doc), "doc_token": "revoked"})
        middle = FakeMiddle(remote_root=self.doc)
        result = Package(middle).search(SearchRequest(token=FPX, query="fnAlpha"))
        self.assertFalse(result.ok)
        self.assertIn("doc_token", result.error or "")


class TestInfo(SkillrefBase):
    def test_info_modern_topic(self):
        middle = FakeMiddle()
        result = Package(middle).info(InfoRequest(
            token=FPX, name="fnAlpha", source="local", doc_root=str(self.doc),
        ))
        self.assertTrue(result.ok, result.error)
        self.assertTrue(result.found)
        self.assertEqual(result.func_name, "fnAlpha")
        self.assertIn("Alpha does X", result.plain_text)
        self.assertIsNone(result.raw_html)

    def test_info_include_raw(self):
        middle = FakeMiddle()
        result = Package(middle).info(InfoRequest(
            token=FPX, name="fnAlpha", source="local", doc_root=str(self.doc),
            include_raw=True,
        ))
        self.assertTrue(result.found)
        self.assertIn("Alpha does X", result.raw_html or "")

    def test_info_legacy_null_topic_falls_back_to_whole_file(self):
        middle = FakeMiddle()
        result = Package(middle).info(InfoRequest(
            token=FPX, name="fnLegacy", source="local", doc_root=str(self.doc),
        ))
        self.assertTrue(result.ok, result.error)
        self.assertTrue(result.found)
        self.assertIn("Legacy body text", result.plain_text)

    def test_info_unknown_function_is_not_found(self):
        middle = FakeMiddle()
        result = Package(middle).info(InfoRequest(
            token=FPX, name="noSuchFn", source="local", doc_root=str(self.doc),
        ))
        self.assertTrue(result.ok, result.error)
        self.assertFalse(result.found)

    def test_info_remote_uses_doc_token(self):
        self.config({"source": "remote", "doc_root": str(self.doc), "doc_token": DOC_TOKEN})
        middle = FakeMiddle(remote_root=self.doc)
        result = Package(middle).info(InfoRequest(token=FPX, name="fnAlpha"))
        self.assertTrue(result.ok, result.error)
        self.assertTrue(result.found)
        self.assertEqual(result.source, "remote")
        self.assertTrue(all(call[1] == DOC_TOKEN
                            for call in middle.calls if call[0] == "download_file"))


class TestValidation(SkillrefBase):
    def test_bad_search_in(self):
        with self.assertRaises(ValueError):
            SearchRequest(token=FPX, query="x", search_in="bogus")

    def test_bad_mode(self):
        with self.assertRaises(ValueError):
            SearchRequest(token=FPX, query="x", mode="glob")

    def test_bad_limit(self):
        with self.assertRaises(ValueError):
            SearchRequest(token=FPX, query="x", limit=0)

    def test_bad_under(self):
        with self.assertRaises(ValueError):
            SearchRequest(token=FPX, query="x", under=["../etc"])

    def test_timeout_must_be_positive(self):
        with self.assertRaises(ValueError):
            SearchRequest(token=FPX, query="x", timeout=-1)


class TestConfigSnapshotWiring(SkillrefBase):
    """真实 ``common.config`` 快照路径（不 monkeypatch 快照函数）。"""

    def setUp(self) -> None:
        super().setUp()
        skillref_mod._config_snapshot = self._orig_snapshot
        from common import config as common_config

        self.common_config = common_config
        self.config_path = self.tmp / "work" / "config.json"

    def test_section_from_real_snapshot(self):
        self.config_path.write_text(
            json.dumps({
                "business_thread_pool_size": 8,
                "skillref": {"source": "local", "doc_root": str(self.doc)},
            }),
            encoding="utf-8",
        )
        self.common_config.reload_config(self.config_path)
        snapshot = skillref_mod._config_snapshot()
        self.assertIsInstance(snapshot, dict)
        self.assertEqual(snapshot["skillref"]["doc_root"], str(self.doc))

        middle = FakeMiddle()
        result = Package(middle).search(SearchRequest(token=FPX, query="fnAlpha"))
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.source, "local")

    def test_missing_section_is_business_failure(self):
        self.config_path.write_text(json.dumps({"business_thread_pool_size": 8}),
                                    encoding="utf-8")
        self.common_config.reload_config(self.config_path)
        middle = FakeMiddle()
        result = Package(middle).search(SearchRequest(token=FPX, query="fnAlpha"))
        self.assertFalse(result.ok)
        self.assertIn("数据源未配置", result.error or "")


if __name__ == "__main__":
    unittest.main()
