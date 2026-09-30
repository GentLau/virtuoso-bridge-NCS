# round9 · 半真机 3 个红的分诊结论（已全部消解）

> 执行：subagent `/root/log_semantics_r9`（复核 + 复跑）｜2026-09-29 21:56
> 对象：`test/artifacts/evidence/round9/semi-r9-final.log`（21:24 整组）summary 的 3 个失败
> 口径：复跑证据落 `test/artifacts/evidence/round9/`；结论只认复跑 rc/JSON。

## 1. `maestro_env_probe.py`（21:14 红，rc=1）→ ✅ 已修已复跑绿

- 原红：`test/semi/probes/_maestro_tb.py:59` 的 `inner["result"][0..2]` 对
  C4 命名字段 `CommandResult` 取位置索引 → `KeyError: 0`（2s 即死）。
- 修复：`_maestro_tb.py` 的 `shell()` 改为先取 `result["returncode"|"stdout"|"stderr"]`（21:27 生效；作者头为设计侧）。
- 复跑（21:55）：`python test/semi/probes/maestro_env_probe.py` → **rc=0**；
  日志 `round9/maestro-env-probe-r9b.log`（libraries/…/`== rfExamples cells (29) == True []` 全绿）。

## 2. `maestro_e2e_probe.py`（21:19 红，rc=1）→ ✅ 已修已复跑绿

- 原红：同上（`_maestro_tb.py` 位置索引）→ `step_disk` 处 `KeyError: 0`。
- 复跑（21:55）：`python test/semi/probes/maestro_e2e_probe.py` → **rc=0**；
  日志 `round9/maestro-e2e-probe-r9b.log`（schematic/maestro/inspect/disk/lib/cell 全走通）。

## 3. `one_shot_burst_tb.py`（21:22 红，rc=2，12/72 transport 失败）→ ✅ 伪红（并发争用）

- 根因：整组 semi 与门禁 maestro **同时**占用 vblog CIW；探针本身设计用于暴露
  `ChannelException(2,"Connect failed")` 压力，但要求每调用仍取回自己的答案——
  并发行把预期压力放大成真实 transport 失败。
- 反证（root 21:27 solo）：36×3 组 **rc=0**、gui 36/36、spectre 36/36、`failures: []`，
  证据 `round9/one-shot-burst-r9.json`。

## 4. 收口口径（供主报告）

半真机整组 40 探针在 **21:24** 的第一次跑批为 `ok=False`（3 红，全部为上述原因）；
3 红已在 21:27–21:55 全部消解（2 个 TB 侧修复后复跑绿 + 1 个并发伪红有 solo 绿证据）。
主报告应写"**半真机 40 探针：首次整组 37 绿 3 红；3 红经分诊/复跑全部消解（非产品缺陷）**"，
并指向本文件 + `round9/{maestro-env-probe-r9b.log, maestro-e2e-probe-r9b.log, one-shot-burst-r9.json}`。
