# 未解析调用点逐条裁定（78 处）

> 维护：测试（root）｜ 2026-09-28 ｜ 生成器：`test/shared/runners/build_op_param_matrix.py`
> 机器清单：`test/reports/round8/op-param-matrix.md` §未解析调用点（A/B 两节）、
> `test/artifacts/evidence/round8/unresolved-sites.json`

## 结论先说

78 处 = **59 处「管道行」**（op 载体函数内部把形参原样转发，真值在调用点已解析，不构成漏测）
+ **19 处待人工复核**，本次已逐条裁定：

| 类别 | 条数 | 是否影响覆盖结论 |
|---|---:|---|
| 负向/假 op（`nope`、`test.*`、`tb.*`、`skillref.search.probe`，用于 404/400/500/超时/限流判据） | 13 | 否——不是产品 op |
| 动态枚举**真实 op**（循环/参数化拼接），已在别处有解析命中 | 6 | 否——本条已另行核对（见下） |

**没有任何真实业务 op 只出现在"未解析"桶里**；`calibre.pex` / `calibre.export`
「零调用点」的结论不受本桶影响（见 §2 的两处动态拼接证据）。

## 1. 负向 / 假 op（13 条，不影响覆盖）

| 文件:行 | 表达式 | 用途 |
|---|---|---|
| `test/offline/core/api_server_tb.py:235` | `nope.nope.nope` | 顶层 404 |
| `test/offline/core/api_server_tb.py:300` | `test.boom` | 500 且不带 traceback |
| `test/offline/core/api_server_tb.py:396` | `test.ctor` | 构造器失败路径 |
| `test/offline/core/api_server_tb.py:429` / `:447` | `test.slow` | 限流/慢调用 |
| `test/offline/unit/test_top_layer_dispatch.py:67` / `:94` | `tb.echo` | 分发正常/非法字段 |
| `test/offline/unit/test_top_layer_dispatch.py:89` | `nope` | 404 |
| `test/offline/unit/test_top_layer_dispatch.py:101` | `tb.reject` | 领域校验 400 |
| `test/offline/unit/test_top_layer_dispatch.py:107` | `tb.boom` | 未捕获异常 5xx |
| `test/offline/unit/test_middle_contracts.py:167` | `tb.timeout.contract` | timeout 非 bool 400 |
| `test/offline/unit/test_norm_gap_batch2.py:257` | `skillref.search.probe` | 未知字段拒绝 |
| `test/offline/unit/test_round8_clause_gaps.py:93` | `tb.dc_echo` | 未知字段拒绝 |

判定依据：这些名字都**不在** `OPERATIONS`（79 个）里；用例断言的是分发层错误语义，
按设计就不应计入 op×参数矩阵。

## 2. 动态枚举真实 op（6 条，已逐条核对）

| 文件:行 | 表达式 | 实际取值 | 核对结论 |
|---|---|---|---|
| `test/offline/core/api_server_tb.py:281` | `for operation in ("basic.gui.run", "basic.spectre.run")` | 两个真实 basic op | 两者在其它调用点均为 CANDIDATE |
| `test/offline/unit/test_param_timeout_contract.py:174` | `payload["operation"] = op`（循环全部 79 op） | 真实 op 全集 | 即矩阵里「通用 `timeout` 38 条」的合同承担者 |
| `test/semi/probes/calibre_package_http_probe.py:111` | `f"calibre.{args.kind}"` | `--kind` 只允许 `env/drc/lvs` | 取不到 `pex`/`export`，零调用点结论成立 |
| `test/live/packages/calibre_e2e_tests.py:131` | `f"calibre.{kind}"` | 调用处只传 `"drc"` / `"lvs"` 字面量（:147/:204/:309） | 同上 |
| `test/live/packages/cellview_e2e_tests.py:277` | `_expect_fail(transport, operation, …)` | `lib.delete`/`cell.delete`/`view.delete`/`cat.delete` | 四个 op 在别处均有正例命中；此处为负向 |
| `test/shared/fixtures/probe.py:24` | `call(op, **payload)` | 由调用方传入 | 通用夹具，不计覆盖 |

## 3. 管道行（59 条，不构成漏测）

形态固定为

```python
def _op(transport, operation: str, **fields):      # ← 本函数是 op 载体
    return transport.call({"operation": operation, "token": TOKEN, **fields})

def _value(transport, operation, **fields):
    return _op(transport, operation, **fields)      # ← 「管道行」：形参原样转发
```

调用者（真正决定 op 的叶子调用点）写的是字面量，**已被解析并计入矩阵**；
管道行自身没有信息量，单列一类不计覆盖。分布见
`op-param-matrix.md` §未解析调用点 B 节（39 个文件，每文件 1–4 行）。

## 4. 复核方式（可重跑）

```powershell
python test/shared/runners/build_op_param_matrix.py     # 重算矩阵 + 重生成 A/B 分节
```

脚本会把 `enclosing`（调用点所在函数）写进 JSON；`plumbing=True` 即为管道行。
若将来某条 A 节条目被改成真实 op，重跑后它会自动从 A 节消失（或转为 CANDIDATE），
**不需要**手工维护本文件的数字。
