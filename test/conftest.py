"""Shared pytest fixtures for the offline suites.

The offline tests create work dirs with ``tempfile.mkdtemp(prefix="vb-")``
(the bridge's working-directory contract).  Nothing in the *production* code
owns those dirs, so this fixture gives each **pytest session its own temp root**
and removes that root when the session finishes.

为什么不是"扫描 %TEMP% 里新出现的 vb-* 再删"（2026-09-23 事故）:
旧实现会在会话结束时删掉"本会话开始后新出现的所有 ``vb-*`` 目录"。两个 pytest
会话**并发**跑时（测试台常这么干：一条真机线、一条离线线），会话 A 结束时的清理
会把会话 B **正在用**的目录一起删掉，表现为随机 FileNotFoundError
（``vb-key-*/…`` 消失 → 注册流程用例报 "credential not found"；跨机器 TB 也中过）。
改成"进程私有的 temp 根"后：并发会话互不可见，清理只作用于自己那棵子树。

Scope is **session**, not per-test: several test classes create their work dir
in ``setUpClass`` and keep using it across methods — a per-test sweep would
delete it under them.
"""
from __future__ import annotations

import atexit
import os
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

# 本会话的私有 temp 根：`vbsession-<pid>-<rand>`。
#
# **必须在 conftest 导入时立刻生效**（不能等到 session fixture 才开始）：
# 有些测试模块在 import 期就 `make_credential()` / `mkdtemp()`（例如
# `test_reservation.py`、`test_register_flow.py` 的模块级 `_KEY_DIR`），
# 那些目录一旦落在共享 %TEMP% 里，就可能被**别人的**清理扫掉 →
# validate 报 "credential not found" 这类与环境无关的假红。
#
# 前缀故意不用 `vb-`：老的清理实现（以及别的遗留脚本）按 `vb-*` 扫 %TEMP%，
# 用 `vbsession-` 可以避免被它们误删。
_TEMP_ROOT = Path(tempfile.mkdtemp(prefix=f"vbsession-{os.getpid()}-{uuid.uuid4().hex[:6]}-"))
_PREVIOUS_TEMP = tempfile.tempdir
tempfile.tempdir = str(_TEMP_ROOT)


def _cleanup_temp_root() -> None:
    tempfile.tempdir = _PREVIOUS_TEMP
    shutil.rmtree(_TEMP_ROOT, ignore_errors=True)


atexit.register(_cleanup_temp_root)


@pytest.fixture(autouse=True, scope="session")
def _session_temp_root():
    """兜底：会话期间若有代码改回共享 temp，这里再钉一次；会话结束清理自己的子树。"""
    tempfile.tempdir = str(_TEMP_ROOT)
    try:
        yield _TEMP_ROOT
    finally:
        tempfile.tempdir = _PREVIOUS_TEMP


# ---------------------------------------------------------------------------
# 官方测试姿势：**一个 pytest 会话 = 一个 work root**（2026-09-24 起）
# ---------------------------------------------------------------------------
# 产品口径（`src/common/paths.py`）：work root 是**进程级、一次绑定**的基座，
# 生产里没有任何"换根"的动作。测试也必须遵守：
#
# * 由下面的 session fixture 在会话开始时**绑定一次**（会话私有 temp 根下的
#   `work-root/`），整个 pytest 进程不再换根；
# * 用例要"干净环境"时**不换根**，而是靠 `_reset_shared_registry` 在用例开始前
#   清掉共享根里的 `registry.json`（等价于生产里的"管理端点把注册表清空/重导"），
#   需要并存多个用户时给它们起**各自的名字**；
# * 独立脚本（`test/live/**`、`test/semi/probes/**`、`test/offline/core/*_tb.py`）
#   是**入口**，允许在 `main()` 里用 `init_work_dir(<--work-dir>)` 绑定自己的根
#   —— 一个进程仍然只有一个根。
#
# 迁移期兜底：若某个测试模块在 import 期就绑过根，这里**沿用**它并打印一行，
# 保证套件仍可运行（迁移完成后应看不到这一行）。

_SESSION_WORK_ROOT: Path | None = None


@pytest.fixture(autouse=True, scope="session")
def _session_work_root():
    global _SESSION_WORK_ROOT
    from common.paths import init_work_dir, work_root

    root = _TEMP_ROOT / "work-root"
    try:
        _SESSION_WORK_ROOT = init_work_dir(root)
    except RuntimeError as exc:  # 已被模块级代码绑过：沿用，不换根
        _SESSION_WORK_ROOT = work_root()
        print(f"[conftest] work root already bound -> reuse {_SESSION_WORK_ROOT} ({exc})")
    try:
        yield _SESSION_WORK_ROOT
    finally:
        _SESSION_WORK_ROOT = None


@pytest.fixture(autouse=True)
def _reset_shared_registry(_session_work_root):
    """用例级状态隔离：清共享根里的 `registry.json`（**不动 root**）。

    生产里对应"管理端点把注册表清空后重新导入"；测试用它替代过去的"每个用例
    一个独立 work root"。在 `setUpClass` 里写注册表的类不受影响：它们在每个用例的
    fixture 之前就写好了……除非它们自己也想被清掉——那种类请显式用 `case_dir` 模式。
    """
    from common.paths import registry_path

    path = registry_path()
    try:
        path.unlink()
    except OSError:
        pass
    lock = path.with_suffix(".json.lock")
    try:
        lock.unlink()
    except OSError:
        pass
    yield
