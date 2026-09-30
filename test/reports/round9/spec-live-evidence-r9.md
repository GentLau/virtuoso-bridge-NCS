# 只引 semi/live 证据的条款 → 本轮产物对表（机器结论）

- 口径：本轮 = mtime ≥ 2026-09-29 18:00
- 条数 18；状态分布 {'R9-LIVE-STALE': 2, 'R9-LIVE-FRESH': 16}

| 条款 | verdict | 本轮状态 | 证据（解析后） |
|---|---|---|---|
| `路由#024` | indirect | R9-LIVE-STALE | None |
| `注册#007` | direct | R9-LIVE-FRESH | None; test/artifacts/evidence/semi-probes.json |
| `注册#011` | indirect | R9-LIVE-FRESH | test/artifacts/evidence/semi-probes.json; None |
| `注册#040` | direct | R9-LIVE-FRESH | test/artifacts/evidence/semi-probes.json; None |
| `schematic#018` | direct | R9-LIVE-STALE | None; test/artifacts/evidence/round8/screenshot-params/schematic.json |
| `schematic#025` | direct | R9-LIVE-FRESH | test/artifacts/package-e2e-r9-full/schematic.log; test/artifacts/evidence/atom-coverage-2026-09-28.json |
| `symbol#026` | direct | R9-LIVE-FRESH | test/artifacts/package-e2e-r9-full/symbol.log; test/artifacts/evidence/semi-probes.json |
| `symbol#082` | indirect | R9-LIVE-FRESH | test/artifacts/evidence/semi-probes.json; test/artifacts/package-e2e-r9-full/symbol.log |
| `layout#048` | direct | R9-LIVE-FRESH | test/artifacts/package-e2e-r9-full/layout.log; test/artifacts/evidence/atom-coverage-2026-09-28.json |
| `layout#079` | indirect | R9-LIVE-FRESH | test/artifacts/package-e2e-r9-full/layout.log; test/artifacts/evidence/semi-probes.json |
| `layout#179` | direct | R9-LIVE-FRESH | None; test/artifacts/evidence/round8/layout-geometry-classification.json; test/artifacts/package-e2e-r9-full/l |
| `verilog#060` | indirect | R9-LIVE-FRESH | None; test/artifacts/package-e2e-r9-full/verilog.log |
| `verilog#065` | indirect | R9-LIVE-FRESH | None; test/artifacts/package-e2e-r9-full/verilog.log |
| `verilog#099` | indirect | R9-LIVE-FRESH | test/artifacts/package-e2e-r9-full/verilog.log |
| `veriloga#069` | direct | R9-LIVE-FRESH | test/artifacts/package-e2e-r9-full/veriloga.log; test/artifacts/evidence/round8 |
| `veriloga#088` | indirect | R9-LIVE-FRESH | None; test/artifacts/package-e2e-r9-full/veriloga.log |
| `veriloga#094` | direct | R9-LIVE-FRESH | test/artifacts/package-e2e-r9-full/veriloga.log; None |
| `calibre#172` | indirect | R9-LIVE-FRESH | test/artifacts/evidence/semi-probes.json; None |
