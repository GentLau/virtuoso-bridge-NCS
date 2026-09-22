"""File the two defects found during symbol work through POST /api/bug."""
from __future__ import annotations

import json
import urllib.request

CONTROL = "http://127.0.0.1:8124/api/bug"
TOKEN = "vb-vblog"

PROCESS_LIFETIME = {
    "token": TOKEN,
    "title": "Windows Job Object: job.close() 后孙进程仍存活",
    "severity": "high",
    "module": "middleware/common.process_lifetime + server.supervisor",
    "reporter": "upper-layer dev (symbol package)",
    "observed": {
        "test": "test/unit/test_process_lifetime.py::TestProcessJob::test_close_kills_parent_and_descendant",
        "assert_error": "AssertionError: True is not false : descendant survived job close",
        "reproducer_rate": "2/2（单跑该文件、全量 pytest test/unit 都失败；全量里仅此 1 项失败）",
        "facts": [
            "job.assign(parent) 返回 True（测试断言通过）",
            "job.close() 后 parent.wait(timeout=5) 成功 → 父进程确实被杀",
            "等待 5s 后孙进程（parent 在 job.assign 之后 Popen 出来的 python -c sleep(60)）仍存活",
        ],
    },
    "expected": "Job 关闭时（KILL_ON_JOB_CLOSE）父进程及其全部后代都被终止",
    "hypotheses": [
        "运行外壳（agent/CI）本身带 Job，且含 SILENT_BREAKAWAY 语义，导致 CreateProcess 出的进程脱离 Job 树",
        "assign 发生在父进程启动之后（非 CREATE_SUSPENDED → assign → ResumeThread 的原子做法），嵌套 Job 下继承不稳定",
    ],
    "suggestions": [
        "assign 之后调用 IsProcessInJob(parent, NULL, &inJob) 并写进断言消息，先区分‘不在 Job 内’还是‘在 Job 内未被清’",
        "生产路径建议 CREATE_SUSPENDED → AssignProcessToJobObject → ResumeThread，保证子进程从第一条指令起就在 Job 内",
        "若确认为外壳 breakaway 行为，请标注该用例为环境敏感，避免误判产品回归",
    ],
    "evidence_doc": "doc/report/缺陷-进程生命周期-子进程未被Job清除.md",
    "impact": "上层业务包无直接影响；真机若同样失效，supervisor 停机/重启可能遗留隧道或 daemon 后代进程",
}

SKILL_WRAP = {
    "token": TOKEN,
    "title": "daemon 单行/多行 SKILL 语义不一致：多行时 errset(progn ...) 被拆成多实参",
    "severity": "medium",
    "module": "src/bridge/resources/ramic_bridge_daemon_27.py（单行内联 vs 落盘 load() 两条路径）",
    "reporter": "upper-layer dev (symbol package)",
    "observed": {
        "statement": "同一段 SKILL，写成一整行可以跑通；一旦含换行就走落盘 load() 路径，errset(progn ...) 报错",
        "reproduce": [
            "OK（单行）: let((a) a = errset(progn(1 2 3)) car(a)) → 3",
            "FAIL（多行）: 'vbX = errset(progn'  换行  'vbResult = nil' ... → *Error* errset: too many arguments (at most 2 expected, 8 given)",
            "OK（多行，progn( 后紧跟第一条语句）: a = errset(progn(println(\"a\") 换行 ... 42)) → 42",
            "OK（多行，lambda 包裹）: a = errset(funcall(lambda(() ...)))",
        ],
        "impact": "上层业务包在多行 SKILL 里做资源清理（errset/unwindProtect）时会踩坑，且报错信息指向 errset 而非换行，定位成本高",
    },
    "expected": "同一段 SKILL 无论是否含换行，语义应一致；或至少在文档/spec 里写明多行路径的 progn 展开差异",
    "suggestions": [
        "统一两条路径的包裹方式（例如都走落盘 load()，或都不做 progn 包裹）",
        "若确认是 SKILL 语义而非实现缺陷，请在上层开发指南写明‘多行代码里 errset(progn 必须紧跟首条语句’",
    ],
    "evidence_doc": "doc/report/机制-SKILL多行代码errset陷阱.md",
}


def post(payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        CONTROL, data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        print(response.status, response.read().decode("utf-8"))


if __name__ == "__main__":
    post(PROCESS_LIFETIME)
    post(SKILL_WRAP)
