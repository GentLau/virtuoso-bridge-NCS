"""打包入口点与 CLI 契约（非业务面也要有 TB —— 2026-09-30 补）。

覆盖动机：`pyproject.toml` 的 console_scripts 与三个 `python -m` 入口
（`register.server` / `server.supervisor` / `server.api_server`）此前**没有任何用例**：
一旦改名/挪文件，安装后的 `virtuoso-bridge` 命令会直接坏掉，而业务层 TB 全绿也发现不了。

判据（值级）：
* `[project.scripts]` 声明的 `module:attr` 必须可导入且 `attr` 可调用；
* 三个模块入口必须存在，且 `python -m <mod> --help` 成功退出并打印
  文档里承诺的参数名（`--host/--port/--work-dir/--control-port/--business-port`）；
* 控制面入口的默认端口相关参数可被解析（不动网络，只跑 `--help`）。
"""
from __future__ import annotations

import importlib
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = ROOT / "pyproject.toml"


def _console_scripts() -> dict[str, str]:
    text = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(r"\[project\.scripts\](.*?)(?:\n\[|\Z)", text, re.S)
    if not match:
        return {}
    scripts: dict[str, str] = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, target = line.split("=", 1)
        scripts[name.strip().strip('"')] = target.split("#", 1)[0].strip().strip('"')
    return scripts


class PackagingEntrypoints(unittest.TestCase):
    def test_pyproject_declares_console_script_and_target_is_callable(self) -> None:
        scripts = _console_scripts()
        self.assertIn("virtuoso-bridge", scripts, f"console_scripts 缺失: {scripts}")
        target = scripts["virtuoso-bridge"]
        self.assertIn(":", target, f"入口点格式应为 module:attr（实测 {target!r}）")
        module_name, attr = target.split(":", 1)
        module = importlib.import_module(module_name)
        self.assertTrue(callable(getattr(module, attr, None)),
                        f"{target} 不可调用（改名/挪文件？）")

    def _help(self, module: str) -> str:
        result = subprocess.run(
            [sys.executable, "-m", module, "--help"],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace",
        )
        self.assertEqual(result.returncode, 0,
                         f"python -m {module} --help 失败: {result.stderr[-200:]}")
        return (result.stdout or "") + (result.stderr or "")

    def test_control_plane_module_help_contract(self) -> None:
        text = self._help("register.server")
        for flag in ("--host", "--port", "--work-dir"):
            self.assertIn(flag, text, f"控制面 --help 缺 {flag}")

    def test_supervisor_module_help_contract(self) -> None:
        text = self._help("server.supervisor")
        for flag in ("--control-port", "--business-port", "--work-dir"):
            self.assertIn(flag, text, f"supervisor --help 缺 {flag}")

    def test_business_api_module_help_contract(self) -> None:
        text = self._help("server.api_server")
        for flag in ("--host", "--port", "--work-dir"):
            self.assertIn(flag, text, f"api_server --help 缺 {flag}")


if __name__ == "__main__":
    unittest.main()
