# C11 · `/api/user/*` 仍收归管理员且 `enhanced_token` 未接入 update：个人 token + 增强凭据无法自助查询/修改自己的注册表条目

| 字段 | 值 |
|---|---|
| 级别 | P2（个人管理核心能力不可达：真实控制面对个人 token 稳定 401；前端只能显示缺口或错误地借用管理员权限） |
| 层 | 控制面权限模型（个人自助 registry） |
| 归属 | 设计侧（先定个人自助权限矩阵/端点语义，再由 server 实现；不能只改前端） |
| 状态 | **待决策** |
| 位置 | spec：`spec/design-concepts/顶层/add-控制面与业务面.md:67-95`（query/update/delete 均标管理权限，且明确“个人 token 不能自助修改”）、`spec/design-concepts/中层/add-中层配置文档.md:47`（仅 `mode=local` 需管理权限，无字段级个人权限矩阵）；实现：`src/register/server.py:232-285`（`/api/users`、`/api/user/<user>`、update、delete 入口先走 `_require_admin()`）、`:723-802`（update 只接受管理端 patch）、`:361-390`（`enhanced_token` 只在 `POST /api/register apply` 校验）。 |
| 首报 | 2026-09-30（个人管理页真机查询 401，root 复核 spec 与实现） |
| 最近更新 | 2026-09-30（新立；前端停止用管理员凭据代偿） |

## 现象

真实 8124 实测：`Authorization: Bearer <管理员 token>` → `GET /api/user/<user>` 200；`Authorization: Bearer <该 user 的个人 token>` → 401 `unauthorized`。因此个人页无法按目标语义“个人 token 证明本人身份 + enhanced_token 证明受保护变更权限”工作。当前 spec 与实现彼此一致（都规定 admin-only），但都缺少产品要求的个人自助权限模型。

## 复现

```text
1. 从 work-dir registry 取某 user 的个人 token；
2. `curl -H 'Authorization: Bearer <personal>' http://127.0.0.1:8124/api/user/<user>` → 401；
3. 同请求改用管理员 token → 200；
4. 前端个人页严格用 personal Authorization 提交，不再回退管理员凭据。
```

## 证据

`doc/report/控制台三页-后端接口与权限缺口.md`；代码锚点 `src/register/server.py:232-285,361-390,723-802`；页面契约测试 `test/offline/unit/test_registration_page.py::test_personal_page_combines_query_and_update`（要求 personal Authorization 且禁止 enhanced 回退）。

## 验收判据（修好即转绿）

① spec 补字段级权限矩阵，明确 personal token 只能访问本人、哪些字段普通修改、哪些字段必须 `enhanced_token`；② server 提供 personal-token-only-own-user 的查询/更新语义，并在 update 接入 `enhanced_token`（只校验、不落盘、不回显）；③ 个人页无需管理员 token 即可查询/修改自己的 registry；④ 负例：个人 token 访问他人条目必须拒绝。

## 下一步 / 责任人

spec owner 先拍板权限矩阵与 self 端点形状；后端按 spec 实现。前端已移除管理员 Authorization 回退，仍在 401 时显式点名该缺口。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> 卡片**可以手改**（测试侧维护：补现象、补判据、补证据直接写在卡里即可）。唯一要注意的是
> `make_bug_cards.py` 重新生成同名卡会覆盖手改内容——手改后顺手同步到 `make_bug_cards.py`
> 的对应条目（或先留一份），就不会丢（见 2026-09-28 教训：P-074 的「讨论决策」一度被刷新吃掉，已回填）。
