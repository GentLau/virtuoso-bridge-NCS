# 用例档位审计（semi/live 调用点 × 非法档线索）

> 矩阵：`test/reports/round8/op-param-matrix.json`；op 总数 **78**。
> `single`（live/semi 只出现 1 次）**2**；`no_negative_hint` **10**。

## single（需人工确认是否只有一个档位）

- `virtuoso.gui.list_windows`
- `virtuoso.skillref.info`

## no_negative_hint（需人工确认非法档写法）

- `basic.command.run`
- `basic.skill.execute`
- `calibre.lvs`
- `calibre.read_results`
- `virtuoso.gui.list_windows`
- `virtuoso.layout.gds`
- `virtuoso.layout.read`
- `virtuoso.layout.write`
- `virtuoso.schematic.read`
- `virtuoso.schematic.write`

> 口径：本工具只出清单；分诊结论请写在 round10 的审计 md 里（含误报/真实缺口）。
