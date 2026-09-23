# skillref 业务包 真机测试报告

> 版本：v1
> 日期：2026-09-21
> 执行：direct dispatch / work-dir `test/tb/artifacts/log-vblog` / token `vb-vblog`
> 脚本：`test/tb/skillref_e2e_tests.py --transport direct`

## 1. 结论

**direct 真机 5/5 PASS**（HTTP 8127 待基座修复后回归）。

```
PASS    SEARCH-01 local four levels
PASS    SEARCH-02 modes + unknown
PASS    INFO-01 local found/missing
PASS    SEARCH/INFO-02 remote
PASS    ERR-01 bad source/root
```

## 2. 关键证据

| 项 | 实测 |
|---|---|
| local 四层 | name/entry/topic 对 `dbOpenCellView` 均有命中；body 在 `under=["cpf_ref"]` 下命中 `ground bounce` |
| modes | exact 精确命中 `dbOpenCellViewByType`；未知函数查询返回空且 ok=true |
| info | `dbOpenCellViewByType` found=true 且正文含函数名；不存在函数 found=false 且 ok=true |
| remote | 同名 search/info 经 `doc_token` 执行 C/D 成功，结果与 local 同口径 |
| 失败 | 不存在 doc_root → ok=false；非法 `source="mars"` → ok=false |

## 3. 测试中修正的问题

1. direct 测试进程缺少服务进程的同款初始化：8127 启动时执行 `common.config.init_config(config_path())`，
   测试的 `DirectTransport` 原本没做，导致 remote 模式读不到 `skillref.doc_token` 而误报
   "需要查询执行账号"。已在 `DirectTransport.__init__` 补上 config 初始化。

## 4. 已知限制

- 远端正文层整树不建索引（spec §6.5 已裁定），body 搜索需要 `under` 限定或接受 `truncated`；
- `doc_token` 与"token 原样透传"的冲突仍在 spec §6.6 待 owner 裁决（当前按方案 A 实现）；
- HTTP 8127 回归待基座修复后补。
