# 运行数据目录（`test/artifacts/`）

本目录不是测试本身，而是**运行数据的唯一落盘处**；整目录 gitignore（仅保留本 README）。

入库口径：`env/`（注册表等运行状态）与 `tmp/`（临时产物）**一律不进 git**；
只有 `evidence/` 中确实支撑结论的关键证据才用 `git add -f` 入库。

| 子目录 | 放什么 | 生命周期 |
|---|---|---|
| `env/` | 环境：可复用 work-dir、`registry.json`、`local-root/`、fake 群（TB 的 `--work-dir` 指这里） | 跨轮复用，改环境前先确认没有服务在跑 |
| `evidence/` | 产物：一次运行的证据（json/txt/log、报告快照、覆盖率证据） | 一轮一份，**只增不改** |
| `tmp/` | 零时产物：coverage 数据（`tmp/coverage-db/`）、`*.out`、调试 dump | 可随时整目录删除 |

- 命名与内容要求见 [`../docs/写TB规范.md`](../docs/写TB规范.md) §5；根层不再新增散文件。
- 要入库的关键证据用 `git add -f`，并在提交说明写明它支撑哪条结论。
- 每轮会被测试重写的运行产物（离线 green、runner results、导出的 gds/map、探针截图等）默认**退索引**
  （文件留在磁盘）；需要引用时另存 `<run-id>/` 快照再 `git add -f`。
- `admin-token.txt` 是本目录唯一的敏感输入（gitignored），固定在根层，勿复制到别处、勿写进任何提交内容。
- `.coverage*` 只允许出现在 `tmp/coverage-db/`（一次性运行）或 `evidence/cov-main/`（主覆盖率 runner 自带数据文件）；仓库根、`test/` 其他位置一律不许出现。
