# 只读审计任务书：read 路径的"打开方式"是否用错（P-104 同类）

> 执行者：`/root/readonly_open_audit`（只读审计员）｜ 下发：测试/root，2026-09-29
> 产出：`test/reports/round8/readonly-open-audit.md`
> 起因：P-104（`maeOpenSetup` 默认 `?mode "a"` 会**创建** view，读路径没传 `"r"`）。本任务找**其它同类**。

## 硬约束（违反即失败）

1. **只读**：不得修改任何文件（含 `src/`、`test/` 下的 TB/规范/报告、`make_bug_cards.py`）；不得提交 git。
2. **不得做真机试验**：不开 CIW/ADE/Virtuoso 会话、不调产品 API、不创建/删除任何对象。
3. 允许：读文件、`rg`/`git log/diff` 等只读命令、对 `http://127.0.0.1:8123` 的**只读 HTTP 查询**。
4. 需要真机验证才能定论的，写进报告"待 root 真机验证"清单，不要自己跑。
5. 已定案的 **P-104 本体不要再分析/不要动**（用户口径：等修复通知后由 root 复验）。

## 一、背景模板（P-104，供理解模式，不需重复分析）

- 代码：`src/pyapi/packages/maestro.py` 的 `_open_session` 调 `maeOpenSetup(lib cell view)`（未传 `?mode`）。
- 官方文档（8123 → `maeSKILLref.fnd` / `maestroSKILL.html`）：`?mode` 默认 `"a"`（append，原文 "This is the default"）；
  `"r"` = read（"You cannot create a new view in read mode"）；描述含 "If the given cellview does not exist, the function creates a new cellview with the same name."。
- 现象：读路径（read_config/read_results/export/read_history）对不存在的 view 返回 `ok=true` + 空配置，**并在库里建出空 view 目录**。

## 二、任务

1. **静态扫描** `src/`（重点 `src/pyapi/packages/*.py`，并看 `src/bridge/resources/*.py` 与其中生成 SKILL 的 `*.il`），列出所有"打开/获取对象或会话"的调用，例如（按实际出现即可）：
   `maeOpenSetup`、`dbOpenCellViewByType`、`dbOpenCellView`、`geOpen`、`hiOpenWindow`、`hiOpenCellView`、
   `ddGetObj`、`ddGetObjFiles`、`maeOpenResults`、`ahdlOpen`、`schOpen`、`dbOpenLib`、`ddOpenLib`、`dbClose`/`dbSave` 配对等。
2. **逐个查 8123 文档**（只读 HTTP）：
   - `GET http://127.0.0.1:8123/api/find?q=<fn>&mode=exact&limit=5`
   - `GET http://127.0.0.1:8123/api/info?name=<fn>`
   - 三问：**有没有只读参数？默认值是什么？默认会不会创建/加锁/进编辑态？返回值 `nil` 的含义？**
3. **对照代码判定**该调用在**读路径**还是**写路径**：
   - 读路径：`read*` / `read_config` / `read_results` / `read_history` / `export` / `status` / `list*` / `screenshot` / `check`；
   - 写路径：`write*` / `create*` / `delete*` / `generate` / `run`（写路径用默认/可写模式通常合理）。
   - **只标记**：读路径 + 未传只读参数 + 默认有创建/加锁/编辑副作用的组合。
4. 注意"查找+可创建"二合一 API（如 `ddGetObj`，文档明写 "…**and creates** cells, views, and files"）：看代码是否传了创建型 mode。

## 三、交付（写 `test/reports/round8/readonly-open-audit.md`）

1. 表：`函数 | 代码位置（文件:行）| 官方文档结论（含原文引用）| 实际用法（读/写路径 + 传了什么）| 风险（创建/加锁/编辑态/无）| 判定 OK / 疑似问题 / 无法判定 | 建议的只读写法`；
2. 摘要：疑似问题按严重度排序，每条一句话影响；
3. **建议立案清单**（标题 / 位置 / 证据；由 root 建卡，你不要动 `make_bug_cards.py`）；
4. **待 root 真机验证**清单。

完成后给我 ≤12 行汇报：扫了哪些函数、几条疑似、最严重两条、需要 root 做什么。
