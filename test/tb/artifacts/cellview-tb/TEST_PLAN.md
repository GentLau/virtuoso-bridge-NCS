# cellview 业务包 真机测试计划

> 版本：v1
> 日期：2026-09-21
> 对象：`src/pyapi/packages/cellview.py`（业务包：cellview）
> 依据：`spec/design-concepts/上层/5-cellview.md`

## 1. 目标与范围

在真实 Virtuoso（IC6.1.8-64b）下验证 cellview 包全部 22 个对外操作：
lib/cell/view/category 四个层级的 list / create / copy / delete / rename，
以及 lib 的 get/bind、category 的 add_cell/remove_cell。

重点验证：

1. 只读操作（lib.list / lib.get / cat.list）对既有库 `schemtest` 可用；
2. 临时库 `cv_e2e_lib` 全生命周期：create → bind → rename → view create/list →
   view copy/rename/delete → cell list/copy/rename/delete；
3. category 全生命周期：create → list → add_cell → cell.list(category=) →
   remove_cell → rename → delete；
4. lib.copy 与清理后 lib.list 不再包含测试库。

## 2. 环境

| 项 | 值 |
|---|---|
| 业务面 | `127.0.0.1:8127`（验收以 `--transport http` 为准） |
| work-dir | `test/tb/artifacts/log-vblog` |
| token | `vb-vblog` |
| Virtuoso | IC6.1.8-64b（WSL `wsl-gent`） |
| 执行脚本 | `test/tb/cellview_e2e_tests.py` |

## 3. 测试台

| 对象 | 用途 |
|---|---|
| `schemtest` | 既有库：只读断言 |
| `cv_e2e_lib` → `cv_e2e_lib2` | 临时库：写生命周期与 rename |
| `cv_e2e_copy` | lib.copy 落点（用完即删） |
| `cv_e2e_cell` | cell/view/category 的载体 cell |
| `cv_e2e_cat` → `cv_e2e_cat2` | category 生命周期 |

远端库根为 role root（`/home/Gent/.virtuoso-bridge/vblog/<lib>`）。

## 4. 用例

| 用例 | 覆盖操作 | 预期 |
|---|---|---|
| CELLVIEW-01 | 全部 22 个操作 | lib.list 含 schemtest；lib.get 返回 path；lib.create 后 bind 成功；rename 可见；view.create 后 view.list 含 schematic；cell.list 含载体 cell；view.copy/rename/delete 成功；cell.copy/rename/delete 成功；cat.create 后 cat.list 含之；add_cell 后 cell.list(category) 含 cell；remove_cell 生效；cat.rename/delete 成功；lib.copy 成功；清理后 lib.list 不含测试库 |

## 5. 通过准则

- CELLVIEW-01 PASS；
- 每个写操作都要有对应的读回证据；
- 失败必须保留失败响应与 SKILL 错误原文；
- 测试库清理失败视为用例失败（不污染环境）。
