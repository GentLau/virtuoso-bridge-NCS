# verilog 业务包 真机测试计划

> 版本：v1
> 日期：2026-09-21
> 对象：`src/pyapi/packages/verilog.py`（业务包：verilog）
> 依据：`spec/design-concepts/上层/8-verilog.md`

## 1. 目标与范围

验证 verilog 包 4 个对外操作：`read` / `write`（`text.v` 文本视图）、
`import`（`ihdl` 结构网表导入，默认 functional+symbol）、
`export`（`oa2verilog`）。

重点验证：

1. 文本视图 ensure_view + set_source 后按 `read(focus=[source])` 读回；
2. 本地文件读（file_path + file_is_local）；
3. `ihdl` 导入：`LD_LIBRARY_PATH` 正确、`ref_lib_list` 默认 `basic`、
   日志 `End of Logfile.`、cells 去标点后含顶层；
4. 语法错误导入失败且 `reason == parse_failed`；
5. `structural_views=1`（schematic）导入后 `oa2verilog` 导出，
   产物含 module 头、module_count ≥ 1。

## 2. 环境

| 项 | 值 |
|---|---|
| 业务面 | `127.0.0.1:8127`（验收以 `--transport http` 为准） |
| work-dir | `test/tb/artifacts/log-vblog` |
| token | `vb-vblog` |
| Virtuoso | IC6.1.8-64b（WSL `wsl-gent`，ihdl/oa2verilog 同机） |
| 执行脚本 | `test/tb/verilog_e2e_tests.py` |

## 3. 测试台

| cell | 用途 |
|---|---|
| `schemtest/vlog_text/verilog` | 文本视图写/读 |
| `schemtest/vlog_imp_top` | functional 导入（含子模块 `vlog_imp_nand2`） |
| `schemtest/vlog_exp_top` | schematic 导入 + oa2verilog 导出（子模块 `vlog_exp_nand2`） |

源码经本机 `verilog/` 暂存目录上传（file_is_local=true）。

## 4. 用例

| 用例 | 覆盖 | 预期 |
|---|---|---|
| WRITE-01 | write(ensure_view+set_source) / read(文本视图) / read(本地文件) | 文本内容读回一致 |
| IMPORT-01 | import(默认 structural_views=4) | reason=completed、cells 含顶层与子模块 |
| IMPORT-02 | import(语法错误) | 失败且 reason=parse_failed |
| EXPORT-01 | import(structural_views=1) + export | 导出 .v 落盘、含 module 头、module_count≥1 |

## 5. 通过准则

- 4 个用例全部 PASS；
- import 成功判定只看日志 `End of Logfile.` 与产物视图（不信任 rc）；
- 失败保留 `verilogIn.batch.log` / `xmvlog.log` 关键行；
- 测试 cell 用后删除。
