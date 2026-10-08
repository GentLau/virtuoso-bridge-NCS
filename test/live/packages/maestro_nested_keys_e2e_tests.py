# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-10-08 15:10
# 依赖: test/live/packages/maestro_mc_e2e_tests.py（建 setup 的调用姿势一致）
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查：`basic.skill.execute("1+2")` + maestro_tb / SERDES_TB_LIB / tsmcN65 三库可见；
# ②③ 构建：在 maestro_tb 下建**专属** setup cell `nkm_<stamp>`（set_test + add_output），
#    不碰共享 tb_ctle 的 setup；
# ④ 只做被测动作：每个键一条命令（enabled / enable_tests / disable_tests / model_file /
#    model_section / sections / type_name / type_value / spec_name，以及 P-118 起
#    job policy 三操作 create/attach/delete 的 name/job_type/test 键）；
# ⑤ 读回比对：P-109 补齐后**全部值级断言**（corner 名/变量/参数/启用状态/models、
#    test job_policy、outputs[].spec），不再有 readback:none；
# ⑥ 收尾：只写本 TB 的 cell；证据 JSON 落盘。
"""maestro 嵌套键真机补测（round9 缺口：`nested-key-coverage.md` §2 的 12 个 maestro 键）。

覆盖动机：op×参数矩阵的嵌套键审计发现这 12 个键此前**没有任何 TB 触碰**
（只有离线 L0 契约 `test/offline/unit/test_nested_command_keys_contract.py` 钉住"键→SKILL 拼装"）。
离线契约**不算真机覆盖**，本 TB 把它们逐条打到真机。

判定口径（诚实优先）：

* `model_file` / `model_section` / `job_type` / `enabled` / `enable_tests` / `disable_tests` /
  `test_name` 的公开读回面在 P-109 已补齐（`read_config` 的 corner
  `enabled/enabled_tests/disabled_tests/models[].{name,file,section,test}` 与 test
  `job_policy.{simulation,netlisting}`）→ 本 TB 对 7 键全部做**值级断言**
  （NKM-02/03/05；修复前这三条记为 `readback:none`）。
* `type_name`/`type_value`（set_var/set_parameter 的别名）、`spec_name`（delete_spec）、
  corner 变量/参数、corner 名 → **有公开读回**，逐条值级断言。
* `sections`（load_corners）：正例用 `test/shared/fixtures/maestro_corner65.csv`
  （NKM-07a，corner 名值级读回），负例见 NKM-07b。

用法::

    PYTHONPATH=src python test/live/packages/maestro_nested_keys_e2e_tests.py --transport http \
        --out test/artifacts/evidence/round9/maestro-nested-keys-r9.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"
LIB = "maestro_tb"
DESIGN_LIB, DESIGN_CELL, DESIGN_VIEW = "SERDES_TB_LIB", "tb_ctle", "schematic"
MODEL_FILE = "/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/models/spectre/cor_25.scs"
STAMP = time.strftime("%m%d%H%M%S")
CELL = f"nkm_{STAMP}"
CORNER_CELL = f"nkm_corner_{STAMP}"
TEST = "nkm_test"
OUTPUT = "NKM_OUT"
CORNER_FIXTURE = ROOT / "test" / "shared" / "fixtures" / "maestro_corner65.csv"


class HttpTransport:
    def __init__(self, api: str, token: str) -> None:
        self.api, self.token = api, token

    def call(self, payload: dict[str, Any], timeout: int = 600) -> dict[str, Any]:
        body = json.dumps({"token": self.token, **payload}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.api, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return {"ok": False,
                    "error": f"HTTP {error.code}: {error.read().decode('utf-8')[:300]}"}


def _value(response: dict[str, Any]) -> dict[str, Any]:
    """C1 契约：业务载荷在顶层 `value`（新口径亦可能是 `result`）。"""
    for key in ("value", "result"):
        value = response.get(key)
        if isinstance(value, dict):
            return value
    data = response.get("data")
    return data if isinstance(data, dict) else {}


def _write(transport: HttpTransport, commands: list[dict[str, Any]]) -> dict[str, Any]:
    response = transport.call({
        "operation": "virtuoso.maestro.write",
        "library": LIB, "cell": CELL, "view": "maestro",
        "commands": commands,
    })
    if response.get("ok") is not True:
        raise AssertionError(f"maestro.write failed: {response.get('error')}")
    return _value(response)


def _read_config(transport: HttpTransport, cell: str = CELL) -> dict[str, Any]:
    response = transport.call({
        "operation": "virtuoso.maestro.read_config",
        "library": LIB, "cell": cell, "view": "maestro",
    })
    if response.get("ok") is not True:
        raise AssertionError(f"maestro.read_config failed: {response.get('error')}")
    return _value(response)


def run_suite(transport: HttpTransport) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    results: list[tuple[str, str]] = []
    evidence: dict[str, Any] = {"stamp": STAMP, "cell": CELL, "cases": {}}

    def run(name: str, func) -> Any:
        try:
            value = func()
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            evidence["cases"][name] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            print(f"FAIL    {name}: {type(exc).__name__}: {exc}", flush=True)
            return None
        results.append((name, "PASS"))
        return value

    def case_env() -> None:
        response = transport.call({"operation": "basic.skill.execute", "skill_code": "1+2"})
        assert response.get("ok") is True, f"skill 探活失败: {response.get('error')}"
        assert str(_value(response).get("output") or "").strip() == "3", "1+2 != 3"
        for lib in (LIB, DESIGN_LIB, "tsmcN65"):
            probe = transport.call({
                "operation": "basic.skill.execute",
                "skill_code": f'sprintf(nil "%L" ddGetObj("{lib}")~>name)',
            })
            assert probe.get("ok") is True, f"库 {lib} 探活失败"
            assert lib in str(_value(probe).get("output") or ""), f"库 {lib} 不可见"

    def case_build() -> None:
        _write(transport, [
            {"op": "set_test", "test": TEST, "lib": DESIGN_LIB, "cell": DESIGN_CELL,
             "view": DESIGN_VIEW, "simulator": "spectre"},
            {"op": "add_output", "test": TEST, "name": OUTPUT, "output_type": "net",
             "signal_name": "/VOP", "plot": True, "save": True},
            {"op": "set_var", "name": "NKM_GLOBAL", "value": "1.5", "scope": "global"},
        ])
        cfg = _read_config(transport)
        evidence["cases"]["build"] = {"tests": sorted(cfg.get("tests", {})),
                                      "variables": cfg.get("variables")}
        assert TEST in (cfg.get("tests") or {}), f"set_test 未落盘：{cfg.get('tests')}"
        outputs = [o.get("name") for o in ((cfg["tests"][TEST].get("outputs") or []))]
        assert OUTPUT in outputs, f"add_output 未落盘：{outputs}"
        assert (cfg.get("variables") or {}).get("NKM_GLOBAL") == "1.5", \
            f"全局变量未落盘：{cfg.get('variables')}"

    def case_enabled_and_test_gates() -> None:
        """`enabled` / `enable_tests` / `disable_tests`：corner 元数据值级读回。"""
        _write(transport, [
            {"op": "set_corner", "name": "nkm_c_off", "enabled": False},
            {"op": "set_corner", "name": "nkm_c_gate_on", "enable_tests": [TEST]},
            {"op": "set_corner", "name": "nkm_c_gate_off", "disable_tests": [TEST]},
        ])
        cfg = _read_config(transport)
        corners = cfg.get("corners") or {}
        evidence["cases"]["enabled_and_test_gates"] = {
            "corners": corners,
            "readback": "enabled/enabled_tests/disabled_tests 均从 axlGetEnabled/axlGetCornerDisabledTests 读回",
        }
        for name in ("nkm_c_off", "nkm_c_gate_on", "nkm_c_gate_off"):
            assert name in corners, f"{name} 未出现在 read_config.corners：{corners}"
        assert corners["nkm_c_off"]["enabled"] is False, \
            f"nkm_c_off.enabled 未读回 False：{corners['nkm_c_off']}"
        assert TEST in (corners["nkm_c_gate_on"].get("enabled_tests") or []), \
            f"enable_tests 未读回：{corners['nkm_c_gate_on']}"
        assert TEST in (corners["nkm_c_gate_off"].get("disabled_tests") or []), \
            f"disable_tests 未读回：{corners['nkm_c_gate_off']}"

    def case_setup_corner_model() -> None:
        """`model_file` / `model_section`：corner.models 值级读回。"""
        _write(transport, [
            {"op": "setup_corner", "name": "nkm_c_model", "model_file": MODEL_FILE,
             "model_section": "ss_25", "variables": {"NKM_CV": "0.9"}},
        ])
        cfg = _read_config(transport)
        corner = (cfg.get("corners") or {}).get("nkm_c_model") or {}
        evidence["cases"]["setup_corner_model"] = {
            "corner": corner, "model_file": MODEL_FILE, "model_section": "ss_25",
            "readback": "corner.models[].{file,section} 从 axlGetModel* 读回",
        }
        assert corner, "setup_corner 未创建 corner"
        assert (corner.get("variables") or {}).get("NKM_CV") == "0.9", \
            f"corner 变量未落盘：{corner.get('variables')}"
        models = corner.get("models") or []
        assert any(
            str(model.get("file")) == MODEL_FILE
            and str(model.get("section")) == "ss_25"
            for model in models
        ), f"model_file/model_section 未读回：{models}"

    def case_type_name_type_value_alias() -> None:
        """`type_name` / `type_value`（set_var 的别名）：corner 变量值级读回。

        注：`set_parameter` 的 `name` 必须是 **Library/Cell/View/Instance/Property 五段层次路径**
        （见 NKM-08 负例）；正例已由 `maestro_e2e_tests.py::WRITE-04` 使用
        `maestro_tb/rc_probe/schematic/R0/r` 做值级覆盖（P-111）。
        """
        _write(transport, [
            {"op": "set_var", "name": "NKM_TYPEVAR", "value": "2.25",
             "type_name": "corner", "type_value": "nkm_c_model"},
        ])
        cfg = _read_config(transport)
        corner = (cfg.get("corners") or {}).get("nkm_c_model") or {}
        variables = corner.get("variables") or {}
        evidence["cases"]["type_name_type_value"] = {"corner_variables": variables}
        assert variables.get("NKM_TYPEVAR") == "2.25", \
            f"type_name/type_value 写的变量未落到 corner：{variables}"

    def case_set_parameter_name_contract() -> None:
        """`set_parameter` 名称契约负例；正例已由 maestro_e2e_tests.py::WRITE-04 覆盖
        （`maestro_tb/rc_probe/schematic/R0/r`，global/corner 值级读回，P-111）。"""
        response = transport.call({
            "operation": "virtuoso.maestro.write",
            "library": LIB, "cell": CELL, "view": "maestro",
            "commands": [{"op": "set_parameter", "name": "nkm/param", "value": "4.5"}],
        })
        message = str(response.get("error") or "")
        evidence["cases"]["set_parameter_name_contract"] = {
            "ok": response.get("ok"), "error": message}
        assert response.get("ok") is not True, "非法 set_parameter 名称竟被接受"
        assert "Library/Cell/View/Instance/Property" in message, \
            f"拒绝原因不是名称契约：{message!r}"

    def case_job_policy_job_type() -> None:
        """job policy 三操作真机往返（P-118）：create（具名）→ attach → 值级读回。

        覆盖键：create 的 `name`/`policy`、attach 的 `test`/`name`。
        收尾：去挂载（attach 不带 name）+ 删除具名资源，不留状态。
        """
        policy_name = f"NKM_SIM_POLICY_{STAMP}"
        _write(transport, [
            {"op": "create_job_policy", "name": policy_name,
             "policy": {"maxjobs": 2}},
        ])
        _write(transport, [
            {"op": "attach_job_policy", "test": TEST, "name": policy_name},
        ])
        cfg = _read_config(transport)
        policy = ((cfg.get("tests") or {}).get(TEST) or {}).get("job_policy") or {}
        evidence["cases"]["job_policy_job_type"] = {
            "job_control_mode": cfg.get("job_control_mode"),
            "job_policy": policy,
            "readback": "create(name)+attach(test,name) 后读回该 test 的有效 policy DPL",
        }
        assert TEST in (cfg.get("tests") or {}), "job policy 写入后 test 丢失（破坏状态）"
        sim_policy = (policy.get("simulation") or {})
        assert sim_policy, f"simulation job policy 未读回：{policy}"
        assert int(sim_policy.get("maxjobs") or 0) == 2, \
            f"具名 policy 未反映 maxjobs=2：{sim_policy}"
        assert sim_policy.get("name") == policy_name, \
            f"读回的不是挂载的具名资源：{sim_policy.get('name')!r}"
        _write(transport, [
            {"op": "attach_job_policy", "test": TEST},
            {"op": "delete_job_policy", "name": policy_name},
        ])

    def case_spec_name() -> None:
        """`spec_name`（delete_spec）→ outputs[].spec 值级读回（先添加再删除）。"""
        _write(transport, [
            {"op": "set_spec", "test": TEST, "name": OUTPUT, "lt": 1.0},
        ])
        added = _read_config(transport)["tests"][TEST]["outputs"]
        spec_added = next((o.get("spec") for o in added if o.get("name") == OUTPUT), None)
        evidence["cases"]["spec_name"] = {"after_add": spec_added}
        assert spec_added, f"set_spec 后 outputs[].spec 为空：{added}"
        _write(transport, [
            {"op": "delete_spec", "spec_name": f"{TEST}.{OUTPUT}"},
        ])
        deleted = _read_config(transport)["tests"][TEST]["outputs"]
        spec_deleted = next((o.get("spec") for o in deleted if o.get("name") == OUTPUT), None)
        evidence["cases"]["spec_name"]["after_delete"] = spec_deleted
        assert not spec_deleted, f"delete_spec(spec_name=) 未删掉 spec：{deleted}"

    def case_load_corners_positive() -> None:
        """`load_corners` 正例：合法 CSV 加载出 corner 名（值级读回）。"""
        assert CORNER_FIXTURE.is_file(), f"fixture missing: {CORNER_FIXTURE}"
        response = transport.call({
            "operation": "virtuoso.maestro.write",
            "library": LIB, "cell": CORNER_CELL, "view": "maestro",
            "commands": [{"op": "load_corners", "local_path": str(CORNER_FIXTURE)}],
        })
        cfg = _read_config(transport, CORNER_CELL)
        corners = sorted((cfg.get("corners") or {}).keys())
        evidence["cases"]["load_corners_positive"] = {
            "ok": response.get("ok"), "corners": corners,
            "fixture": str(CORNER_FIXTURE),
        }
        assert response.get("ok") is True, f"load_corners CSV 加载失败：{response.get('error')}"
        assert {"FFF_HVLT", "FSF_LVHT"} <= set(corners), f"CSV corner 未读回：{corners}"

    def case_load_corners_negative() -> None:
        """`load_corners` 负例：本地文件不存在必须结构化失败、不静默成功。"""
        bogus = ROOT / "test" / "artifacts" / "evidence" / "round9" / f"nope_{STAMP}.csv"
        response = transport.call({
            "operation": "virtuoso.maestro.write",
            "library": LIB, "cell": CELL, "view": "maestro",
            "commands": [{"op": "load_corners", "local_path": str(bogus),
                          "sections": "corners"}],
        })
        evidence["cases"]["load_corners_negative"] = {
            "ok": response.get("ok"), "error": response.get("error"),
            "steps": [s.get("name") for s in (response.get("steps") or [])][:6],
        }
        assert response.get("ok") is not True, "load_corners 对不存在的本地文件竟返回成功"

    def case_netlisting_job_policy_p118() -> None:
        """NKM-09（P-118）：netlisting 具名 policy 的 create/attach 必须真落盘读回。

        P-118 根因：旧 `set_job_policy(job_type="netlisting")` 在 test 无
        netlisting policy 时整段静默 no-op（`read_config.job_policy.netlisting`
        恒 null）。新模型下 create/attach 对 netlisting 先自动切 LSCS，取不到
        基础 DPL 或 set 返回 nil 都是结构化失败；本用例做完整往返：

          create(name, netlisting, {maxjobs:1}) → attach(test, name, netlisting)
          → read_config.tests.<test>.job_policy.netlisting.maxjobs == 1
          → 去挂载 + delete（不残留资源）。
        """
        policy_name = f"NKM_NET_POLICY_{STAMP}"
        _write(transport, [
            {"op": "create_job_policy", "name": policy_name,
             "job_type": "netlisting", "policy": {"maxjobs": 1}},
        ])
        _write(transport, [
            {"op": "attach_job_policy", "test": TEST,
             "name": policy_name, "job_type": "netlisting"},
        ])
        cfg = _read_config(transport)
        policy = (((cfg.get("tests") or {}).get(TEST) or {})
                  .get("job_policy") or {})
        net = policy.get("netlisting")
        evidence["cases"]["netlisting_p118"] = {
            "job_control_mode": cfg.get("job_control_mode"),
            "netlisting": net,
        }
        assert net, (
            "P-118 红钉：netlisting 具名 policy 挂载后仍未读回"
            f"（静默 no-op；policy={policy!r}）")
        assert int((net or {}).get("maxjobs") or 0) == 1, \
            f"P-118 红钉：netlisting policy 未按值落盘：{net}"
        _write(transport, [
            {"op": "attach_job_policy", "test": TEST,
             "job_type": "netlisting"},
            {"op": "delete_job_policy", "name": policy_name},
        ])

    run("NKM-ENV 环境检查（1+2 + 三库可见）", case_env)
    run("NKM-01 建专属 setup（set_test + add_output + 全局变量落盘）", case_build)
    run("NKM-02 enabled / enable_tests / disable_tests（值级读回）",
        case_enabled_and_test_gates)
    run("NKM-03 setup_corner model_file/model_section（models 值级读回）", case_setup_corner_model)
    run("NKM-04 type_name/type_value 别名（set_var → corner 变量值级）", case_type_name_type_value_alias)
    run("NKM-05 job_type/test_name（有效 job policy 值级读回）", case_job_policy_job_type)
    run("NKM-06 spec_name（delete_spec → outputs[].spec 值级）", case_spec_name)
    run("NKM-07a load_corners CSV 正例（corner 名值级读回）", case_load_corners_positive)
    run("NKM-07b load_corners 负例（本地文件缺失必须失败）", case_load_corners_negative)
    run("NKM-08 set_parameter 名称契约（非五段路径必须结构化拒绝）", case_set_parameter_name_contract)
    # 红钉放最后：P-118 今天必红，不挡上面的覆盖率。
    run("NKM-09 netlisting 具名 policy create/attach 真机往返（P-118）",
        case_netlisting_job_policy_p118)
    return results, evidence


def main(argv: list[str] | None = None) -> int:
    global API, TOKEN
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=("http",), default="http")
    parser.add_argument("--api", default=API)
    parser.add_argument("--token", default=TOKEN)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    API, TOKEN = args.api, args.token
    results, evidence = run_suite(HttpTransport(args.api, args.token))
    for name, status in results:
        print(f"{status:6}  {name}")
    if args.out:
        evidence["api"] = args.api
        evidence["results"] = [{"case": n, "status": s} for n, s in results]
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        print(f"evidence: {path}")
    return 0 if results and all(s == "PASS" for _, s in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
