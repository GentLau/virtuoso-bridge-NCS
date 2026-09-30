"""跑"红钉"TB 并判定钉子是否还钉得住（round9 新增）。

为什么需要：`写TB规范.md` 要求缺陷必须挂红钉、修好即转红（XPASS 提醒删标记）。
离线红钉（`pytest.mark.xfail(strict=True)`）会被离线套件天然覆盖；
但**真机红钉**（例如 C06 的 `skill_live/packages/skill_log_semantics_e2e_tests.py`）此前**没有任何 runner 引用**——
没人跑它，就既证明不了"还红"，也无法在修好后转红提醒。

本 runner 的判定：
  * `RED-PIN-HOLDS`：rc != 0（缺陷未修，符合预期）；
  * `RED-PIN-UNEXPECTED-GREEN`：rc == 0 → **缺陷可能已修**，应删红钉/改判；
  * `RED-PIN-BROKEN`：rc != 0 但输出不像"预期失败"（例如全部超时/环境不可用），需要人工看；

退出码：全部 HOLD 时 0；出现 UNEXPECTED-GREEN 或 BROKEN 时 1。

用法::

    python test/shared/runners/run_redpins.py            # 跑全部红钉
    python test/shared/runners/run_redpins.py --only c06 # 只跑某条
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "test" / "artifacts" / "evidence" / "redpins"

#: 红钉清单：key → (TB 路径, 期望"红"的判据说明, 追加参数, 预期失败行正则)
#: 2026-09-30 更新：C06 已修（套件 12/12 绿）→ 移除；加入当前两条真机红钉。
REDPINS: dict[str, tuple[str, str, list[str], str]] = {
    "c09-maestro-history": (
        "test/live/packages/maestro_e2e_tests.py",
        "C09：完整套件内 `write_history` rename 链报 SDB handle 错误（隔离路径已绿、整链仍红）",
        ["--transport", "http"],
        r"FAIL\s+HISTORY-01",
    ),
    "p116-symbol-orders": (
        "test/live/packages/symbol_e2e_tests.py",
        "P-116：spec 3-symbol.md:200 称 pin_order 与 term_order 一致；真机 term_order 未随 schEditPinOrder 同步",
        ["--transport", "http"],
        r"FAIL\s+ORDERS-TERM",
    ),
}


def classify(rc: int, text: str, marker: str) -> str:
    if rc == 0:
        return "RED-PIN-UNEXPECTED-GREEN"
    # 先排除"环境不可用"类红：这类红不能算钉子钉住（否则缺陷修没修都看不出来）
    if re.search(r"SKILL execution timed out|Connect failed|Empty response", text):
        return "RED-PIN-BROKEN"
    # 预期失败必须落在该红钉自己的用例上，否则算"红得不像预期"
    if re.search(marker, text):
        return "RED-PIN-HOLDS"
    return "RED-PIN-BROKEN"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    args = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)

    picked = {k: v for k, v in REDPINS.items() if not args.only or k == args.only}
    rows = []
    bad = 0
    for key, (tb, why, extra, marker) in picked.items():
        log = OUT / f"{key}.log"
        proc = subprocess.run(
            # 注意：Windows 上 `text=True` 会按 locale(GBK) 解码，TB 输出含非 GBK 字节时
            # 读线程会抛 UnicodeDecodeError 并让 stdout 变成 None（2026-09-29 踩到）→ 显式 UTF-8。
            [sys.executable, tb, *extra], cwd=ROOT, text=True,
            encoding="utf-8", errors="replace",
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=3600,
        )
        output = proc.stdout or ""
        log.write_text(output, encoding="utf-8")
        status = classify(proc.returncode, output, marker)
        if status != "RED-PIN-HOLDS":
            bad += 1
        rows.append({"pin": key, "tb": tb, "why": why, "rc": proc.returncode,
                     "status": status, "log": log.relative_to(ROOT).as_posix()})
        print(f"[{status}] {key} rc={proc.returncode} → {log.relative_to(ROOT).as_posix()}",
              flush=True)

    payload = {"generated": dt.datetime.now().isoformat(timespec="seconds"),
               "pins": rows, "actionable": [r["pin"] for r in rows
                                            if r["status"] != "RED-PIN-HOLDS"]}
    (OUT / "redpins.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for r in rows:
        if r["status"] == "RED-PIN-UNEXPECTED-GREEN":
            print(f"  ⚠ {r['pin']} 绿了 → 缺陷可能已修，去删红钉/改判（判据：{r['why']}）")
        elif r["status"] == "RED-PIN-BROKEN":
            print(f"  ⚠ {r['pin']} 红得不像预期（疑似环境/超时），看日志 {r['log']}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
