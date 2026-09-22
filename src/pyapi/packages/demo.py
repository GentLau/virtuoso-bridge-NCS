"""``demo`` business package: the non-production reference operations.

把一个领域（demo）里的多个业务操作收拢到一个业务包里（spec 上层 §1：插件单元 =
业务包，业务操作是包里的方法）：

* ``demo.pipeline.run``     上传 → Skill → 命令 → 下载（组合示例）
* ``demo.parallel.probe``   并发命令/上传探针（并发示例）
* ``virtuoso.netlist.import``  网表导入参考实现（领域示例）

实现复用已有的三个包类，本模块只做"包 = 业务操作集合"的收拢与登记。
"""
from __future__ import annotations

from dataclasses import dataclass, field

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


@dataclass(frozen=True)
class PathsFactsRequest:
    """``demo.paths.facts``：查询本进程的本机目录（只读）。"""

    token: str


@dataclass
class PathsFactsResult:
    ok: bool
    steps: list[dict] = field(default_factory=list)
    error: str | None = None
    work_root: str = ""
    temp_dir: str = ""
    log_dir: str = ""
    artifact_dir: str = ""


class Package:
    """demo 领域：把参考/示例类业务操作收进一个业务包。"""

    def __init__(self, middle: Middle) -> None:
        self.middle = middle
        self._pipeline = FileSkillCommandFilePackage(middle)
        self._probe = ParallelProbePackage(middle)
        self._netlist = NetlistPackage(middle)

    def run_pipeline(self, request: PipelineRequest) -> PipelineResult:
        return self._pipeline.run_request(request)

    def run_parallel_probe(self, request: ProbeRequest) -> ParallelProbeResult:
        return self._probe.run_request(request)

    def import_netlist(self, request: NetlistRequest) -> NetlistResult:
        return self._netlist.run(request)

    def paths_facts(self, request: PathsFactsRequest) -> PathsFactsResult:
        """返回本机工作根与派生子目录（来自 common 基座，只读）。

        ``common`` 是四层共享的基底模块（进程级路径），上层可直接读；本操作把它
        暴露成业务操作，便于调用方确认自己的落点。
        """
        from common.paths import artifact_dir, log_dir, temp_dir, work_root

        if not isinstance(request.token, str) or not request.token:
            raise ValueError("token must be a non-empty string")
        if self.middle is not None:
            token_check = self.middle.query(token=request.token)
            if token_check.status.value != "success":
                return PathsFactsResult(
                    ok=False,
                    steps=[{
                        "name": "token",
                        "ok": False,
                        "detail": token_check,
                    }],
                    error="; ".join(token_check.errors) or "invalid token",
                )
        facts = {
            "work_root": str(work_root()),
            "temp_dir": str(temp_dir()),
            "log_dir": str(log_dir()),
            "artifact_dir": str(artifact_dir()),
        }
        return PathsFactsResult(
            ok=True,
            steps=[{"name": "paths", "ok": True, "detail": facts}],
            **facts,
        )


#: spec 上层 §4.2：包级自描述（操作名, 方法名, Request, Result）
OPERATIONS = (
    (PIPELINE_OPERATION, "run_pipeline", PipelineRequest, PipelineResult),
    (PROBE_OPERATION, "run_parallel_probe", ProbeRequest, ParallelProbeResult),
    (NETLIST_OPERATION, "import_netlist", NetlistRequest, NetlistResult),
    ("demo.paths.facts", "paths_facts", PathsFactsRequest, PathsFactsResult),
)

OPERATION_NAMES = tuple(operation for operation, *_ in OPERATIONS)

__all__ = ["OPERATIONS", "OPERATION_NAMES", "Package"]
