# 六步流程（test/docs/写TB规范.md §1）——离线用例：
# ① 环境检查**不适用**：纯函数 / 假 middle，不连真机；②③ 前置构建/校验**不适用**：无持久对象；
# ④⑤ = Arrange→Act→Assert；⑥ 无现场可留（不落盘、不起服务、不占端口）。
# -*- coding: utf-8 -*-
"""上层/处理调度链路的**静态合规约束**（离线，AST 扫描）。

覆盖的 spec 原文：

* `spec/design-concepts/顶层/1-顶层.md:48`「可测试约束：处理/调度模块只允许标准库、
  `common.paths`、`common.jsonutil`、`common.config`、`server.*`、`pyapi.*`；
  **不得出现 `transport.*`、`socket`、`subprocess`、`paramiko`**」；
* `顶层/1-顶层.md:74-75`「不得在业务请求处理链路读 `VB_*`/`.env`/注册表文件，
  不得建立 SSH/TCP/socket/隧道、不得调用 `subprocess`」；
* `上层/1-上层.md:99-100`「上层不导入 `transport.*`/`socket`/`subprocess`/`paramiko`/隧道/端口/注册表/daemon 协议，
  不读 `VB_*`/`.env` 判断 local/remote」。

为什么补这条：原先这条覆盖挂在 `test/upper_layer_paths.py`（靠 `demo` 包的
`demo.paths.facts` 操作取证），**2026-09-24 该包连同用例一起被删除** → 矩阵里这行变成
"引用了不存在的证据"（第七轮逐行核账抓到）。这里改回"直接扫源码"，不依赖任何包是否还在。

负控制：`test_scanner_catches_violation` 在临时目录造一个含 `import paramiko` 的模块，
断言扫描函数**必须**报出来——否则这条用例只是"永远绿"的摆设。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[3] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FORBIDDEN_MODULES = ("transport", "socket", "subprocess", "paramiko")


def _scan(path: Path) -> dict:
    """返回 {'imports': set, 'vb_env': [行], 'dotenv': [行]}（只认字面量，不做符号求值）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    vb_env: list[str] = []
    dotenv: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            args = [a.value for a in node.args if isinstance(a, ast.Constant)
                    and isinstance(a.value, str)]
            if name in ("getenv", "get") and any(str(a).startswith("VB_") for a in args):
                vb_env.append(f"{path.name}:{node.lineno}")
            if name in ("open", "read_text", "read_bytes") and any(
                    str(a).endswith(".env") for a in args):
                dotenv.append(f"{path.name}:{node.lineno}")
        elif isinstance(node, ast.Subscript):
            if isinstance(node.slice, ast.Constant) and \
                    str(node.slice.value).startswith("VB_"):
                vb_env.append(f"{path.name}:{node.lineno}")
    return {"imports": imports, "vb_env": vb_env, "dotenv": dotenv}


def _targets() -> list[Path]:
    """处理/调度链路：业务面全部 pyapi 包 + 顶层 dispatch（管理面 supervisor 不在内）。"""
    files = sorted((SRC / "pyapi").rglob("*.py"))
    files.append(SRC / "server" / "dispatch.py")
    return [path for path in files if path.is_file()]


def test_no_forbidden_imports_in_upper_layer() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _targets():
        hits = sorted(set(_scan(path)["imports"]) & set(FORBIDDEN_MODULES))
        if hits:
            offenders[str(path.relative_to(SRC.parent))] = hits
    assert not offenders, (
        "处理/调度链路出现 spec 明文禁止的依赖（顶层/1-顶层.md:48、上层/1-上层.md:99）："
        f"{offenders}"
    )


def test_no_vb_env_or_dotenv_reads_in_upper_layer() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _targets():
        scan = _scan(path)
        if scan["vb_env"] or scan["dotenv"]:
            offenders[str(path.relative_to(SRC.parent))] = scan["vb_env"] + scan["dotenv"]
    assert not offenders, (
        "业务请求处理链路读了 VB_*/.env（顶层/1-顶层.md:74、上层/1-上层.md:100）："
        f"{offenders}"
    )


def test_scanner_catches_violation(tmp_path: Path) -> None:
    """负控制：扫描器必须能抓到真违规，否则上面两条只是摆设。"""
    bad = tmp_path / "bad_module.py"
    bad.write_text(
        "import paramiko\n"
        "import os\n"
        "TOKEN = os.getenv('VB_REMOTE_HOST')\n"
        "cfg = open('.env')\n",
        encoding="utf-8",
    )
    scan = _scan(bad)
    assert "paramiko" in scan["imports"]
    assert scan["vb_env"], "getenv('VB_*') 必须被抓到"
    assert scan["dotenv"], "open('.env') 必须被抓到"


@pytest.mark.parametrize("rel", ["pyapi/packages/_spectre_util.py", "server/dispatch.py"])
def test_targets_are_actually_scanned(rel: str) -> None:
    """正控制：确认扫描面覆盖到真实文件（防止 _targets() 因路径写错而空扫）。"""
    names = {str(p.relative_to(SRC)) for p in _targets()}
    assert rel.replace("/", "\\") in names or rel in names
