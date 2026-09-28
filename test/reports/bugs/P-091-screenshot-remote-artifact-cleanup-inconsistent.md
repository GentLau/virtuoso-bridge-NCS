# P-091 · 截图远端产物保留策略三包不一致：schematic 保留、symbol/layout 下载后 `rm -f` 删掉（spec 写「远端存 role root screenshots/」）

| 字段 | 值 |
|---|---|
| 级别 | P3（口径/文档级：不影响本地产物，但使「远端留证」与审计核对失效） |
| 层 | 上层（symbol / layout 包）· 与 spec 口径 |
| 归属 | 待归属（spec 口径 owner 或三包实现统一） |
| 状态 | **待决策** |
| 位置 | `src/pyapi/packages/symbol.py:979-987`（finally 里 `rm -f <remote_png>`）；`src/pyapi/packages/layout.py:1480-1487`（同款 finally）；`src/pyapi/packages/schematic.py:814-852`（**不删**，远端长期保留）；spec：`spec/design-concepts/上层/2-schematic.md:27`、`3-symbol.md:41-45`、`4-layout.md:183` 均写「远端存 role root 的 screenshots/」。 |
| 首报 | 2026-09-28（第八轮 screenshot 参数车道实测发现） |
| 最近更新 | 2026-09-28（新立） |

## 现象

真机实测（2026-09-28，`screenshot_params_e2e_tests.py`）：
- `virtuoso.schematic.screenshot` 跑完后远端 `role_root/screenshots/<cell>_<ms>.png` **留存**；
- `virtuoso.symbol.screenshot` / `virtuoso.layout.screenshot` 跑完后同名远端文件 **找不到**（`find /home/vbuser2 -name 'rx_fe-*'` 与 `find /home/Gent -name 'lay_e2e-*'` 均 0 命中，而本地 `artifact/screenshots/*.png` 正常且为合法 PNG）。
⇒ 「远端存 screenshots/」这条 spec 只对 schematic 成立；symbol/layout 把远端当临时暂存并清理。

## 复现

```text
PYTHONPATH=src python test/live/packages/screenshot_params_e2e_tests.py --transport http \
  --token vb-vbuser2 --lib serdes_rx --cell rx_fe --view symbol --kind symbol \
  --out test/artifacts/evidence/round8/screenshot-params/symbol.json
# 同参数换 --kind layout --token vb-vblog --lib schemtest --cell lay_e2e --view layout
```

## 证据

`test/artifacts/evidence/round8/screenshot-params/{schematic,symbol,layout}.json`（SC-01 会把 `remote_present=` 打进 NOTE）；对照 `find` 命令输出见卡片正文。

## 验收判据（修好即转绿）

① spec 与实现二选一对齐：要么三包统一清理（改 spec 文案为「远端暂存」），要么三包统一保留（去 symbol/layout 的 rm）；② 新 TB 的 SC-01 不再出现三包口径分叉。

## 下一步 / 责任人

spec owner 定「暂存 vs 留证」；测试侧按结论改 TB 的 NOTE 为断言。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
