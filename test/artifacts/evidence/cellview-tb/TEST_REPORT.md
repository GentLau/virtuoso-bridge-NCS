# cellview 业务包 真机测试报告

> 日期：2026-09-22
> 环境：8127 业务面（重启后 PID 18488）· token `vb-vblog` · Virtuoso IC6.1.8-64b
> 脚本：`python test/tb/cellview_e2e_tests.py --transport http`

## 结果

| 用例 | 覆盖操作 | 结果 |
|---|---|---|
| CELLVIEW-01 full CRUD | 全部 22 个操作 | **PASS** |

覆盖明细：`lib.list/get/create/bind/rename/copy/delete`、`cell.list/copy/delete/rename`、
`view.list/create/copy/delete/rename`、`cat.list/create/add_cell/remove_cell/rename/delete`。

## 本轮修复（测试驱动发现）

1. 几乎所有 SKILL 生成器括号不平衡（reader 自动补 `)` 后语义错乱）；
2. `if(cond then X nil)` 在 SKILL 中恒返回 nil（else 分支未用 `else` 关键字），
   9 处 `vbLib/vbCell/vbView` 查找全部失效 → 改为三参形式 `if(cond X nil)`；
3. `dbCopyCellView` 第一参数误传库名字符串 → 改为先
   `dbOpenCellViewByType(... vbView~>viewType "r")` 打开 cellview 对象再复制；
4. `_view_copy_skill` / `_cell_copy_skill` 重写为对象级复制（逐 view 打开/复制/关闭）。

## 通过准则复核

- 写操作均有读回证据（rename 后 list 可见、view/cell/cat 生命周期闭环）；
- 测试库 `cv_e2e_*` 全部清理，lib.list 不含残留；
- 无失败残留。全量回归证据见
  `test/tb/artifacts/http-e2e/cellview_e2e_tests.py.log`。
