# Bug 报告：schematic read 生成的 SKILL 在 daemon 端 load 失败

> 日期：2026-09-18
> 报告人：上层业务包开发
> 严重程度：阻塞 schematic 业务包真机验证
> 归属：待定位（daemon 侧 SKILL 加载 / 上层生成的 SKILL 文本）

## 1. 现象

调用 `schematic.Package.read()`（上层业务包，通过 `BusinessServer` 直连）时，`middle.execute_skill()` 返回：

```python
status = error
errors = [
  '("load" 0 t nil ("*Error* load: error while loading file - \\"/tmp/vb_eval_ggd7r747.il\\" at line 7"))'
]
```

简单 SKILL（列库、列 cell/view）在同一 token 下执行正常。

## 2. 环境

- 端口：8127（`server.api_server`）
- work-dir：`C:\Users\user\Desktop\repos_Github\virtuoso-bridge-NCS\test\tb\artifacts\log-vblog`
- token：`vb-vblog`
- Virtuoso：6.1.8-64b（WSL）
- 上层包：`src/pyapi/packages/schematic.py`（Draft v2 对应实现）

## 3. 复现

```python
import sys
sys.path.insert(0, "src")
from transport.middle import BusinessServer
from pyapi.packages.schematic import Package, ReadRequest

middle = BusinessServer(r"test/tb/artifacts/log-vblog")
pkg = Package(middle)
r = pkg.read(ReadRequest(
    token="vb-vblog",
    library="rfLib",
    cell="LNA_PB",      # 该库存在 schematic view 的 cell
    focus="connectivity",
    timeout=120,
))
print(r.ok, r.error)    # False, errors 含上述 load 错误
```

生成的完整 SKILL 文本已 dump 到：
`test/tb/artifacts/dump_read.il`

（对 `ReadRequest(library="rfLib", cell="LNA_PB", focus="connectivity")` 的 dump）

## 4. 已排查（上层侧）

1. `py_compile` 通过；
2. 简单 SKILL 调用（`ddGetLibList`、遍历 cell/views）成功；
3. 对生成 SKILL 做了括号配对、字符串配对人工检查，未发现明显失衡；
4. 相同长脚本通过 daemon 写入 `/tmp/vb_eval_*.il` 后 load 报 line 7，疑似 daemon 侧对较长/多行 SKILL 的加载兼容问题，需中层/底层确认。

## 5. 建议处理

- 对照 `dump_read.il` 第 7 行附近，确认 daemon load 失败的精确原因；
- 确认 daemon 对 `setof` / `foreach` / 多行脚本 / `%L` 格式的支持情况；
- 上层侧暂不修改，待定位结果反馈后配合调整生成的 SKILL 文本。

## 6. 影响

- `virtuoso.schematic.read` 真机验证阻塞；
- `write` / `check_and_save` 未在真机执行，等待本问题闭环后验证。

## 7. 底层/中层复核补充（2026-09-18）

### 7.1 `load` 失败的根因在上层生成的 SKILL 文本

对 `test/tb/artifacts/dump_read.il` 做静态复核后，确认该文件本身不是合法、
平衡的 SKILL：

- 括号配对扫描最终多出一个未闭合的 `(`；
- 第 15–16 行、第 18–19 行在 SKILL 字符串字面量中包含了**真实换行**，
  而不是 SKILL 所需的 `\n` 两字符转义；
- 对应生成代码位于 `src/pyapi/packages/schematic.py` 的 `_read_skill()`，
  尤其是 `PINS`/`PIN|...` 片段中的 Python `\n` 转义（约第 305、310、317 行）。

将该脚本修正为合法转义后，通过当前 daemon 的“多行 SKILL 临时文件 + `load`”
路径执行时不再出现 load 语法错误；在当前缺少 `rfLib/LNA_PB` 的环境下，
只返回正常的 `dbOpenCellViewByType` 不存在 warning，而不是 reader/load 错误。

因此本 BUG 的直接责任不在 daemon 的通用 `load` 包装，而在上层业务包生成的
SKILL 文本。`src/pyapi/**` 不在本次中层/底层修改范围内，未作改动。

### 7.2 已修复的独立问题：daemon 临时求值文件逃逸到 `/tmp`

复核同时确认 daemon 原先使用 `tempfile.mkstemp()` 且未传 `dir=`，因此多行
SKILL 临时文件会落到系统 `/tmp`，与“使用注册表提供的 role 工作路径”的部署
意图不符。本次已在底层/部署侧修复：

- `virtuoso_setup.il` 部署时注入 `RBTempDir`（`role.daemon.root`）和
  `RBDLogPath`（`role.daemon.root/status/daemon.log`）；
- `ramic_bridge.il` 将 `RBTempDir` 传给 daemon 进程；
- `ramic_bridge_daemon_3.py` / `ramic_bridge_daemon_27.py` 使用配置目录
  创建临时 `.il`；未配置时回退到 daemon 脚本所在目录，不再使用 `/tmp`。

真机验证命令执行后，临时文件实际出现在：

```text
/home/Gent/.virtuoso-bridge/vblog/vb_eval_<id>.il
```

`/tmp/vb_eval_*.il` 无残留。
