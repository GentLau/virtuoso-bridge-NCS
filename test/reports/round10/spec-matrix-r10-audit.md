# round10 · spec 条款矩阵复核（机器结论）

- 输入矩阵：`test/reports/round8/round8-spec覆盖矩阵.json`（297 条）
- 本轮 JUnit：`test/artifacts/evidence/round10/offline-r10.xml`（116 个测试文件）
- 旧结论分布：{'direct': 255, 'indirect': 14, 'na': 60, 'partial': 6}
- **本轮离线证据状态**：{'R10-GREEN': 237, 'NO-OFFLINE-EVIDENCE': 39, 'NA-NO-EVIDENCE-NEEDED': 59}（脚本式 core TB 由 `core-multi-r10.json` 覆盖，ok=True，30 用例）
- 变更影响候选：**0** 条（需逐条改判）

| 状态 | 条数 | 含义 |
|---|---|---|
| R10-GREEN | 237 | 引用的离线证据文件本轮跑过且无红 |
| NA-NO-EVIDENCE-NEEDED | 59 | 条款本身标 na（不要求证据） |
| R10-RED | 0 | 本轮有红 → 该条款结论依赖已立案缺陷 |
| R10-NOT-IN-XML | 0 | 有离线证据文件但本轮 JUnit 里没有 |
| NO-OFFLINE-EVIDENCE | 39 | 只引用了 semi/live/产物类证据（需另核） |
