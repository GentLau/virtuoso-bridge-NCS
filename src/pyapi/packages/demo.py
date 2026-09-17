"""``demo`` business package: the non-production reference operations.

把一个领域（demo）里的多个业务操作收拢到一个业务包里（spec 上层 §1：插件单元 =
业务包，业务操作是包里的方法）：

* ``demo.pipeline.run``     上传 → Skill → 命令 → 下载（组合示例）
* ``demo.parallel.probe``   并发命令/上传探针（并发示例）
* ``virtuoso.netlist.import``  网表导入参考实现（领域示例）

实现复用已有的三个包类，本模块只做"包 = 业务操作集合"的收拢与登记。
"""
from __future__ import annotations

from pyapi.models import Middle

from pyapi.packages.file_skill_command_file import (
    BusinessResult as PipelineResult,
    FileSkillCommandFilePackage,
    OPERATION_NAME as PIPELINE_OPERATION,
    Request as PipelineRequest,
)
from pyapi.packages.netlist_import import (
    OPERATION_NAME as NETLIST_OPERATION,
    Package as NetlistPackage,
    Request as NetlistRequest,
    Result as NetlistResult,
)
from pyapi.packages.parallel_probe import (
    OPERATION_NAME as PROBE_OPERATION,
    ParallelProbePackage,
    ParallelProbeResult,
    Request as ProbeRequest,
)


class Package:
    """demo 领域：把参考/示例类业务操作收进一个业务包。"""

    def __init__(self, middle: Middle) -> None:
        self._pipeline = FileSkillCommandFilePackage(middle)
        self._probe = ParallelProbePackage(middle)
        self._netlist = NetlistPackage(middle)

    def run_pipeline(self, request: PipelineRequest) -> PipelineResult:
        return self._pipeline.run_request(request)

    def run_parallel_probe(self, request: ProbeRequest) -> ParallelProbeResult:
        return self._probe.run_request(request)

    def import_netlist(self, request: NetlistRequest) -> NetlistResult:
        return self._netlist.run(request)


#: spec 上层 §4.2：包级自描述（操作名, 方法名, Request, Result）
OPERATIONS = (
    (PIPELINE_OPERATION, "run_pipeline", PipelineRequest, PipelineResult),
    (PROBE_OPERATION, "run_parallel_probe", ProbeRequest, ParallelProbeResult),
    (NETLIST_OPERATION, "import_netlist", NetlistRequest, NetlistResult),
)

OPERATION_NAMES = tuple(operation for operation, *_ in OPERATIONS)

__all__ = ["OPERATIONS", "OPERATION_NAMES", "Package"]
