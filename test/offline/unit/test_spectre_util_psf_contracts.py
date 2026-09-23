"""Edge-path contracts for the PSF half of ``pyapi.packages._spectre_util``.

``test_spectre_util_contracts.py`` covers the metric calculators and the happy
path of ``parse_psf_file``.  This file targets the parser branches that file
never reaches - they are exactly the branches a real Spectre run hits when a
result is unusual rather than wrong:

* header forms (text before ``HEADER``, unquoted values),
* ``TRACE`` GROUP mapping and bare trace names,
* swept VALUE entries (complex pairs, malformed numbers, non-matching lines),
* non-swept VALUE forms (typed / plain number / legacy / STRUCT instance),
* ``_scalar`` and ``parse_psf_file`` rejection paths,
* the raw-directory discovery helpers (scan root, merge, layout detection).
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pyapi.packages import _spectre_util as util


HEADER_ONLY = "\n".join([
    "noise before the marker",
    "HEADER",
    '"PSFversion" "1.00"',
    '"date" 2026-09-23',
    '"note" "two words"',
    "TYPE",
    '"x" FLOAT',
])

SWEPT_PSF = "\n".join([
    "HEADER",
    '"PSFversion" "1.00"',
    "SWEEP",
    '"time"',
    "TRACE",
    '"1" GROUP 1',
    '"vout" "V"',
    '"2" GROUP 2',
    '"iout" "A"',
    '"bare_net"',
    "VALUE",
    '"time" 0.0',
    '"1" (1.0 0.5)',
    '"2" (0.0 -1.0)',
    '"1" (1.0e 0.5)',
    "### not a frame line",
    '"junk" notanumber',
    '"time" 1e-9',
    '"1" (1.1 0.4)',
    "END",
])

NON_SWEPT_PSF = "\n".join([
    "HEADER",
    '"PSFversion" "1.00"',
    "TYPE",
    '"mytype" STRUCT(',
    '"a" FLOAT',
    '"b" FLOAT',
    ")",
    "TRACE",
    '"vout" "V"',
    "VALUE",
    '"vout" "V" 1.25',
    '"ibias" 3.5e-6',
    '"label" "text"',
    '"inst1" "mytype" (',
    "1.0",
    "2.0",
    ")",
    '"legacy" foo',
    "END",
])


class TestParseHeader(unittest.TestCase):
    def test_ignores_text_before_the_marker(self):
        header = util._parse_header(HEADER_ONLY)
        self.assertEqual(header["PSFversion"], "1.00")

    def test_unquoted_value_is_kept(self):
        # "_date" has no quotes around the value: second MATCH form.
        self.assertEqual(util._parse_header(HEADER_ONLY)["date"], "2026-09-23")

    def test_section_marker_stops_the_header(self):
        self.assertNotIn("x", util._parse_header(HEADER_ONLY))

    def test_empty_content_gives_empty_header(self):
        self.assertEqual(util._parse_header("only noise\n"), {})


class TestSectionHelpers(unittest.TestCase):
    def test_sweep_variable_blank_line_stops_scan(self):
        lines = ["SWEEP", "", '"time"', "TRACE", '"v" "V"', "VALUE", "END"]
        sections = util._section_lines(lines)
        self.assertEqual(util._sweep_variable(lines, sections, len(lines)), "")

    def test_sweep_variable_reads_first_quoted_name(self):
        lines = ["SWEEP", '"time"', "TRACE", "VALUE", "END"]
        sections = util._section_lines(lines)
        self.assertEqual(util._sweep_variable(lines, sections, len(lines)), "time")

    def test_trace_mapping_group_and_bare_names(self):
        lines = SWEPT_PSF.splitlines()
        sections = util._section_lines(lines)
        names, group_to_name = util._trace_mapping(lines, sections, len(lines))
        self.assertEqual(names, ["vout", "iout", "bare_net"])
        self.assertEqual(group_to_name, {"1": "vout", "2": "iout"})

    def test_trace_mapping_value_marker_stops_scan(self):
        lines = ["TRACE", '"a" "V"', "VALUE", '"b" "V"', "END"]
        sections = util._section_lines(lines)
        names, _ = util._trace_mapping(lines, sections, len(lines))
        self.assertEqual(names, ["a"])


class TestScalar(unittest.TestCase):
    def test_quoted_number_stays_a_string(self):
        self.assertEqual(util._scalar('"12.5"'), "12.5")

    def test_plain_number_becomes_float(self):
        self.assertEqual(util._scalar(" 1e-3 "), 1e-3)

    def test_non_numeric_text_passes_through(self):
        self.assertEqual(util._scalar("foo"), "foo")

    def test_empty_quoted_string_is_unwrapped_not_kept(self):
        # len()==2 is the boundary of the quote check: an empty quoted value must
        # still lose its quotes rather than fall through to the float() attempt.
        self.assertEqual(util._scalar('""'), "")
        self.assertEqual(util._scalar('"a"'), "a")


class TestStructTypes(unittest.TestCase):
    def test_members_are_collected_until_depth_closes(self):
        lines = NON_SWEPT_PSF.splitlines()
        structs = util._parse_struct_types(lines, 0, len(lines))
        self.assertEqual(structs, {"mytype": ["a", "b"]})

    def test_unknown_section_yields_no_structs(self):
        self.assertEqual(util._parse_struct_types(["VALUE", "END"], 0, 2), {})


class TestNonSweptParsing(unittest.TestCase):
    def test_typed_plain_and_legacy_value_forms(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            path = Path(tmp) / "dc.dc"
            path.write_text(NON_SWEPT_PSF, encoding="utf-8")
            _, data = util.parse_psf_file(path)
        self.assertEqual(data["vout"], 1.25)
        self.assertAlmostEqual(data["ibias"], 3.5e-6)
        self.assertEqual(data["label"], "text")
        self.assertEqual(data["legacy"], "foo")

    def test_struct_instance_expands_into_prefixed_fields(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            path = Path(tmp) / "dc.dc"
            path.write_text(NON_SWEPT_PSF, encoding="utf-8")
            _, data = util.parse_psf_file(path)
        self.assertEqual(data["inst1:a"], 1.0)
        self.assertEqual(data["inst1:b"], 2.0)

    def test_blank_line_stops_the_value_scan(self):
        text = "\n".join([
            "HEADER", '"PSFversion" "1.00"', "VALUE",
            '"a" 1.0', "", '"b" 2.0', "END",
        ])
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            path = Path(tmp) / "dc.dc"
            path.write_text(text, encoding="utf-8")
            _, data = util.parse_psf_file(path)
        self.assertEqual(data, {"a": 1.0})


class TestSweptParsing(unittest.TestCase):
    def test_group_mapping_and_complex_pairs(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            path = Path(tmp) / "tran1.tran.tran"
            path.write_text(SWEPT_PSF, encoding="utf-8")
            _, data = util.parse_psf_file(path)
        self.assertEqual(data["time"], [0.0, 1e-9])
        self.assertEqual(data["vout"], {"re": [1.0, 1.1], "im": [0.5, 0.4]})
        # Sample-and-hold: a trace that is not re-stated in the newest point
        # keeps its previous value, so iout repeats its first sample.
        self.assertEqual(data["iout"], {"re": [0.0, 0.0], "im": [-1.0, -1.0]})

    def test_unmapped_trace_is_filled_with_nan(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            path = Path(tmp) / "tran1.tran.tran"
            path.write_text(SWEPT_PSF, encoding="utf-8")
            _, data = util.parse_psf_file(path)
        self.assertEqual(len(data["bare_net"]), 2)
        self.assertTrue(all(value != value for value in data["bare_net"]))  # NaN

    def test_malformed_and_foreign_lines_are_skipped(self):
        # "1" (1.0e 0.5) -> complex regex matches, float() fails;
        # "### ..."     -> matches neither form;
        # "junk" ...    -> scalar form matches, float() fails.
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            path = Path(tmp) / "tran1.tran.tran"
            path.write_text(SWEPT_PSF, encoding="utf-8")
            _, data = util.parse_psf_file(path)
        self.assertNotIn("junk", data)
        self.assertNotIn("###", data)

    def test_blank_line_stops_the_value_scan(self):
        text = "\n".join([
            "HEADER", '"PSFversion" "1.00"', "SWEEP", '"time"', "TRACE",
            '"v" "V"', "VALUE", '"time" 0.0', '"v" 1.0', "", '"time" 1.0', "END",
        ])
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            path = Path(tmp) / "tran1.tran.tran"
            path.write_text(text, encoding="utf-8")
            _, data = util.parse_psf_file(path)
        self.assertEqual(data["time"], [0.0])

    def test_swept_parser_without_value_section_returns_empty(self):
        lines = SWEPT_PSF.splitlines()
        sections = util._section_lines(lines)
        sections.pop("VALUE")
        self.assertEqual(util._parse_swept_data(lines, sections, len(lines)), {})

    def test_swept_parser_without_sweep_variable_returns_empty(self):
        lines = ["SWEEP", "", "TRACE", '"v" "V"', "VALUE", '"time" 0.0', "END"]
        sections = util._section_lines(lines)
        self.assertEqual(util._parse_swept_data(lines, sections, len(lines)), {})


class TestParsePsfFileRejections(unittest.TestCase):
    def test_missing_file(self):
        missing = Path(tempfile.gettempdir()) / "vb-does-not-exist.psf"
        with self.assertRaises(FileNotFoundError):
            util.parse_psf_file(missing)

    def test_empty_file(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            path = Path(tmp) / "empty.dc"
            path.write_text("   \n", encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                util.parse_psf_file(path)
        self.assertIn("empty", str(ctx.exception))

    def test_no_value_section(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            path = Path(tmp) / "novalue.dc"
            path.write_text("HEADER\n\"PSFversion\" \"1.00\"\nEND\n", encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                util.parse_psf_file(path)
        self.assertIn("VALUE", str(ctx.exception))

    def test_value_section_without_parsable_data(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            path = Path(tmp) / "nodata.dc"
            path.write_text("HEADER\nVALUE\nEND\n", encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                util.parse_psf_file(path)
        self.assertIn("no PSF data", str(ctx.exception))


class TestDirectoryHelpers(unittest.TestCase):
    def _write(self, path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_scan_root_missing_directory_returns_itself(self):
        missing = Path(tempfile.gettempdir()) / "vb-no-such-raw"
        self.assertEqual(util._psf_scan_root(missing), missing)

    def test_scan_root_descends_into_same_named_inner_dir(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            raw = Path(tmp) / "run.raw"
            self._write(raw / "run.raw" / "dc.dc", NON_SWEPT_PSF)
            self.assertEqual(util._psf_scan_root(raw), raw / "run.raw")

    def test_scan_root_descends_into_psf_child(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            raw = Path(tmp) / "run.raw"
            self._write(raw / "psf" / "dc.dc", NON_SWEPT_PSF)
            self.assertEqual(util._psf_scan_root(raw), raw / "psf")

    def test_scan_root_skips_empty_psf_child(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            raw = Path(tmp) / "run.raw"
            (raw / "psf").mkdir(parents=True, exist_ok=True)   # no PSF files inside
            self.assertEqual(util._psf_scan_root(raw), raw)

    def test_scan_root_skips_sweep_bookkeeping_dirs(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            raw = Path(tmp) / "run.raw"
            self._write(raw / "sw1.sweep1" / "dc.dc", NON_SWEPT_PSF)
            self.assertEqual(util._psf_scan_root(raw), raw)

    def test_scan_root_descends_into_child_with_info_file(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            raw = Path(tmp) / "run.raw"
            self._write(raw / "detail" / "detail.info", NON_SWEPT_PSF)
            self.assertEqual(util._psf_scan_root(raw), raw / "detail")

    def test_parse_psf_directory_merges_dc_ac_and_info(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            root = Path(tmp) / "results"
            self._write(root / "dc.dc", NON_SWEPT_PSF)
            self._write(root / "ac.ac.ac", NON_SWEPT_PSF)
            self._write(root / "op.info", NON_SWEPT_PSF)
            parsed = util.parse_psf_directory(root, "all")
        self.assertIn("dc_vout", parsed["data"])
        self.assertIn("ac_vout", parsed["data"])
        self.assertIn("op_vout", parsed["data"])
        self.assertEqual(sorted(parsed["analyses"]), ["ac", "dc", "info"])
        self.assertEqual(parsed["files"], sorted(set(parsed["files"])))

    def test_parse_psf_directory_without_analysis_raises(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            root = Path(tmp) / "empty"
            root.mkdir(parents=True, exist_ok=True)
            with self.assertRaises(ValueError) as ctx:
                util.parse_psf_directory(root, "tran")
        self.assertIn("no PSF analysis", str(ctx.exception))

    def test_parse_psf_directory_with_single_analysis_filter(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            root = Path(tmp) / "results"
            self._write(root / "dc.dc", NON_SWEPT_PSF)
            self._write(root / "op.info", NON_SWEPT_PSF)
            parsed = util.parse_psf_directory(root, "dc")
        self.assertEqual(parsed["analyses"], ["dc"])
        self.assertIn("dc_vout", parsed["data"])
        self.assertNotIn("op_vout", parsed["data"])

    def test_candidate_falls_back_to_the_sorted_glob(self):
        # No exact candidate name is present, so _candidate() must take the
        # *first* match in sorted order - not an arbitrary/last one.
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            root = Path(tmp) / "results"
            self._write(root / "b_op.dc", NON_SWEPT_PSF)
            self._write(root / "a_op.dc", NON_SWEPT_PSF)
            parsed = util.parse_psf_directory(root, "dc")
        self.assertEqual(parsed["files"], ["a_op.dc"])
        self.assertIn("dc_vout", parsed["data"])

    def test_detect_layout_single_raw_and_missing(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            base = Path(tmp)
            single = self._write(base / "tran1.tran.tran", SWEPT_PSF)
            self.assertEqual(util.detect_layout(single), "single")
            raw = base / "raw"
            self._write(raw / "dc.dc", NON_SWEPT_PSF)
            self.assertEqual(util.detect_layout(raw), "raw")
            with self.assertRaises(FileNotFoundError):
                util.detect_layout(base / "nope")

    def test_detect_layout_sweep(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            root = Path(tmp) / "results"
            self._write(root / "sw1-0_a.tran.tran", SWEPT_PSF)
            self.assertEqual(util.detect_layout(root), "sweep")

    def test_list_result_files_reports_relative_names(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            root = Path(tmp) / "results"
            self._write(root / "dc.dc", NON_SWEPT_PSF)
            self._write(root / "notes.txt", "ignored")
            self.assertEqual(util.list_result_files(root), ["dc.dc"])


class TestSweepDirectory(unittest.TestCase):
    def _write(self, path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_classic_layout_skips_non_numeric_point_dir(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            root = Path(tmp) / "results"
            self._write(root / "sw1.sweep1" / "1" / "dc.dc", NON_SWEPT_PSF)
            (root / "sw1.sweep1" / "logs").mkdir(parents=True, exist_ok=True)
            parsed = util.parse_sweep_directory(root)
        self.assertEqual(parsed["layout"], "classic")
        self.assertEqual(parsed["point_count"], 1)
        # Each point is parsed as a raw directory, so merged keys carry the
        # analysis prefix (dc_ / ac_ / <info>_).
        self.assertIn("dc_vout", parsed["signals"])

    def test_classic_layout_skips_files_named_like_sweep_dirs(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            root = Path(tmp) / "results"
            self._write(root / "sw1.sweep1", "not a directory")      # -> continue
            self._write(root / "sw2.sweep2" / "note.txt", "plain")   # -> not a dir
            self._write(root / "sw2.sweep2" / "1" / "dc.dc", NON_SWEPT_PSF)
            parsed = util.parse_sweep_directory(root)
        self.assertEqual(parsed["point_count"], 1)

    def test_flat_layout_ignores_non_matching_names(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            root = Path(tmp) / "results"
            self._write(root / "sw1-0_op.tran.tran", SWEPT_PSF)
            self._write(root / "notes.txt", "ignored")
            parsed = util.parse_sweep_directory(root)
        self.assertEqual(parsed["layout"], "flat")
        self.assertEqual(parsed["point_count"], 1)

    def test_flat_layout_skips_names_the_pattern_cannot_index(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            root = Path(tmp) / "results"
            self._write(root / "swX-1_a.tran.tran", SWEPT_PSF)   # glob yes, regex no
            self._write(root / "sw1-0_a.tran.tran", SWEPT_PSF)
            parsed = util.parse_sweep_directory(root)
        self.assertEqual(parsed["layout"], "flat")
        self.assertEqual(parsed["point_count"], 1)

    def test_no_recognised_layout_raises(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            root = Path(tmp) / "results"
            root.mkdir(parents=True, exist_ok=True)
            with self.assertRaises(ValueError) as ctx:
                util.parse_sweep_directory(root)
        self.assertIn("no sweep layout", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
