# -*- coding: utf-8 -*-
"""CDS.log 增量 reader 的独立单元测试。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from spec.demo.cdslog_demo import (
    CdsLogIncrementReader,
    DemoSkillExecutor,
    SkillLogEmitter,
)


class CdsLogDemoTests(unittest.TestCase):
    def test_each_invocation_returns_only_new_byte_range(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vb-log-test-") as temporary:
            path = Path(temporary) / "CDS.log"
            path.write_bytes("old history\n".encode("utf-8"))
            old_size = path.stat().st_size
            reader = CdsLogIncrementReader(path, log_level="all", start_at_end=True)
            emitter = SkillLogEmitter(path)

            first = emitter.invoke(["\\i first 信息", "\\w first warning"], reader)
            second = emitter.invoke(["\\e second error", "second info"], reader)

            self.assertIn("VB-BEGIN", first.text)
            self.assertIn("first 信息", first.text)
            self.assertNotIn("old history", first.text)
            self.assertIn("VB-BEGIN", second.text)
            self.assertIn("second error", second.text)
            self.assertNotIn("first warning", second.text)
            self.assertNotIn("old history", second.text)
            self.assertEqual(first.start_offset, old_size)
            self.assertEqual(second.start_offset, first.end_offset)
            self.assertEqual(reader.cursor, second.end_offset)

    def test_log_levels_filter_after_cursor_is_read(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vb-log-test-") as temporary:
            path = Path(temporary) / "CDS.log"
            lines = [
                "\\i info line\n",
                "\\w warning line\n",
                "\\e error line\n",
            ]
            path.write_text("".join(lines), encoding="utf-8")

            all_reader = CdsLogIncrementReader(path, log_level="all", start_at_end=False)
            warn_reader = CdsLogIncrementReader(path, log_level="warn", start_at_end=False)
            error_reader = CdsLogIncrementReader(path, log_level="error", start_at_end=False)
            off_reader = CdsLogIncrementReader(path, log_level="off", start_at_end=False)

            all_text = all_reader.read_increment().text
            warn_text = warn_reader.read_increment().text
            error_text = error_reader.read_increment().text
            off_result = off_reader.read_increment()

            self.assertIn("info line", all_text)
            self.assertIn("warning line", all_text)
            self.assertIn("error line", all_text)
            self.assertNotIn("info line", warn_text)
            self.assertIn("warning line", warn_text)
            self.assertIn("error line", warn_text)
            self.assertNotIn("warning line", error_text)
            self.assertIn("error line", error_text)
            self.assertEqual(off_result.text, "")
            self.assertEqual(off_reader.cursor, path.stat().st_size)

    def test_oversized_increment_degrades_to_error_only(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vb-log-test-") as temporary:
            path = Path(temporary) / "CDS.log"
            reader = CdsLogIncrementReader(
                path,
                log_level="all",
                log_max_bytes=220,
                start_at_end=False,
            )
            emitter = SkillLogEmitter(path)
            result = emitter.invoke(
                [
                    "\\i " + ("info-" * 30),
                    "\\w " + ("warning-" * 10),
                    "\\e important error",
                ],
                reader,
            )
            self.assertTrue(result.truncated)
            self.assertIn("important error", result.text)
            self.assertNotIn("info-info", result.text)
            self.assertNotIn("warning-warning", result.text)
            self.assertIn("[log truncated: error-only", result.text)
            self.assertLessEqual(result.byte_length, 220)

    def test_many_errors_keep_head_and_tail_when_still_too_large(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vb-log-test-") as temporary:
            path = Path(temporary) / "CDS.log"
            reader = CdsLogIncrementReader(
                path,
                log_level="all",
                log_max_bytes=180,
                start_at_end=False,
            )
            emitter = SkillLogEmitter(path)
            result = emitter.invoke(
                ["\\e error-{:03d}-{}".format(i, "x" * 12) for i in range(40)],
                reader,
            )
            self.assertTrue(result.truncated)
            self.assertIn("error-000", result.text)
            self.assertIn("error-039", result.text)
            self.assertIn("[log truncated: error-only", result.text)
            self.assertLessEqual(result.byte_length, 180)

    def test_file_rotation_resets_cursor(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vb-log-test-") as temporary:
            path = Path(temporary) / "CDS.log"
            reader = CdsLogIncrementReader(path, log_level="all", start_at_end=False)
            emitter = SkillLogEmitter(path)
            first = emitter.invoke(["before rotation"], reader)
            self.assertGreater(first.end_offset, 0)

            path.write_text("fresh after rotation\n", encoding="utf-8")
            after = reader.read_increment()
            self.assertEqual(after.start_offset, 0)
            self.assertIn("fresh after rotation", after.text)
            self.assertEqual(reader.cursor, path.stat().st_size)

    def test_skill_result_exposes_increment_as_log_field(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vb-log-test-") as temporary:
            path = Path(temporary) / "CDS.log"
            reader = CdsLogIncrementReader(path, start_at_end=True)
            executor = DemoSkillExecutor(path, reader)
            result = executor.execute_skill("1+1", ["\\e one error"])
            self.assertEqual(result.status, "success")
            self.assertEqual(result.output, "1+1")
            self.assertIn("VB-BEGIN", result.log)
            self.assertIn("one error", result.log)

    def test_invalid_configuration_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vb-log-test-") as temporary:
            path = Path(temporary) / "CDS.log"
            with self.assertRaises(ValueError):
                CdsLogIncrementReader(path, log_level="verbose")
            with self.assertRaises(ValueError):
                CdsLogIncrementReader(path, log_max_bytes=0)


if __name__ == "__main__":
    unittest.main()
