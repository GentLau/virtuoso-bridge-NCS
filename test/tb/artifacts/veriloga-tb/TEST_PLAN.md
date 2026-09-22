# veriloga 业务包 真机测试计划

> 版本：v1
> 日期：2026-09-21
> 对象：`src/pyapi/packages/veriloga.py`（业务包：veriloga）
> 依据：`spec/design-concepts/上层/11-veriloga.md`

## 1. 目标与范围

验证 veriloga 包 3 个对外操作：`read` / `write`（`text.veriloga` 文本视图）
与 `check_and_save`（headless 等价 GUI Check and Save：
`VerAParseModule` + `ahdlUpdateViewInfo`）。

重点验证：

1. ensure_view + set_source 后读回（source/sha256）；
2. check_and_save 成功时返回 module/ports/pin_order/param_list；
3. patch_source 文本替换生效；
4. expected_sha256 守卫：不符必失败且报 sha256 mismatch；
5. 语法错误：check_and_save 失败且 errors 含 `VACOMP-` 诊断；
6. delete_view 删除后视图不存在。

## 2. 环境

| 项 | 值 |
|---|---|
| 业务面 | `127.0.0.1:8127`（验收以 `--transport http` 为准） |
| work-dir | `test/tb/artifacts/log-vblog` |
| token | `vb-vblog` |
| Virtuoso | IC6.1.8-64b + Spectre 24.1 AHDL 编译器（WSL `wsl-gent`） |
| 执行脚本 | `test/tb/veriloga_e2e_tests.py` |

## 3. 测试台

| cell | 用途 |
|---|---|
| `schemtest/va_e2e/veriloga` | 文本视图生命周期 + check_and_save |

编译错误日志落 role root 下 `veriloga_err/schemtest__va_e2e.log`。

## 4. 用例

| 用例 | 覆盖 | 预期 |
|---|---|---|
| WRITE-01 | ensure_view + set_source / read | 源码读回一致 |
| CHECK-01 | check_and_save | 成功，ports 含 a/b、param_list 含 g |
| WRITE-02 | patch_source | 替换后文本含新表达式 |
| WRITE-03 | expected_sha256 守卫 | 错误哈希失败并报 mismatch |
| CHECK-02 | 语法错误 | 失败且 errors 含 `VACOMP-` |
| WRITE-04 | delete_view | 视图删除 |

## 5. 通过准则

- 6 个用例全部 PASS；
- CHECK-02 必须带 `VACOMP-` 诊断原文（不得只报 "parse failed"）；
- 失败保留 `veriloga_err/*.log` 原文；
- 测试视图用后清理。
