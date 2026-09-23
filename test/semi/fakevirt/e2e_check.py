#!/usr/bin/env python3
"""端到端回归：真 client → 真 daemon → fake CIW（对照真机探针结果）。

用法（仓库根目录，Windows 或 WSL 均可）：

    python test/semi/fakevirt/e2e_check.py \
        --host 172.20.170.21 --port 65131 --token vb-lab1 --hostname w1-gent

期望值来源：wsl-gent 真机 IC6.1.8 探针（test/semi/fakevirt/probe_real.py，2026-09-20）：

    1/2               -> 0        （整数除法，向零截断）
    -7/2              -> -3
    1.0/2             -> 0.5      （涉及浮点则浮点除）
    hiFlush()         -> t
    printf(...)       -> t        （log 增量带 "\\o " 前缀）
    boom()            -> ("eval" 0 t nil ("*Error* eval: undefined function" boom))
    ...
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from common.skill_client import SkillClient  # noqa: E402

EXPECT_OK = {
    "1+2": "3",
    "1/2": "0",
    "-7/2": "-3",
    "1.0/2": "0.5",
    "hiFlush()": "t",
    "list(1 2)": "(1 2)",
    "RBDToken": '"vb-lab1"',
}

EXPECT_ERR = {
    "boom()": '("eval" 0 t nil ("*Error* eval: undefined function" boom))',
    "zzz": '("eval" 0 t nil ("*Error* eval: unbound variable" zzz))',
    'strcat(1 2)': (
        '("strcat" 0 t nil ("*Error* strcat: argument #1 should be either '
        'a string or a symbol (type template = \\"S\\")" 1))'
    ),
    'fileLength("/tmp/nonexistent-xyz")': (
        '("fileLength" 0 t nil ("*Error* fileLength: no such file or directory" '
        '"/tmp/nonexistent-xyz"))'
    ),
}

MULTILINE_OK = {
    "1+\n2": "3",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="fake Virtuoso end-to-end check")
    parser.add_argument("--host", default="172.20.170.21")
    parser.add_argument("--port", type=int, default=65131)
    parser.add_argument("--token", default="vb-lab1")
    parser.add_argument("--hostname", default="w1-gent",
                        help="fake CIW 的 getHostName() 期望值")
    args = parser.parse_args()

    client = SkillClient(host=args.host, port=args.port, token=args.token, timeout=15)
    failures = 0

    expect_ok = dict(EXPECT_OK)
    expect_ok["getHostName()"] = f'"{args.hostname}"'
    expect_ok.update(MULTILINE_OK)

    print("== 期望成功的用例 ==")
    for skill, expected in expect_ok.items():
        result = client.execute_skill(skill, log_level="off")
        actual = result.output if result.status.value == "success" else f"<{result.errors}>"
        ok = result.status.value == "success" and result.output == expected
        failures += 0 if ok else 1
        label = repr(skill)
        print(f"{'PASS' if ok else 'FAIL'}  {label:28s} expected={expected!r} actual={actual!r}")

    print("== 期望报错的用例（真机 errset 结构）==")
    for skill, expected in EXPECT_ERR.items():
        result = client.execute_skill(skill, log_level="off")
        ok = result.status.value == "error" and result.errors == [expected]
        failures += 0 if ok else 1
        print(f"{'PASS' if ok else 'FAIL'}  {skill!r:36s} expected_err={expected!r} actual={result.errors!r}")

    print("== log 链路 ==")
    skill = 'printf("probe-log\\n")'
    result = client.execute_skill(skill, log_level="all")
    ok = (
        result.status.value == "success"
        and result.output == "t"
        and result.log == "\\o probe-log\n"
    )
    failures += 0 if ok else 1
    print(f"{'PASS' if ok else 'FAIL'}  {skill!r} output={result.output!r} log={result.log!r}")

    print(f"\n{'ALL PASS' if not failures else f'{failures} FAILURE(S)'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
