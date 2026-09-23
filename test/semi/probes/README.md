# probes

只读或一次性诊断探针，不作为准出证据。包括 Cadence 文档/技能工具链、Calibre 环境、
GUI/Maestro/Symbol 包探针、`maestro_leak_probe.py` 会话泄漏探针和 SKILL 语法矩阵。

新增：

- `gui_display_probe.py`：gui 包在真实 display 上的半真机表征
  （EWMH 顶层窗口、CIW 定位、整屏截图），覆盖“X11/GUI 现场”里归属上层 gui 包的部分。

探针若需要远端 scratch，必须使用注册表 root 下的 `tmp/` 或显式 `--root`；
输出证据放 `../artifacts/`。
