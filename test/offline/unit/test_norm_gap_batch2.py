# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-28 20:40
# 依赖: 无
# =======================================================================
"""第八轮 gap-actions 的离线批次（条款级缺口 → 直接断言）。

覆盖 `test/reports/round8/round8-gap-actions.md` 里的离线可闭合项：

  * skillref#103  `search_in="all"` 必须等价于最深一档 `body`
  * skillref#140  `max_candidates` 同时是**下载上限**
  * skillref#141  正文层远端候选搜索默认 120 s，调用方可覆盖
  * skillref#062  远端路径禁止本地 stat（`Path.exists()/is_dir()`）
  * schematic#017 `focus` 含 `connectivity` 时忽略 `object_filter`
  * layout#139    禁止不带 bbox 的 `hiZoomIn`/`hiZoomOut`

第 1 步（环境检查）：离线用例，不需要真机环境检查。
第 3 步（构建前置）：每一类自带 fake 中层 / 本地 doc 树，见 setUp。
"""

from __future__ import annotations

import ast
import json
import shutil
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pyapi.packages.layout as L  # noqa: E402
import pyapi.packages.schematic as S  # noqa: E402
import pyapi.packages.skillref as SR  # noqa: E402
import test_skillref_package as SR_TB  # noqa: E402  （复用同一份 doc 树 fixture）
from pyapi.models import CommandResult, ExecutionStatus, QueryResult  # noqa: E402

DOC_TOKEN = "doc-token-ok"
CALLER = "caller-token"


class _FakeMiddle:
    """最小中层替身：命令/下载可编程，记录每次调用的 timeout。"""

    def __init__(self, grep_lines=None, remote_root: Path | None = None):
        self.grep_lines = list(grep_lines or [])
        self.remote_root = remote_root
        self.calls: list[tuple] = []

    def query(self, *, token: str):
        return QueryResult(status=ExecutionStatus.SUCCESS)

    def run_command(self, cmd, timeout=None, *, token, parallel=False):
        self.calls.append(("run_command", cmd, timeout))
        return CommandResult(returncode=0, stdout="\n".join(self.grep_lines) + "\n",
                             stderr="", kind="command")

    def download_file(self, remote_path, local_path, timeout=None, *, token,
                      recursive=False):
        self.calls.append(("download_file", str(remote_path), timeout, recursive))
        if self.remote_root is None:
            return CommandResult(returncode=1, stdout="", stderr="missing",
                                 kind="path")
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


class TestSkillrefAllEqualsBody(unittest.TestCase):
    """skillref#103：`all` = 最深一档（body），层序要一致。"""

    def test_all_resolves_to_body_layers(self):
        pkg = SR.Package(_FakeMiddle())
        missing = str(Path(tempfile.gettempdir()) / "vb-no-such-doc-root")
        all_result = pkg.search(SR.SearchRequest(
            token=CALLER, source="local", doc_root=missing, query="x", search_in="all"))
        body_result = pkg.search(SR.SearchRequest(
            token=CALLER, source="local", doc_root=missing, query="x", search_in="body"))
        self.assertEqual("body", all_result.search_in)
        self.assertEqual(body_result.layers_run, all_result.layers_run)
        self.assertEqual(["name", "entry", "topic", "body"], all_result.layers_run)
        entry = pkg.search(SR.SearchRequest(
            token=CALLER, source="local", doc_root=missing, query="x", search_in="entry"))
        self.assertEqual(["name", "entry"], entry.layers_run,
                         "entry 档不得下探到 topic/body")


class TestSkillrefBodyRemoteBudget(unittest.TestCase):
    """skillref#140/#141：下载上限 = max_candidates；候选搜索默认 120 s。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="vb-skillref-remote-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.remote = SR_TB.build_doc_tree(self.tmp / "remote-doc")
        for index in range(6):
            (self.remote / "cpf_ref" / f"extra{index}.html").write_text(
                f"<html><body>ground bounce case {index}</body></html>", encoding="utf-8")
        self.lines = ["cpf_ref/reference.html"] + [
            f"cpf_ref/extra{index}.html" for index in range(6)]
        # remote 模式的查询代理账号来自 common.config 快照（spec：skillref.doc_token）
        patcher = unittest.mock.patch.object(
            SR, "_config_snapshot", return_value={"skillref": {"doc_token": DOC_TOKEN}})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _search(self, middle, **overrides):
        request = SR.SearchRequest(
            token=CALLER, source="remote",
            doc_root=str(self.remote), query="ground bounce", search_in="body",
            under=["cpf_ref"], limit=2, **overrides)
        return SR.Package(middle).search(request)

    def test_downloads_never_exceed_max_candidates(self):
        middle = _FakeMiddle(self.lines, self.remote)
        result = self._search(middle, max_candidates=3)
        downloads = [c for c in middle.calls
                     if c[0] == "download_file" and not c[3]]
        self.assertLessEqual(len(downloads), 3,
                             f"下载数必须 ≤ max_candidates：{len(downloads)}")
        self.assertTrue(result.ok, result.error)
        self.assertTrue(result.truncated, "候选数 ≥ max_candidates 时必须标 truncated")

    def test_body_search_default_timeout_is_120(self):
        middle = _FakeMiddle(self.lines, self.remote)
        self._search(middle)
        grep = [c for c in middle.calls if c[0] == "run_command"][0]
        self.assertEqual(120, grep[2], f"正文层远端候选搜索默认 120 s，实测 {grep[2]}")

    def test_body_search_timeout_can_be_overridden(self):
        middle = _FakeMiddle(self.lines, self.remote)
        self._search(middle, timeout=45)
        grep = [c for c in middle.calls if c[0] == "run_command"][0]
        self.assertEqual(45, grep[2], "调用方显式 timeout 必须覆盖默认 120 s")
        downloads = [c for c in middle.calls
                     if c[0] == "download_file" and not c[3]]
        self.assertTrue(downloads, "必须有候选下载")
        self.assertTrue(all(len(c) == 4 for c in downloads),
                        "每次下载都要显式传 timeout 关键字")


class TestSkillrefNoRemoteStat(unittest.TestCase):
    """skillref#062：远端路径只做 POSIX 拼接，禁止本地 stat。"""

    def test_remote_body_search_has_no_local_stat(self):
        source = (ROOT / "src" / "pyapi" / "packages" / "skillref.py").read_text(
            encoding="utf-8", errors="replace")
        tree = ast.parse(source)
        segments = [
            ast.get_source_segment(source, node)
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            for node in node.body
            if isinstance(node, ast.FunctionDef) and node.name == "_search_body_remote"
        ]
        self.assertEqual(1, len(segments), "找不到 _search_body_remote")
        body = segments[0]
        # `Path(relative).name` 只是本机字符串处理；禁止的是对远端路径做本地 stat。
        for banned in (".exists(", ".is_dir(", ".is_file(", "os.path.exists",
                       "os.path.isdir"):
            self.assertNotIn(banned, body,
                             f"远端正文搜索不得出现 {banned}（本地 stat 远端路径）")


class TestSchematicConnectivityIgnoresFilter(unittest.TestCase):
    """schematic#017：focus 含 connectivity 时 object_filter 必须被忽略。"""

    def _skill(self, focus, flt):
        return S._read_skill(S.ReadRequest(
            token=CALLER, library="L", cell="C", view="schematic",
            focus=focus, object_filter=flt))

    def test_filter_ignored_when_connectivity_requested(self):
        flt = {"instance": {"names": ["SENTINEL_INST"]}}
        skill = self._skill("connectivity", flt)
        self.assertNotIn("SENTINEL_INST", skill,
                         "focus=connectivity 时连接关系必须全量，object_filter 不得生效")

    def test_filter_applies_for_positions_focus(self):
        flt = {"instance": {"names": ["SENTINEL_INST"]}}
        skill = self._skill("positions", flt)
        self.assertIn("SENTINEL_INST", skill,
                      "非 connectivity 的 focus 下 object_filter 必须照常拼接")


class TestLayoutZoomNeverBboxless(unittest.TestCase):
    """layout#139：禁止不带 bbox 的 hiZoomIn/hiZoomOut（会卡死 SKILL 通道）。"""

    def setUp(self):
        self.pkg = L.Package(_FakeMiddle())

    def _expr(self, command):
        return self.pkg._display_expr(
            command, L.DisplayRequest(token=CALLER, library="L", cell="C", commands=[]))

    def test_fit_view_always_passes_bbox(self):
        expr = self._expr({"op": "fit_view"})
        self.assertIn("hiZoomIn(vbWin vbLayoutCv~>bBox)", expr)
        self.assertNotIn("hiZoomOut(", expr)

    def test_zoom_uses_absolute_scale_not_bboxless_hizoom(self):
        expr = self._expr({"op": "zoom", "scale": 2.5})
        self.assertIn("hiZoomAbsoluteScale", expr)
        self.assertNotIn("hiZoomIn(", expr)
        self.assertNotIn("hiZoomOut(", expr)

    def test_bad_scale_is_rejected(self):
        with self.assertRaises(ValueError):
            self._expr({"op": "zoom", "scale": 0})


class TestSkillrefMissingRootNoFallback(unittest.TestCase):
    """skillref#055：doc_root 不存在 → 业务失败且错误带该路径，不得退回/猜路径。"""

    def test_missing_doc_root_fails_with_path_and_no_fallback(self):
        middle = _FakeMiddle()
        missing = Path(tempfile.gettempdir()) / "vb-definitely-missing-docroot"
        result = SR.Package(middle).search(SR.SearchRequest(
            token=CALLER, source="local", doc_root=str(missing),
            query="ground bounce", search_in="body", under=["cpf_ref"]))
        self.assertFalse(result.ok)
        self.assertIn(str(missing), result.error or "",
                      "错误文案必须回带调用方给的 doc_root")
        self.assertEqual([], [c for c in middle.calls if c[0] != "query"],
                         "本地 doc_root 不可见时不得尝试远端/其它路径（无 fallback）")


class TestRequestIdNotIntroduced(unittest.TestCase):
    """总览#238：本版不引入 request_id —— 顶层把它按未知字段处理（4xx 拒绝）。

    真机实测（8127，`virtuoso.skillref.search`）：带 `request_id` 与带任意未知字段
    都返回 400 `unexpected keyword argument`。这里用同一个入口 `dispatch.build_request`
    离线钉住该口径（dataclass 请求模型路径）。

    ⚠ 已知不一致（第八轮观察）：pydantic 请求模型未统一 `extra="forbid"`，
    未知字段在那条路径上会被静默忽略；见 round8 报告的观察项。
    """

    def test_unknown_field_rejected_on_dataclass_request(self):
        from server import dispatch as dispatch_module
        from pyapi.packages.skillref import SearchRequest

        spec = dispatch_module.OperationSpec(
            package=object,
            method="search", request_model=SearchRequest)
        with self.assertRaises(dispatch_module.DispatchError) as ctx:
            dispatch_module.build_request(
                spec,
                {"operation": "skillref.search.probe", "token": "t-238",
                 "query": "x", "source": "local", "doc_root": "R:/x",
                 "request_id": "r-238"},
                "t-238")
        self.assertIn("unexpected keyword argument", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
