"""客户端 Python 版本守卫（spec r17）：<3.9 只警告、不拒绝启动。"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from common import runtime_env
from register import server as register_server
from server import api_server, supervisor


class TestClientPythonWarning(unittest.TestCase):
    def setUp(self):
        runtime_env._warned = False

    def test_supported_interpreter_stays_quiet(self):
        with redirect_stderr(io.StringIO()) as err:
            self.assertIsNone(runtime_env.warn_if_client_python_unsupported())
        self.assertEqual(err.getvalue(), "")

    def test_old_interpreter_warns_once_without_refusing_to_run(self):
        stderr = io.StringIO()
        with mock.patch.object(
            runtime_env.sys, "version_info", (3, 8, 10)
        ), redirect_stderr(stderr):
            text = runtime_env.warn_if_client_python_unsupported()
            again = runtime_env.warn_if_client_python_unsupported()
        self.assertIsNotNone(text)
        self.assertIn("3.8", text)
        self.assertIn("3.9", text)
        self.assertIn("unspecified", text)
        self.assertIsNone(again, "同一进程只提示一次")
        self.assertEqual(stderr.getvalue().count("warning:"), 1)

    def test_all_client_entrypoints_call_the_guard(self):
        """三个客户端入口（注册/业务/管理）都必须先过警告守卫。"""
        for module in (register_server, api_server, supervisor):
            with self.subTest(module=module.__name__):
                with mock.patch.object(
                    runtime_env, "warn_if_client_python_unsupported"
                ) as warned, mock.patch.object(
                    sys, "stdout", io.StringIO()
                ):
                    with self.assertRaises(SystemExit):
                        module.main(["--help"])
                warned.assert_called_once()


if __name__ == "__main__":
    unittest.main()
