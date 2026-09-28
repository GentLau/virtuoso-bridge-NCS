# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-28 23:52
# 依赖: 真机 vblog token（rc_probe 无 Interactive.* 时本探针自行造一条）
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查：业务面可达；②③ 取一条 Interactive.*（没有就裸 run 造一条）作为基线；
# ④ 只做被测动作（open_waveform_gui 传正确/错误 result 名各一次）；
# ⑤ 读回比对：若错误 result 名与正确名**行为一致**（都成功）⇒ 参数被忽略 ⇒ RED；
# ⑥ 收尾：关闭波形窗口（不删现场）。
"""P-089 红灯钉：`maestro.open_waveform_gui.result` 声明但**从未被实现读取**。

代码证据：`rg -n "request.result" src/pyapi/packages/maestro.py` 只命中
`read_results` 的波形表达式（`:1909/:1912`）；`open_waveform_gui` 的 SKILL
（`:3139-3158`）只做 `v(signal)`，没有 `?result` 分支。

判据：传一个**不存在的** result 名应当结构化失败（或与正确名行为不同）；
若两次都成功且窗口正常 ⇒ 参数静默无效 ⇒ **RED**。
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
    data = body.get("data") or {}
    ok = body.get("ok") is not False and data.get("ok") is not False
    return ok, str(body.get("error") or data.get("error") or ""), (data.get("value") or {})


def main() -> int:
    def interactive_names() -> list[str]:
        _ok, _err, value = call("virtuoso.maestro.read_history",
                                library="maestro_tb", cell="rc_probe",
                                view="maestro")
        return [str(h.get("name")) for h in (value.get("histories") or [])
                if str(h.get("name", "")).startswith("Interactive.")]

    histories = interactive_names()
    if not histories:
        # 自造夹具：不带 history= 的 run 会新建 Interactive.<n>（否则本探针只能 rc=2，
        # 那是环境前置而不是产品结论——`rc_probe` 的 history 会被别的工作流换掉）。
        print("FIXTURE: no Interactive.* in rc_probe -> creating one via bare run")
        ok, err, _v = call("virtuoso.maestro.run", library="maestro_tb",
                           cell="rc_probe", view="maestro", blocking=False,
                           timeout=180)
        if not ok:
            print(f"ENV: bare run failed: {err[:200]}")
            return 2
        deadline = time.time() + 240
        while time.time() < deadline and not histories:
            time.sleep(3)
            histories = interactive_names()
    if not histories:
        print("ENV: no Interactive.* history")
        return 2
    history = histories[-1]

    results = {}
    for label, result_name in (("correct", "ac"), ("bogus", "no_such_result_name")):
        ok, err, value = call("virtuoso.maestro.open_waveform_gui",
                              library="maestro_tb", cell="rc_probe", history=history,
                              signals=["net1"], test="ac", analysis="ac",
                              result=result_name)
        results[label] = {"ok": ok, "error": err[:200],
                          "window": value.get("window") or value.get("win")}
        if ok:
            call("virtuoso.maestro.close_waveform_gui",
                 library="maestro_tb", cell="rc_probe")

    ignored = results["correct"]["ok"] and results["bogus"]["ok"]
    evidence = {"probe": "maestro_open_waveform_result_probe", "history": history,
                "results": results,
                "verdict": "RED(result 参数被忽略)" if ignored else "GREEN(参数生效)",
                "expected": "错误 result 名应失败或行为不同"}
    out = OUT / "p089-open-waveform-result.json"
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False)[:600])
    print("evidence:", out)
    return 0 if not ignored else 1


if __name__ == "__main__":
    raise SystemExit(main())
