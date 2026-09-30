"""Static contracts: log=off must not fetch the log at any layer."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

RES = Path(__file__).resolve().parents[3] / "src" / "bridge" / "resources"


class TestLogOffNoFetch(unittest.TestCase):
    def test_il_has_no_marker_injection(self):
        il = (RES / "ramic_bridge.il").read_text(encoding="utf-8")
        self.assertNotIn('hiPrintToLogFile("VB-BEGIN")', il)
        self.assertNotIn('hiPrintToLogFile("VB-END")', il)
        # every flush/fileLength/meta-frame send is gated by log_on
        # (log_on is parsed from the per-request "RBDLogOn=t" directive)
        self.assertIn("when(log_on", il)
        self.assertIn("hiFlushLogFile()", il)

    def test_il_flushes_ciw_before_reading_log_end(self):
        il = (RES / "ramic_bridge.il").read_text(encoding="utf-8")
        eval_pos = il.index("evalstring(")
        terminator_pos = il.index('errset(printf("\\n"))')
        flush_info_pos = il.index("hiFlushInfo()")
        log_end_pos = il.index("lo_end = fileLength(lp)")
        # evalstring 路径没有交互循环的行终止符：先补一个换行把未完结的
        # CIW 输出行送入 CDS.log，再 hiFlushInfo 让它显示，最后取 lo_end。
        self.assertLess(eval_pos, terminator_pos)
        self.assertLess(terminator_pos, flush_info_pos)
        self.assertLess(flush_info_pos, log_end_pos)
        self.assertNotIn("hiFlushCIW()", il)

    def test_daemons_drop_the_il_terminator_line(self):
        for name in ("ramic_bridge_daemon_3.py", "ramic_bridge_daemon_27.py"):
            src = (RES / name).read_text(encoding="utf-8")
            self.assertIn('raw.endswith("\\\\o \\n")', src, name)
            self.assertIn("raw = raw[:-4]", src, name)

    def test_error_frame_is_built_before_the_log_block(self):
        """errset.errset 是单槽全局值：log 块里的 errset 调用会覆盖/清空它。
        错误载荷必须在 when(log_on) 之前就复制进 frames，否则 error 提取
        会拿到 nil 或 flush 自己的错误。"""
        il = (RES / "ramic_bridge.il").read_text(encoding="utf-8")
        eval_pos = il.index("errset(result=evalstring(")
        err_frame_pos = il.index("errset.errset intToChar(30)")
        log_block_pos = il.index("when(log_on", eval_pos)
        self.assertLess(eval_pos, err_frame_pos)
        self.assertLess(err_frame_pos, log_block_pos)

    def test_daemons_do_not_add_misleading_hiFlush(self):
        for name in ("ramic_bridge_daemon_3.py", "ramic_bridge_daemon_27.py"):
            src = (RES / name).read_text(encoding="utf-8")
            self.assertNotIn("hiFlush()", src, name)

    def test_daemons_gate_meta_frame_on_log_on(self):
        for name in ("ramic_bridge_daemon_3.py", "ramic_bridge_daemon_27.py"):
            src = (RES / name).read_text(encoding="utf-8")
            self.assertIn("log_on = log_level != \"off\"", src, name)
            self.assertIn("if log_on:", src, name)
            self.assertNotIn("_cursor_path", src, name)
            self.assertNotIn("VB-BEGIN", src, name)
            self.assertNotIn("VB-END", src, name)

    def test_off_level_maps_to_empty_log(self):
        sys.path.insert(0, str(RES.parent.parent))
        from bridge.resources.ramic_bridge_daemon_3 import filter_delta
        text, truncated = filter_delta("\\e err\n\\w warn\n", "off", 65536)
        self.assertEqual(text, "")
        self.assertFalse(truncated)


if __name__ == "__main__":
    unittest.main()
