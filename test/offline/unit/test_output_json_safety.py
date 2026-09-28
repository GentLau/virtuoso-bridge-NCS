"""上层结果语义：缺样本的 trace 必须给 `null` / 省略，不许把 `math.nan` 塞进出参（P-049）。

**2026-09-24 口径更正**（设计侧澄清）：
* 测试专用的 `src/server/stress_server.py` 已从生产源码删除 → 相关内容不再属于 P-049；
* 业务面 `server/api_server.py::_send` 已用 `dumps_strict` + 500 兜底（本文件保留一条**负控制**证明它有效）；
* daemon 响应当前只含字符串，裸 `json.dumps` 属于**防御性加固（可选，不立案）**；
* **真正剩下的是上层**：`pyapi/packages/_spectre_util.py` 在某个 trace 缺该扫描点数值时写入
  `signal_state.get(name, math.nan)`，而 `psf_external()` 会原样放行 float → NaN 进入 API 出参，
  严格客户端（`loads_strict`）整包拒收。按上层结果语义应改成 `null`（或省略该点）。

本文件用真实 PSF 文本走到那条分支：第 2 个扫描点只给 `vout`、不给 `iout`。
修复前：`data["iout"][1]` 是 NaN、`dumps_strict(data)` 抛错 → 两条断言红；
修复后：值是 `None`、严格序列化通过 → 自动转绿。
"""
from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from common.jsonutil import dumps_strict
from pyapi.packages import _spectre_util as util

#: 第 1 个扫描点只有 `vout`：`iout`（复数）与 `vcm`（实数）**从未出现过**
#: → 触发 `signal_state.get(name, math.nan)`；两种形状的出参都要给 null。
#: 第 2 个扫描点给全 → 顺带钉住"沿用上一次值"的正常语义（不是缺失）。
MISSING_TRACE_PSF = "\n".join([
    "HEADER",
    '"PSFversion" "1.00"',
    "SWEEP",
    '"time"',
    "TRACE",
    '"1" GROUP 1',
    '"vout" "V"',
    '"2" GROUP 2',
    '"iout" "A"',
    '"3" GROUP 3',
    '"vcm" "V"',
    "VALUE",
    '"time" 0.0',
    '"1" (1.0 0.5)',
    '"time" 1e-9',
    '"1" (1.1 0.4)',
    '"2" (0.0 -1.0)',
    '"3" 0.9',
    "END",
])


def _no_nan(value) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, complex):
        return math.isfinite(value.real) and math.isfinite(value.imag)
    if isinstance(value, dict):
        return all(_no_nan(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return all(_no_nan(item) for item in value)
    return True


class TestMissingTraceIsNull(unittest.TestCase):
    def _parse(self) -> dict:
        with tempfile.TemporaryDirectory(prefix="vb-psf-") as tmp:
            path = Path(tmp) / "sweep.psf"
            path.write_text(MISSING_TRACE_PSF, encoding="utf-8")
            _header, data = util.parse_psf_file(path)
        return data

    def test_missing_sample_is_null_not_nan(self):
        data = self._parse()
        # 实数 trace：缺失点是列表里的一个元素
        self.assertIn("vcm", data, f"traces: {list(data)}")
        vcm = data["vcm"]
        self.assertEqual(len(vcm), 2, f"vcm series: {vcm!r}")
        self.assertIsNone(vcm[0], f"首个扫描点缺该 trace 时必须给 null: {vcm!r}")
        self.assertEqual(vcm[1], 0.9, f"第 2 点应沿用值（正常 carry-forward）: {vcm!r}")
        # 复数 trace：出参是 {"re": [...], "im": [...]}，缺失点也要是 null
        self.assertIn("iout", data, f"traces: {list(data)}")
        iout = data["iout"]
        self.assertIsInstance(iout, dict, f"复数 trace 形状: {iout!r}")
        self.assertEqual(len(iout["re"]), 2, f"iout.re: {iout!r}")
        self.assertIsNone(iout["re"][0], f"复数首个扫描点缺该 trace 时必须给 null: {iout!r}")
        self.assertEqual(iout["re"][1], 0.0, f"第 2 点实部: {iout!r}")

    def test_whole_result_is_strictly_serialisable(self):
        data = self._parse()
        self.assertTrue(_no_nan(data), f"出参里仍有非有限值: {data!r}")
        dumps_strict(data)          # 出现 NaN/Infinity 会抛 ValueError


class TestApiServerResponseGuard(unittest.TestCase):
    """负控制：业务面**已经**守住（不可序列化出参 → 500 + 严格 JSON 错误体）。"""

    def test_api_server_falls_back_to_strict_error_body(self):
        import io

        from server import api_server

        handler = object.__new__(api_server.ApiHandler)
        sent: dict = {}
        handler.send_response = lambda status: sent.update(status=status)
        handler.send_header = lambda key, value: None
        handler.end_headers = lambda: None
        handler.wfile = io.BytesIO()
        handler.close_connection = False
        handler._send(200, {"ok": True, "data": {"missing_trace": float("nan")}})
        body = handler.wfile.getvalue().decode("utf-8")
        payload = json.loads(body, parse_constant=lambda name: (_ for _ in ()).throw(
            ValueError(f"non-finite JSON constant: {name}")))
        self.assertEqual(sent.get("status"), 500)
        self.assertFalse(payload["ok"])
        self.assertIn("invalid response payload", payload["error"])


if __name__ == "__main__":
    unittest.main()
