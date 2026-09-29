# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-29 15:05
# 依赖: 无（业务面 8127 + vb-vblog）
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查：业务面可达；②③ 无需构建（探针自带正/负两例）；
# ④ 只做被测动作（带已删字段的 export / 不带的 export）；
# ⑤ 比对：前者必须被拒、后者必须成功；⑥ 保留 JSON 证据，不改共享库。
"""P-084 回归（口径已定，2026-09-29）：`maestro.export.include_results` 按方案②从模型/spec **删除**。

判据（负向 + 正向 sanity）：
  * 传 `include_results=True` → **必须被拒**（invalid request / unexpected keyword）；
  * 不带该字段的正常 `outputs_csv` 导出 → **必须成功**且产物落盘。
两者同时满足 ⇒ GREEN；若该字段又被静默接受（或正常导出失败）⇒ RED。

用法::

    PYTHONPATH=src python test/semi/probes/maestro_export_include_results_probe.py
"""
from __future__ import annotations

import datetime as dt
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
    data = _c1_wrapper(body)
    if body.get("ok") is False or data.get("ok") is False:
        raise SystemExit(f"{operation} failed: {body.get('error') or data.get('error')}")
    return data.get("value") or {}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%H%M%S")
    target = OUT / f"outputs_plain_{stamp}.csv"
    target.unlink(missing_ok=True)

    # ① 负向：已删除的字段必须被拒（方案②：模型/spec 已删该参数）
    rejected = call("virtuoso.maestro.export", library="maestro_tb", cell="rc_probe",
                    kind="outputs_csv", test="ac", include_results=True,
                    output_path=str(target))
    rejected_text = json.dumps(rejected, ensure_ascii=False)
    field_rejected = (rejected.get("ok") is False) and (
        "include_results" in rejected_text or "invalid request" in rejected_text)

    # ② 正向 sanity：不带该字段的正常导出必须成功、产物落盘
    plain = call("virtuoso.maestro.export", library="maestro_tb", cell="rc_probe",
                 kind="outputs_csv", test="ac", output_path=str(target))
    plain_value = (_c1_wrapper(plain)).get("value") or {}
    plain_path = str(plain_value.get("local_path") or "")
    plain_ok = bool(plain.get("ok")) and bool(plain_path) and Path(plain_path).is_file()

    verdict = ("GREEN(字段已删除且被拒)" if (field_rejected and plain_ok)
               else f"RED(field_rejected={field_rejected}, plain_ok={plain_ok})")
    evidence = {
        "probe": "maestro_export_include_results",
        "case": "include_results 已删：传入必须被拒；不带该字段的导出必须成功",
        "rejected_error": str(rejected.get("error"))[:400],
        "field_rejected": field_rejected,
        "plain_export_ok": plain_ok,
        "plain_local_path": plain_path or None,
        "verdict": verdict,
        "expected": "include_results 传入 → 结构化拒绝；正常 export → 成功（spec 已删该参数）",
    }
    out = OUT / "include-results.json"
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=1)[:800])
    print(f"evidence: {out}")
    return 0 if verdict.startswith("GREEN") else 1


if __name__ == "__main__":
    raise SystemExit(main())


# --- C1 兼容垫片（2026-09-29，C3）------------------------------------------------
# C1（2f88853）起：业务载荷直返顶层（值型 `value`、命令/skill 型 `result`）、
# 成功默认省略 `steps`、失败壳去掉 `data`。历史 TB 按 `response["data"]` 解析，
# 本垫片把新契约响应合成为旧 `data` 壳，让既有解析零改动继续工作。
def _c1_wrapper(body):
    if not isinstance(body, dict):
        return {}
    if isinstance(body.get("data"), dict):
        return body["data"]
    wrapped = {"ok": body.get("ok"), "error": body.get("error")}
    for key in ("value", "result", "steps"):
        if key in body:
            wrapped[key] = body[key]
    return wrapped
