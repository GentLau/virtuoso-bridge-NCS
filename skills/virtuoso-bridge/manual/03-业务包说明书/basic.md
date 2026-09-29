# basic —— 直连底层

`basic.*` 的六个操作分别直通底层的一种能力，不做任何业务编排。它们的用途是**兜底与诊断**：

- 现成业务操作覆盖不到的事情（任意 SKILL、任意 shell 命令）；
- 排查问题（`ls` 看文件、`command -v spectre` 看工具、`xdpyinfo` 看显示器）；
- 在调用方与目标机器之间搬文件。

结果统一放在 `data.result`（不是 `data.value`）里，原样返回底层结果。

## 1. `basic.skill.execute`

在 Virtuoso 的 CIW 里执行一段 SKILL。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `skill_code` | str | ✅ | — | 要执行的 SKILL 文本；多行建议用 `let(...)` / `progn(...)` 包起来 |

返回：`data.result` = `{"status","output","errors","warnings","execution_time","metadata","log"}`。

- `output` 是 SKILL 的**返回值**（字符串形式）；`log` 是这次调用产生的 CDS.log 增量。
- **结果只回到调用方，不会打印在 CIW 里**。要让用户在 CIW 里看到，SKILL 自己 `printf`。
- 超时一律视为"结果未知"，别直接重发写操作。

```json
{"operation":"basic.skill.execute","token":"TOKEN","skill_code":"1+2"}
{"operation":"basic.skill.execute","token":"TOKEN",
 "skill_code":"let((v) v=1+2 printf(\"1+2 = %d\\n\" v) v)"}
```

## 2. `basic.command.run`

在 **command 主机**上执行一条 shell 命令。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `cmd` | str | ✅ | — | shell 命令；每次都是新 shell，没有上一次的环境 |
| `parallel` | bool | — | `false` | `true` 时用独立通道执行，适合并发批量命令 |

返回：`data.result` = `{"returncode","stdout","stderr","kind"}`。

```json
{"operation":"basic.command.run","token":"TOKEN","cmd":"ls -l /home/user/work"}
{"operation":"basic.command.run","token":"TOKEN","cmd":"command -v spectre"}
```

注意：`returncode != 0` 时 `kind` 仍是 `command`（这是命令自己的退出码）；只有 `kind != command` 时
`returncode` 才表示桥的保留码（124 超时 / 255 传输失败等）。

## 3. `basic.file.upload`

把**本机**文件送到目标机器。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `local_path` | str | ✅ | — | 本机路径，如 `C:/work/tb.scs` |
| `remote_path` | str | ✅ | — | 目标机器路径，如 `/home/user/work/tb.scs`；相对路径按 file 角色根解析 |
| `recursive` | bool | — | `false` | `true` 时传整个目录树 |

返回：`data.result` = `{"returncode","stdout","stderr","kind"}`；成功时 `returncode=0`。

落盘是"临时文件 + SHA-256 校验 + 原子替换"；校验失败会报 `kind=checksum`，目标文件不变。

```json
{"operation":"basic.file.upload","token":"TOKEN","local_path":"C:/work/tb.scs","remote_path":"/home/user/work/tb.scs"}
```

## 4. `basic.file.download`

把目标机器上的文件取回**本机**。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `remote_path` | str | ✅ | — | 目标机器路径 |
| `local_path` | str | ✅ | — | 本机落点；父目录不存在会报路径错误 |
| `recursive` | bool | — | `false` | `true` 时取整个目录 |

```json
{"operation":"basic.file.download","token":"TOKEN","remote_path":"/home/user/work/out.raw","local_path":"C:/work/out.raw"}
```

## 5. `basic.gui.run`

在 **GUI 主机**上执行一次性命令（不经过 Virtuoso）。主要用于环境诊断。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `cmd` | str | ✅ | — | 如 `xdpyinfo`、`xwininfo -root -tree`、`echo $DISPLAY` |

返回：`data.result` = `{"returncode","stdout","stderr","kind"}`。

## 6. `basic.spectre.run`

在 **Spectre 主机**上执行一次性命令。用于确认工具与版本。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `cmd` | str | ✅ | — | 如 `spectre -W`、`spectre -v`、`command -v spectre` |

返回：`data.result` = `{"returncode","stdout","stderr","kind"}`。

## 常见问题

| 现象 | 原因 |
|---|---|
| 路径报 `VB-PATH-NOT-VISIBLE:` | 用了本机路径当远端路径，或目标目录不存在 |
| `kind=transport` | SSH/隧道没通（先看服务是否正常、目标机器是否可达） |
| SKILL 报错但 `ok=true` | `basic.skill.execute` 的 `ok` 来自 SKILL 执行状态；SKILL 内部可用 `errset` 吞掉错误，需要看 `output/errors` |
