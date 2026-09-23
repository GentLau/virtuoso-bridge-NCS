# veriloga 业务包 真机测试报告

> 日期：2026-09-22
> 环境：8127 业务面（重启后 PID 18488）· token `vb-vblog` · Spectre 24.1 AHDL
> 脚本：`python test/tb/veriloga_e2e_tests.py --transport http`

## 结果

| 用例 | 覆盖 | 结果 |
|---|---|---|
| WRITE-01 | ensure_view + set_source / read | **PASS** |
| CHECK-01 | check_and_save 成功（ports/param_list） | **PASS** |
| WRITE-02 | patch_source | **PASS** |
| WRITE-03 | expected_sha256 守卫 | **PASS** |
| CHECK-02 | 语法错误 → `VACOMP-` 诊断 | **PASS** |
| WRITE-04 | delete_view | **PASS** |

## 本轮修复（测试驱动发现）

1. `VerAParseModule` 对语法错误返回 `nil`，原代码直接报 "no DPL" 且丢弃诊断 →
   改为读 `veriloga_err/*.log` 返回 `VACOMP-` 错误原文；
2. AHDL context 路径 `strcat(getInstallPath() "/tools/lnx86/...")` 双重拼错 →
   改为 `car(getInstallPath()) + "/etc/context/64bit/ahdlSck.cxt"`；
3. DPL alist 解析兼容 `(nil name ... direction ... width ...)` 首元素。

## 通过准则复核

- CHECK-02 返回 `VACOMP-2259/1743/2248/1648` 等诊断原文；
- `ahdlUpdateViewInfo` 成功判定兼容返回 `t`；
- 测试视图已删除。证据：
  `test/tb/artifacts/http-e2e/veriloga_e2e_tests.py.log`。
