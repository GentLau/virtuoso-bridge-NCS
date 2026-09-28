"""calibre 作业状态判据契约（第五轮新增，先红后绿）。

第五轮真机实测（P-061）：`calibre.lvs` 因输入路径错误 2 秒即退出、日志里有
``ERROR: Can not open source netlist file … for input.``，但
``_calibre_util.job_state`` 判定为 ``unknown``（进程已死 + 有产物），阻塞调用
因此**轮询到超时**（实测 >9 分钟未返回，包内 timeout=1800s）。

本 TB 直接对 ``job_state`` 下判据：进程已死 + 日志终止性 ERROR ⇒ ``failed`` +
``failure_kind``；同时保证"跑完但没有完成标记"仍然不是 failed（避免误报）。
六步流程（test/docs/写TB规范.md §1）——离线用例：
① 环境检查**不适用**：纯函数 / 假 middle，不连真机；②③ 前置构建/校验**不适用**：无持久对象；
④⑤ = Arrange→Act→Assert；⑥ 无现场可留（不落盘、不起服务、不占端口）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from pyapi.packages._calibre_util import job_state  # noqa: E402

ERROR_TAIL = (
    "    DEFINES:\n"
    "    WELL_TO_PG_CHECK DEFINED on line 739 of run_lvs.cal\n"
    "ERROR: Can not open source netlist file /tmp/x.cdl for input.\n"
)


def test_dead_process_with_terminal_error_is_failed():
    state = job_state("lvs", process_alive=False, log_tail=ERROR_TAIL,
                      artifacts=["lvs.rep", "svdb"])
    assert state.status == "failed", (state.status, state.detail)
    assert state.failure_kind == "input", state.failure_kind


def test_dead_process_without_error_marker_stays_unknown():
    """负控制：没有完成标记也没有错误标记时不能误判成 failed。"""
    state = job_state("lvs", process_alive=False,
                      log_tail="still writing report...\n", artifacts=["lvs.rep"])
    assert state.status == "unknown", state.status


def test_running_process_is_running():
    state = job_state("drc", process_alive=True, log_tail="executing...\n", artifacts=[])
    assert state.status == "running"


def test_license_error_is_classified_as_license():
    state = job_state("lvs", process_alive=False,
                      log_tail="ERROR: Cannot checkout license mgcld\n",
                      artifacts=["lvs.rep"])
    assert state.status == "failed"
    assert state.failure_kind == "license", state.failure_kind
