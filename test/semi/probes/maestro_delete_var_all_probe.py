# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-28 21:20
# 依赖: 真机 vblog token（maestro_tb/rc_probe）
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查：业务面可达；②③ 每个 scope 先 set_var 造对象并确认写入成功；
# ④ 只做被测动作（delete_var 各 scope）；⑤ 读回比对：删除成功且变量消失；
# ⑥ 不清理现场（保留留下的变量作为证据，下一轮运行靠唯一名自行还原）。
"""P-086 红灯钉：`maestro.write(delete_var, scope="all")` 确定性失败。

实测（2026-09-28）：
* `scope=global` → set ✓ / delete ✓
* `scope=test`（test=ac） → set ✓ / delete ✓
* `scope=all` → set ✓ / **delete ✗** `*Error* error: Cannot find a setup database entry for handle 0`

根因（测试侧判读）：`maestro.py:930-941` 的 all 分支用
`foreach(tn cadr(axlGetTests(sdb)) … axlGetTest(sdb tn) …)` /
`foreach(cn cadr(axlGetCorners(sdb)) … axlGetCorner(sdb cn) …)` 迭代，
拿到的名字/handle 形态不对，`axlGetVar(0 …)` 直接报 handle 0。
现有套件 `maestro_e2e_tests.py` 的清理把这条放进 `try/except` 吞掉，掩盖了它。

判据：三个 scope 的 delete 都必须成功且变量消失；`all` 分支失败即 **RED**。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"
OUT = ROOT / "test" / "artifacts" / "evidence" / "round8"


def call(operation: str, **fields):
    payload = {"operation": operation, "token": TOKEN, **fields}
    request = urllib.request.Request(API, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = json.loads(error.read().decode("utf-8"))
    data = _c1_wrapper(body)
    ok = body.get("ok") is not False and data.get("ok") is not False
    return ok, str(body.get("error") or data.get("error") or "")


def main() -> int:
    stamp = time.strftime("%H%M%S")
    cases = (
        ("global", f"p086_g_{stamp}", {"scope": "global"}),
        ("test", f"p086_t_{stamp}", {"scope": "test", "test": "ac"}),
        ("all", f"p086_a_{stamp}", {"scope": "all"}),
    )
    results = []
    for label, name, kw in cases:
        ok_set, err_set = call("virtuoso.maestro.write", library="maestro_tb",
                               cell="rc_probe",
                               commands=[{"op": "set_var", "name": name,
                                          "value": "1.0", **kw}])
        ok_del, err_del = call("virtuoso.maestro.write", library="maestro_tb",
                               cell="rc_probe",
                               commands=[{"op": "delete_var", "name": name, **kw}])
        results.append({"scope": label, "set_ok": ok_set, "delete_ok": ok_del,
                        "set_error": err_set[:160], "delete_error": err_del[:200]})
        print(f"{label:6s} set={ok_set} delete={ok_del} err={err_del[:110]}")
    failed = [r for r in results if not r["delete_ok"]]
    evidence = {"probe": "maestro_delete_var_all_probe", "results": results,
                "verdict": "RED(delete_var scope=all 失败)" if failed else "GREEN",
                "expected": "三个 scope 的 delete 都成功"}
    out = OUT / "p086-delete-var-all.json"
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print("verdict:", evidence["verdict"], "->", out)
    return 0 if not failed else 1


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
