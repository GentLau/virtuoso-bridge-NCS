# round9 · spec 条款矩阵复核（B 线代跑 A 线；机器结论）

- 输入矩阵：`test/reports/round8/round8-spec覆盖矩阵.json`（297 条）
- 本轮 JUnit：`test/artifacts/evidence/round9/offline-windows-r9.xml`（115 个测试文件）
- 旧结论分布：{'direct': 222, 'indirect': 16, 'na': 53, 'partial': 6}
- **本轮离线证据状态**：{'R9-GREEN': 226, 'NA-NO-EVIDENCE-NEEDED': 53, 'NO-OFFLINE-EVIDENCE': 18}（脚本式 core TB 由 `core-multi-r9.json` 覆盖，ok=True，30 用例）
- 变更影响候选：**30** 条（需逐条改判）

| 状态 | 条数 | 含义 |
|---|---|---|
| R9-GREEN | 226 | 引用的离线证据文件本轮跑过且无红 |
| NA-NO-EVIDENCE-NEEDED | 53 | 条款本身标 na（不要求证据） |
| R9-RED | 0 | 本轮有红 → 该条款结论依赖已立案缺陷 |
| R9-NOT-IN-XML | 0 | 有离线证据文件但本轮 JUnit 里没有 |
| NO-OFFLINE-EVIDENCE | 18 | 只引用了 semi/live/产物类证据（需另核） |
