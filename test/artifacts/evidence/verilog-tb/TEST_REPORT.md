# verilog 业务包 真机测试报告

> 日期：2026-09-22
> 环境：8127 业务面（重启后 PID 18488）· token `vb-vblog` · IC6.1.8 ihdl/oa2verilog
> 脚本：`python test/tb/verilog_e2e_tests.py --transport http`

## 结果

| 用例 | 覆盖 | 结果 |
|---|---|---|
| WRITE-01 | write(ensure_view+set_source) / read(文本视图) / read(本地文件) | **PASS** |
| IMPORT-01 | import(structural_views=4) → functional+symbol | **PASS** |
| IMPORT-02 | 语法错误 → reason=parse_failed | **PASS** |
| EXPORT-01 | import(structural_views=1) + oa2verilog 导出 | **PASS** |

## 本轮修复（测试驱动发现）

1. `getInstallPath()` 返回 SKILL list `("/path")`，原代码当字符串用 →
   `LD_LIBRARY_PATH` 指向非法路径，`ihdl` rc=127（libsasl2.so.2 缺失）→
   改为 `car(getInstallPath())` 解析 + 多候选 lib 路径；
2. `ref_lib_list :=`（空）被 ihdl 判非法 → 空时默认 `basic`；
3. 日志 cells 解析尾随句号（`vlog_imp_top.`）→ 去标点；
4. 测试夹具模块名与 `cell` 参数不一致（EXPORT 用例误用 vlog_imp_* 源码）→
   改为 vlog_exp_* 源码。

## 通过准则复核

- import 成功仅以日志 `End of Logfile.` + 产物视图判定，不信任 rc；
- 失败路径保留 `VERILOGIN-547` 分类与 xmvlog 诊断；
- 测试 cell 均已清理。证据：
  `test/tb/artifacts/http-e2e/verilog_e2e_tests.py.log`。
