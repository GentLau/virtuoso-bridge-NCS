"""L0 contracts for ``pyapi.packages._spectre_util``.

这一层是 spectre 结果解析与指标计算的**纯函数**：真机 TB 只在"整条链路跑通"
的意义上碰它，这里把 PSF 解析、九类指标、以及各条错误分支逐一钉死。

TRAN_PSF 的格式取自 S11 真机产物
（``test/artifacts/env/log-vblog/artifact/spectre/inv2_pre/inv2_pre.raw/tran1.tran.tran``），
只把数值裁剪成 3 个点，避免自造格式。
"""
from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

from pyapi.packages import _spectre_util as U


#: 真实 PSF ASCII（tran）裁剪样本：time 0/1n/2n，vout 0/1/2
TRAN_PSF = """HEADER
"PSFversion" "1.00"
"simulator" "spectre"
"analysis type" "tran"
"analysis name" "tran1"
"xVecSorted" "ascending"
TYPE
"sweep" FLOAT DOUBLE PROP(
"key" "sweep"
)
"V" FLOAT DOUBLE PROP(
"units" "V"
"key" "node"
)
SWEEP
"time" "sweep" PROP(
"sweep_direction" 0
"units" "s"
"plot" 0
"grid" 1
)
TRACE
"vout" "V"
VALUE
"time" 0.000000000000000e+00
"vout" 0.000000000000000e+00
"time" 1.000000000000000e-09
"vout" 1.000000000000000e+00
"time" 2.000000000000000e-09
"vout" 2.000000000000000e+00
END
"""


def metric(data, **spec):
    return U.compute_metric(data, spec)


class TestPsfExternal(unittest.TestCase):
    def test_complex_becomes_re_im(self):
        self.assertEqual(U.psf_external(complex(1, -2)), {"re": 1.0, "im": -2.0})

    def test_complex_vector_becomes_re_im_vectors(self):
        value = U.psf_external([complex(1, 0), complex(0, 2)])
        self.assertEqual(value, {"re": [1.0, 0.0], "im": [0.0, 2.0]})

    def test_plain_values_pass_through(self):
        self.assertEqual(U.psf_external([1, 2.0, "x"]), [1, 2.0, "x"])
        self.assertIsNone(U.psf_external(None))
        self.assertTrue(U.psf_external(True))
        self.assertEqual(U.psf_external({"a": complex(0, 1)}), {"a": {"re": 0.0, "im": 1.0}})

    def test_unknown_object_is_stringified(self):
        class Weird:
            def __str__(self) -> str:
                return "weird"

        self.assertEqual(U.psf_external(Weird()), "weird")


class TestParsePsfFile(unittest.TestCase):
    def _write(self, tmp: str, name: str = "tran1.tran.tran") -> Path:
        path = Path(tmp) / name
        path.write_text(TRAN_PSF, encoding="utf-8")
        return path

    def test_header_and_vectors(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            header, data = U.parse_psf_file(self._write(tmp))
        self.assertEqual(header["analysis type"], "tran")
        self.assertEqual(header["PSFversion"], "1.00")
        self.assertEqual(data["time"], [0.0, 1e-9, 2e-9])
        self.assertEqual(data["vout"], [0.0, 1.0, 2.0])

    def test_directory_helpers_and_detection(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            raw = Path(tmp) / "inv.raw"
            raw.mkdir()
            self._write(str(raw))
            self.assertTrue(U._has_psf_files(raw))
            self.assertFalse(U._has_psf_files(Path(tmp)))   # 只看本层文件
            listed = U.list_result_files(raw)
            self.assertTrue(any("tran1.tran.tran" in item for item in listed), listed)
            parsed = U.parse_psf_directory(raw)
            self.assertEqual(sorted(parsed), ["analyses", "data", "files"])
            self.assertEqual(parsed["data"]["vout"], [0.0, 1.0, 2.0])
            self.assertEqual(parsed["data"]["time"], [0.0, 1e-9, 2e-9])
            self.assertEqual(parsed["analyses"], ["tran"])
            self.assertEqual(parsed["files"], ["tran1.tran.tran"])
            self.assertIn(U.detect_layout(Path(tmp)), ("single", "raw", "sweep"))
            self.assertEqual(U.detect_layout(Path(tmp) / "inv.raw" / "tran1.tran.tran"),
                             "single")


class TestVectorHelpers(unittest.TestCase):
    DATA = {"time": [0.0, 1.0, 2.0], "vout": [0.0, 1.0, 2.0],
            "freq": [1.0, 10.0, 100.0],
            "ac": [complex(1, 0), complex(0, -1), complex(0.5, 0)]}

    def test_real_and_complex_vectors(self):
        self.assertEqual(U._real_vector(self.DATA, "vout"), [0.0, 1.0, 2.0])
        # 复数向量有两条通道：{"re","im"} 或（实数）列表；**不接受** Python complex 对象
        re_im = {"ac": {"re": [1.0, 0.0], "im": [0.0, -1.0]}}
        self.assertEqual(U._complex_vector(re_im, "ac"), [complex(1, 0), complex(0, -1)])
        self.assertEqual(U._complex_vector({"ac": [1.0, 2.0]}, "ac"),
                         [complex(1, 0), complex(2, 0)])
        with self.assertRaises(ValueError):
            U._real_vector(self.DATA, "missing")
        with self.assertRaises(ValueError):
            U._complex_vector(self.DATA, "missing")
        with self.assertRaises(ValueError):
            U._complex_vector({"ac": [complex(1, 0)]}, "ac")

    def test_indices_in_range(self):
        self.assertEqual(U._indices_in_range([0.0, 1.0, 2.0], None, None), [0, 1, 2])
        self.assertEqual(U._indices_in_range([0.0, 1.0, 2.0], 0.5, 1.5), [1])
        self.assertEqual(U._indices_in_range([0.0, 1.0, 2.0], 2.0, None), [2])


class TestStatisticsAndCrossings(unittest.TestCase):
    DATA = {"time": [0.0, 1.0, 2.0, 3.0], "vout": [0.0, 1.0, 2.0, 3.0]}

    def test_statistics_and_window(self):
        self.assertEqual(metric(self.DATA, type="min", signal="vout")["value"], 0.0)
        self.assertEqual(metric(self.DATA, type="max", signal="vout")["value"], 3.0)
        self.assertEqual(metric(self.DATA, type="mean", signal="vout")["value"], 1.5)
        self.assertAlmostEqual(metric(self.DATA, type="rms", signal="vout")["value"],
                               math.sqrt(14 / 4))
        windowed = metric(self.DATA, type="max", signal="vout", start=1.0, stop=2.0)
        self.assertEqual(windowed["value"], 2.0)

    def test_statistic_error_paths(self):
        bad = metric(self.DATA, type="min", signal="missing")
        self.assertFalse(bad["ok"])
        self.assertEqual(bad["type"], "min")
        empty = metric(self.DATA, type="max", signal="vout", start=10, stop=20)
        self.assertFalse(empty["ok"])
        self.assertIn("empty", empty["detail"])

    def test_threshold_crossing(self):
        rise = metric(self.DATA, type="threshold_crossing", signal="vout", threshold=1.5)
        self.assertTrue(rise["ok"], rise)
        self.assertAlmostEqual(rise["value"], 1.5)
        self.assertEqual(rise["unit"], "s")
        falling = {"time": [0.0, 1.0, 2.0, 3.0], "vout": [3.0, 2.0, 1.0, 0.0]}
        fall = metric(falling, type="threshold_crossing", signal="vout",
                      threshold=1.5, direction="fall")
        self.assertTrue(fall["ok"], fall)
        self.assertAlmostEqual(fall["value"], 1.5)
        # 单调上升信号里没有下降穿越 → 结构化错误
        missing = metric(self.DATA, type="threshold_crossing", signal="vout",
                         threshold=1.5, direction="fall")
        self.assertFalse(missing["ok"])
        self.assertIn("not found", missing["detail"])
        second = metric(self.DATA, type="threshold_crossing", signal="vout",
                        threshold=0.5, edge=2)
        self.assertFalse(second["ok"])          # 只有一次穿越

    def test_delay(self):
        data = {"time": [0.0, 1.0, 2.0, 3.0],
                "a": [0.0, 0.0, 2.0, 2.0], "b": [0.0, 2.0, 2.0, 2.0]}
        value = metric(data, type="delay", from_signal="a", to_signal="b", threshold=1.0)
        self.assertTrue(value["ok"], value)
        self.assertAlmostEqual(value["value"], -1.0)


class TestAcMetrics(unittest.TestCase):
    #: AC 数据用 psf_external 的复数形态（{"re","im"}），与真机解析输出一致
    DATA = {"freq": [1.0, 10.0, 100.0],
            "out": {"re": [1.0, 0.5, 0.01], "im": [0.0, 0.0, 0.0]}}

    def test_ac_magnitude_linear_and_db(self):
        linear = metric(self.DATA, type="ac_magnitude", signal="out", frequency=10.0)
        self.assertTrue(linear["ok"], linear)
        self.assertAlmostEqual(linear["value"], 0.5)
        self.assertIsNone(linear["unit"])
        db = metric(self.DATA, type="ac_magnitude", signal="out", frequency=10.0, scale="db")
        self.assertTrue(db["ok"], db)
        self.assertAlmostEqual(db["value"], 20 * math.log10(0.5), places=6)
        self.assertEqual(db["unit"], "dB")

    def test_ac_magnitude_error_paths(self):
        zero = {"freq": [1.0], "out": {"re": [0.0], "im": [0.0]}}
        bad_db = metric(zero, type="ac_magnitude", signal="out", frequency=1.0, scale="db")
        self.assertFalse(bad_db["ok"])
        self.assertIn("positive", bad_db["detail"])
        bad_scale = metric(self.DATA, type="ac_magnitude", signal="out",
                           frequency=1.0, scale="log")
        self.assertFalse(bad_scale["ok"])
        self.assertIn("scale", bad_scale["detail"])
        no_freq = metric(self.DATA, type="ac_magnitude", signal="out")
        self.assertFalse(no_freq["ok"])

    def test_bandwidth_dc_and_max(self):
        data = {"freq": [1.0, 10.0, 100.0],
                "out": {"re": [1.0, 1 / math.sqrt(2), 0.01], "im": [0.0, 0.0, 0.0]}}
        dc = metric(data, type="bandwidth", signal="out")
        self.assertTrue(dc["ok"], dc)
        self.assertAlmostEqual(dc["value"], 10.0, places=6)
        self.assertEqual(dc["unit"], "Hz")
        peak = metric(data, type="bandwidth", signal="out", reference="max")
        self.assertTrue(peak["ok"], peak)

    def test_bandwidth_error_paths(self):
        one_point = metric({"freq": [1.0], "out": {"re": [1.0], "im": [0.0]}},
                           type="bandwidth", signal="out")
        self.assertFalse(one_point["ok"])
        self.assertIn("two points", one_point["detail"])
        bad_ref = metric(self.DATA, type="bandwidth", signal="out", reference="rms")
        self.assertFalse(bad_ref["ok"])
        self.assertIn("reference", bad_ref["detail"])
        silent = {"freq": [1.0, 2.0], "out": {"re": [0.0, 0.0], "im": [0.0, 0.0]}}
        zero_ref = metric(silent, type="bandwidth", signal="out")
        self.assertFalse(zero_ref["ok"])
        self.assertIn("not positive", zero_ref["detail"])

    def test_noise_integral(self):
        data = {"freq": [0.0, 1.0, 2.0],
                "onoise": {"re": [0.0, 1.0, 1.0], "im": [0.0, 0.0, 0.0]}}
        value = metric(data, type="noise_integral", signal="onoise")
        self.assertTrue(value["ok"], value)
        self.assertAlmostEqual(value["value"], 1.5)
        self.assertEqual(value["unit"], "V^2")
        empty = metric(data, type="noise_integral", signal="onoise", start=10, stop=20)
        self.assertFalse(empty["ok"])
        self.assertIn("empty", (empty.get("detail") or ""))

    def test_noise_integral_empty_window_should_fail(self):
        data = {"freq": [0.0, 1.0, 2.0],
                "onoise": {"re": [0.0, 1.0, 1.0], "im": [0.0, 0.0, 0.0]}}
        empty = metric(data, type="noise_integral", signal="onoise", start=10, stop=20)
        self.assertFalse(empty["ok"])


class TestMetricDispatch(unittest.TestCase):
    def test_unsupported_metric_is_an_error_dict(self):
        result = metric({}, type="banana", signal="x")
        self.assertFalse(result["ok"])
        self.assertIn("unsupported metric", result["detail"])
        self.assertEqual(result["type"], "banana")

    def test_missing_type_is_reported(self):
        result = metric({}, signal="x")
        self.assertFalse(result["ok"])
        self.assertIn("unsupported metric", result["detail"])

    def test_metric_error_shape(self):
        result = U._metric_error("min", ValueError("boom"))
        self.assertEqual(result, {"type": "min", "ok": False, "value": None,
                                  "unit": None, "detail": "ValueError: boom"})


#: swept PSF：SWEEP 段给扫描变量，VALUE 段按 step 分组
SWEPT_PSF = """HEADER
"PSFversion" "1.00"
"simulator" "spectre"
"analysis type" "dc"
"analysis name" "dc1"
TYPE
"sweep" FLOAT DOUBLE PROP(
"key" "sweep"
)
"V" FLOAT DOUBLE PROP(
"units" "V"
"key" "node"
)
SWEEP
"vdd" "sweep" PROP(
"sweep_direction" 0
"units" "V"
)
TRACE
"vout" "V"
VALUE
"vdd" 0.8
"vout" 0.4
"vdd" 1.2
"vout" 0.6
END
"""


class TestSweepLayouts(unittest.TestCase):
    """扫描结果的两种真实布局：classic `<raw>/sw*.sweep*/N/` 与 X/LX flat 文件。"""

    def _classic(self, tmp: Path) -> Path:
        raw = tmp / "job.raw"
        for index, vout in ((1, "0.4"), (2, "0.6")):
            point = raw / "sw1.sweep1" / str(index)
            point.mkdir(parents=True)
            (point / "tran1.tran.tran").write_text(TRAN_PSF, encoding="utf-8")
        return raw

    def _flat(self, tmp: Path) -> Path:
        raw = tmp / "job.raw"
        raw.mkdir(parents=True)
        (raw / "sw0-0_dcOp.dc").write_text(SWEPT_PSF, encoding="utf-8")
        (raw / "sw0-1_dcOp.dc").write_text(SWEPT_PSF, encoding="utf-8")
        return raw

    def test_classic_layout(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            parsed = U.parse_sweep_directory(self._classic(Path(tmp)))
        self.assertEqual(parsed["layout"], "classic")
        self.assertEqual(parsed["point_count"], 2)
        self.assertEqual(sorted(parsed["points"]), [1, 2])
        self.assertEqual(parsed["points"][1]["vout"], [0.0, 1.0, 2.0])
        self.assertEqual(parsed["signals"], ["time", "vout"])

    def test_flat_layout_numbers_points_from_one(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            parsed = U.parse_sweep_directory(self._flat(Path(tmp)))
        self.assertEqual(parsed["layout"], "flat")
        self.assertEqual(sorted(parsed["points"]), [1, 2])
        self.assertEqual(parsed["points"][1]["vout"], [0.4, 0.6])
        self.assertEqual(parsed["point_count"], 2)

    def test_unrecognized_layout_raises(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            empty = Path(tmp) / "empty.raw"
            empty.mkdir()
            with self.assertRaises(ValueError) as ctx:
                U.parse_sweep_directory(empty)
        self.assertIn("no sweep layout recognized", str(ctx.exception))

    def test_non_numeric_point_directories_are_skipped(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            raw = Path(tmp) / "job.raw"
            sweep = raw / "sw1.sweep1"
            (sweep / "notes").mkdir(parents=True)
            (sweep / "notes" / "readme.txt").write_text("x", encoding="utf-8")
            (sweep / "7").mkdir()
            (sweep / "7" / "tran1.tran.tran").write_text(TRAN_PSF, encoding="utf-8")
            parsed = U.parse_sweep_directory(raw)
        self.assertEqual(sorted(parsed["points"]), [7])
        self.assertEqual(parsed["layout"], "classic")

    def test_swept_psf_keeps_per_step_values(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            path = Path(tmp) / "dc.dc"
            path.write_text(SWEPT_PSF, encoding="utf-8")
            header, data = U.parse_psf_file(path)
        self.assertEqual(header["analysis type"], "dc")
        # 第一步建向量，第二步的 vout 追加进去（delta 压缩语义见 spec §9）
        self.assertEqual(data["vout"], [0.4, 0.6])
        self.assertEqual(data["vdd"], [0.8, 1.2])

    def test_sweep_section_removed_falls_over_to_non_swept_and_can_be_empty(self):
        text = SWEPT_PSF.replace('"vdd" "sweep" PROP(\n"sweep_direction" 0\n"units" "V"\n)\n', "")
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            path = Path(tmp) / "dc.dc"
            path.write_text(text, encoding="utf-8")
            # 没有 SWEEP 段时走 non-swept 解析；若最终没解出任何数据，parse_psf_file 会**抛错**
            # 而不是静默返回空 dict（这是刻意的：空结果与"解析失败"必须可区分）。
            with self.assertRaises(ValueError) as ctx:
                U.parse_psf_file(path)
        self.assertIn("no PSF data parsed", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
