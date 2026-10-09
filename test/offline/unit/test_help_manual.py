"""Help endpoint family (spec: 顶层补充·帮助体系 v7).

Offline: manual parser + business ``/help`` / ``/help/operations`` against a
temporary read-only manual root; no real middle is needed.
"""
from __future__ import annotations

import http.client
import json
import sys
import tempfile
import threading
import unittest
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from server import api_server
from server import dispatch as dispatch_module
from server.manual import Manual

_COMMON_MD = (
    "# 公共约定\n\n"
    "## 公共约定\n\n"
    "公共正文。\n\n"
    "### 响应壳\n\n"
    "壳正文。\n"
)

_HELPTEST_MD = (
    "# helptest\n\n"
    "## 1. `tb.help.run` — 测试运行\n\n"
    "运行正文。\n\n"
    "### 1.1 参数\n\n"
    "参数正文。\n\n"
    "## 2. `tb.multi.one` / `tb.multi.two` — 共享一节\n\n"
    "共享正文。\n"
)

_QUICKSTART_MD = "# 快速开始\n\nfixture quickstart\n"

_REFERENCE_MD = (
    "# 参考手册\n\n"
    "## 4. 注册与用户\n\n"
    "注册正文。\n\n"
    "### 4.1 六步注册\n\n"
    "六步正文。\n"
)


def _write_fixture(root: Path) -> None:
    (root / "packages").mkdir(parents=True, exist_ok=True)
    (root / "common.md").write_text(_COMMON_MD, encoding="utf-8")
    (root / "packages" / "helptest.md").write_text(_HELPTEST_MD, encoding="utf-8")
    (root / "01-快速开始.md").write_text(_QUICKSTART_MD, encoding="utf-8")
    (root / "02-参考手册.md").write_text(_REFERENCE_MD, encoding="utf-8")


class TestManualParser(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vb-help-")
        self.root = Path(self.tmp.name)
        _write_fixture(self.root)
        self.manual = Manual(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_operation_section_and_summary(self):
        section = self.manual.operation_section("helptest", "tb.help.run")
        self.assertIsNotNone(section)
        self.assertEqual(section.title, "1. `tb.help.run` — 测试运行")
        self.assertIn("运行正文。", section.body)
        self.assertIn("### 1.1 参数", section.body)  # deeper section stays attached
        self.assertEqual(self.manual.summary(section), "测试运行")

    def test_one_title_can_cover_multiple_operations(self):
        first = self.manual.operation_section("helptest", "tb.multi.one")
        second = self.manual.operation_section("helptest", "tb.multi.two")
        self.assertIsNotNone(first)
        self.assertIs(first, second)
        self.assertEqual(self.manual.summary(first), "共享一节")

    def test_common_section_prefers_deepest_exact_match(self):
        common = self.manual.common()
        self.assertIsNotNone(common)
        self.assertEqual(common.title, "公共约定")
        self.assertIn("### 响应壳", common.body)  # subsections stay in the section

    def test_quickstart_whole_file_and_registration_section(self):
        self.assertEqual(self.manual.quickstart(), _QUICKSTART_MD.strip())
        registration = self.manual.registration()
        self.assertIsNotNone(registration)
        self.assertTrue(registration.startswith("## 4. 注册与用户"))
        self.assertIn("注册正文。", registration)
        self.assertIn("### 4.1 六步注册", registration)

    def test_registration_prefers_dedicated_file_and_ignores_blank(self):
        registration_file = self.root / "registration.md"
        registration_file.write_text(
            "# 独立注册流程\n\n独立注册正文。\n", encoding="utf-8")
        self.assertEqual(
            Manual(self.root).registration(),
            "# 独立注册流程\n\n独立注册正文。",
        )

        registration_file.write_text("\n", encoding="utf-8")
        self.assertTrue(
            Manual(self.root).registration().startswith("## 4. 注册与用户"))

    def test_missing_manual_degrades(self):
        empty = Manual(Path(self.tmp.name) / "missing")
        self.assertIsNone(empty.quickstart())
        self.assertIsNone(empty.registration())
        self.assertIsNone(empty.operation_section("helptest", "tb.help.run"))
        self.assertEqual(empty.unavailable_reason("packages/helptest.md"),
                         "manual file not found")


@dataclass(frozen=True)
class _HelpRequest:
    token: str
    value: int = 0


class _HelpPackage:
    def __init__(self, middle):
        self.middle = middle

    def run(self, request):
        return None


_HelpPackage.__module__ = "pyapi.packages.helptest"


class TestBusinessHelpEndpoints(unittest.TestCase):
    OP = "tb.help.run"

    def setUp(self):
        dispatch_module.register_operation(
            self.OP, _HelpPackage, "run", _HelpRequest, replace=True
        )
        self.tmp = tempfile.TemporaryDirectory(prefix="vb-help-")
        self.root = Path(self.tmp.name)
        _write_fixture(self.root)
        self.server = api_server.build_server(
            "127.0.0.1", 0, object(), manual_root=self.root
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        dispatch_module.PACKAGES.pop(self.OP, None)
        self.tmp.cleanup()

    def _request(self, method, path):
        status, raw = self._request_raw(method, path)
        return status, json.loads(raw)

    def _request_raw(self, method, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request(method, path)
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        return resp.status, raw

    def test_help_root_returns_quickstart_text(self):
        status, body = self._request("GET", "/help")
        self.assertEqual(status, 200, body)
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"], _QUICKSTART_MD.strip())

    def test_success_shell_is_exact_and_does_not_leak_manual_root(self):
        for path in (
            "/help",
            "/help/operations",
            f"/help/operations?name={self.OP}",
        ):
            with self.subTest(path=path):
                status, raw = self._request_raw("GET", path)
                text = raw.decode("utf-8")
                body = json.loads(text)
                self.assertEqual(status, 200, body)
                self.assertEqual(set(body), {"ok", "data", "error"})
                self.assertTrue(body["ok"])
                self.assertIsNone(body["error"])
                self.assertNotIn(str(self.root), text)

    def test_operations_list_and_group_filter(self):
        status, body = self._request("GET", "/help/operations")
        self.assertEqual(status, 200, body)
        data = body["data"]
        entries = data["groups"]["helptest"]
        entry = next(item for item in entries if item["name"] == self.OP)
        self.assertEqual(entry["summary"], "测试运行")
        self.assertEqual(
            data["count"], sum(len(items) for items in data["groups"].values()))

        status, filtered = self._request("GET", "/help/operations?group=helptest")
        self.assertEqual(status, 200)
        self.assertEqual(list(filtered["data"]["groups"]), ["helptest"])
        self.assertEqual(filtered["data"]["count"], len(entries))

    def test_operation_detail(self):
        status, body = self._request(
            "GET", f"/help/operations?name={self.OP}")
        self.assertEqual(status, 200, body)
        data = body["data"]
        self.assertEqual(data["name"], self.OP)
        self.assertEqual(data["package"], "helptest")
        self.assertEqual(data["method"], "run")
        self.assertEqual(data["required_fields"], ["token"])
        self.assertEqual(data["request_schema"]["type"], "object")
        self.assertEqual(data["request_schema"]["required"], ["token"])
        self.assertEqual(
            data["request_schema"]["properties"]["token"]["type"], "string")
        self.assertEqual(data["doc"], {
            "file": "packages/helptest.md",
            "section_title": "1. `tb.help.run` — 测试运行",
        })
        self.assertEqual(data["content_format"], "markdown")
        self.assertEqual(data["common_ref"],
                         {"file": "common.md", "section_title": "公共约定"})
        self.assertEqual(
            data["content"], "运行正文。\n\n### 1.1 参数\n\n参数正文。")
        self.assertEqual(
            data["common"], "公共正文。\n\n### 响应壳\n\n壳正文。")
        self.assertEqual(set(data), {
            "name", "package", "method", "required_fields", "request_schema",
            "doc", "content_format", "common_ref", "common", "content",
        })

    def test_common_flag_and_unknown_operation(self):
        status, body = self._request(
            "GET", f"/help/operations?name={self.OP}&common=0")
        self.assertEqual(status, 200, body)
        self.assertNotIn("common", body["data"])
        self.assertIn("common_ref", body["data"])

        status, body = self._request(
            "GET", "/help/operations?name=tb.help.missing")
        self.assertEqual(status, 404)
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"], "unknown operation: tb.help.missing")

    def test_missing_manual_degrades_without_error(self):
        server = api_server.build_server(
            "127.0.0.1", 0, object(), manual_root=self.root / "missing"
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            conn.request("GET", f"/help/operations?name={self.OP}")
            resp = conn.getresponse()
            body = json.loads(resp.read())
            conn.close()
            self.assertEqual(resp.status, 200, body)
            data = body["data"]
            self.assertNotIn("content", data)
            self.assertEqual(data["content_unavailable"], "manual file not found")
            self.assertEqual(data["request_schema"]["type"], "object")

            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            conn.request("GET", "/help")
            resp = conn.getresponse()
            help_body = json.loads(resp.read())
            conn.close()
            self.assertEqual(help_body["data"], api_server._FALLBACK_QUICKSTART)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_missing_operation_section_degrades_with_section_reason(self):
        operation = "tb.help.no_manual_section"
        dispatch_module.register_operation(
            operation, _HelpPackage, "run", _HelpRequest, replace=True)
        try:
            status, listing = self._request(
                "GET", "/help/operations?group=helptest")
            self.assertEqual(status, 200, listing)
            entry = next(
                item for item in listing["data"]["groups"]["helptest"]
                if item["name"] == operation)
            self.assertEqual(entry, {"name": operation})

            status, body = self._request(
                "GET", f"/help/operations?name={operation}")
            self.assertEqual(status, 200, body)
            data = body["data"]
            self.assertNotIn("content", data)
            self.assertEqual(
                data["content_unavailable"], "manual section not found")
            self.assertIsNone(data["doc"]["section_title"])
            self.assertEqual(data["request_schema"]["type"], "object")
        finally:
            dispatch_module.PACKAGES.pop(operation, None)


if __name__ == "__main__":
    unittest.main()
