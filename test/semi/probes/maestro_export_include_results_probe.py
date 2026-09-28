# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-28 20:05
# 依赖: 真机 vblog token（maestro_tb/rc_probe 有可用 history）
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查：业务面可达 + rc_probe 有 history；②③ 取一条已存在 Interactive.* 作为基线；
# ④ 只做被测动作（同 kind 的 export 分别传 include_results=True/False）；
# ⑤ 读回比对：两次产物的 local_path/bytes/sha 是否一致（若一致 ⇒ 参数被忽略）；
# ⑥ 不清理现场（保留导出件作为证据）。
"""P-084 红灯钉：`maestro.export.include_results` 是声明但**从不被实现读取**的参数。

判据：同一 `kind`（outputs_csv）下 `include_results=True` 与 `=False` 的产物应当不同
（至少 bytes 或文件集合不同）；若完全一致 ⇒ 参数静默无效 ⇒ **RED**。

用法::

    PYTHONPATH=src python test/semi/probes/maestro_export_include_results_probe.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"
OUT = ROOT / "test" / "artifacts" / "evidence" / "round8" / "maestro-include-results"


def call(operation: str, **fields: Any) -> dict[str, Any]:
    payload = {"operation": operation, "token": TOKEN, **fields}
    request = urllib.request.Request(
        API, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return json.loads(error.read().decode("utf-8"))


def value(operation: str, **fields: Any) -> dict[str, Any]:
    body = call(operation, **fields)
    data = body.get("data") or {}
    if body.get("ok") is False or data.get("ok") is False:
        raise SystemExit(f"{operation} failed: {body.get('error') or data.get('error')}")
    return data.get("value") or {}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    histories = value("virtuoso.maestro.read_history",
                      library="maestro_tb", cell="rc_probe").get("histories") or []
    interactive = [h["name"] for h in histories
                   if str(h.get("name", "")).startswith("Interactive.")]
    if not interactive:
        print("ENV: no Interactive.* history in maestro_tb/rc_probe")
        return 2
    history = interactive[-1]

    stamp = dt.datetime.now().strftime("%H%M%S")
    results = {}
    for flag in (True, False):
        target = OUT / f"outputs_include_{flag}_{stamp}.csv"
        target.unlink(missing_ok=True)
        got = value("virtuoso.maestro.export", library="maestro_tb", cell="rc_probe",
                    kind="outputs_csv", history=history, test="ac",
                    include_results=flag, output_path=str(target))
        results[flag] = {"local_path": got.get("local_path"),
                         "bytes": got.get("bytes"),
                         "sha16": sha(target) if target.is_file() else None}

    same_path = results[True]["local_path"] == results[False]["local_path"]
    same_sha = results[True]["sha16"] == results[False]["sha16"]
    # 判据看**内容**：两次导出写到不同 output_path，但若内容 sha 相同，说明
    # include_results 对产物没有任何影响 → 参数被静默忽略。
    verdict = "RED(参数被忽略)" if same_sha else "GREEN(参数生效)"
    evidence = {
        "probe": "maestro_export_include_results",
        "history": history,
        "results": results,
        "same_local_path": same_path, "same_sha": same_sha,
        "verdict": verdict,
        "expected": "include_results=True/False 的产物应有差异（或 spec 删除该参数）",
    }
    out = OUT / "include-results.json"
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=1)[:800])
    print(f"evidence: {out}")
    return 0 if verdict.startswith("GREEN") else 1


if __name__ == "__main__":
    raise SystemExit(main())
