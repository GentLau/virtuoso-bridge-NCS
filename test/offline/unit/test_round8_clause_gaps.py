"""第八轮条款缺口补测（离线可测的 partial 项）。

覆盖 `round8-gap-actions.md` 里三条不需要真机的缺口：

* **schematic#017**：`focus` 含 `connectivity` 时必须忽略 `object_filter`
  （连接关系要全量）—— 断言生成的 SKILL 文本把过滤器收敛为 `t`；
* **layout#139**：禁止不带 bbox 的 `hiZoomIn`/`hiZoomOut`（会进交互橡皮筋并
  卡死 SKILL 通道）—— 断言 fit_view 用带 bbox 的 `hiZoomIn`、zoom 走
  `hiZoomAbsoluteScale`，且生成文本不存在裸 `hiZoomIn(` / `hiZoomOut(`；
* **总览#238**：本版不引入 `request_id` 字段 —— 真实（dataclass）请求模型下
  带 `request_id` 的 operation 必须 400 拒绝，且业务方法不被调用。
"""
from __future__ import annotations

import dataclasses
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from pyapi.packages import layout as layout_pkg  # noqa: E402
from pyapi.packages import schematic as sch  # noqa: E402
from server import dispatch as dispatch_module  # noqa: E402
from server.dispatch import dispatch  # noqa: E402


class TestSchematicConnectivityIgnoresFilter(unittest.TestCase):
    def _skill(self, focus: str) -> str:
        request = sch.ReadRequest(
            token="t", library="L", cell="C", view="schematic", focus=focus,
            object_filter={"instance": {"names": ["I1"]},
                           "wire": {"region": [0, 0, 10, 10]}},
        )
        return sch._read_skill(request)

    def test_connectivity_drops_filters(self):
        text = self._skill("connectivity")
        self.assertIn("&& t)", text,
                      "focus=connectivity 时实例过滤器必须收敛为 t")
        self.assertNotIn("I1", text, "connectivity 模式不得保留 instance 名字过滤")

    def test_positions_keeps_filters(self):
        text = self._skill("positions")
        self.assertIn('"I1"', text,
                      "focus=positions 时 object_filter 必须继续生效（对照）")


class TestLayoutNoBareZoom(unittest.TestCase):
    def _expr(self, command: dict) -> str:
        request = layout_pkg.DisplayRequest(
            token="t", library="L", cell="C", commands=[command])
        return layout_pkg.Package(None)._display_expr(command, request)

    def test_fit_view_zooms_with_bbox(self):
        text = self._expr({"op": "fit_view"})
        self.assertIn("hiZoomIn(vbWin vbLayoutCv~>bBox)", text)

    def test_zoom_uses_absolute_scale_not_bare_zoom_in(self):
        text = self._expr({"op": "zoom", "scale": 2.0})
        self.assertIn("hiZoomAbsoluteScale(vbWin 2)", text)
        self.assertNotIn("hiZoomOut(", text)
        self.assertNotIn("hiZoomIn(vbWin)", text, "禁止不带 bbox 的 hiZoomIn")


@dataclasses.dataclass(frozen=True)
class _DataclassRequest:
    token: str
    value: int = 0


class _DataclassPackage:
    def __init__(self, middle):
        self.middle = middle
        self.called = False

    def echo(self, request):
        self.called = True
        return {"ok": True, "value": request.value}


class TestRequestIdIsRejected(unittest.TestCase):
    def test_request_id_is_unknown_field(self):
        built: list = []

        def factory(middle):
            built.append(_DataclassPackage(middle))
            return built[-1]

        dispatch_module.register_operation(
            "tb.dc_echo", factory, "echo", _DataclassRequest, replace=True)
        status, body = dispatch(None, {
            "operation": "tb.dc_echo", "token": "t", "value": 1,
            "request_id": "r-1"})
        self.assertEqual(status, 400, body)
        self.assertFalse(body["ok"])
        self.assertIn("invalid request", body["error"])
        self.assertEqual(built, [], "未知字段被拒后业务包不得被构造/调用")


if __name__ == "__main__":
    unittest.main()
