# basic —— 直连底层

六个操作分别直通底层的一种能力，不做业务编排。用途是**兜底与诊断**：现成业务操作覆盖不到的事情（任意 SKILL、
任意 shell 命令）、排查问题（`ls`、`command -v spectre`、`xdpyinfo`）、在调用方与目标机器之间搬文件。

业务数据统一放在 `data.result`。

## 1. `basic.skill.execute` — 执行 SKILL

**功能**：在 Virtuoso 的 CIW 里执行一段 SKILL 文本。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `skill_code` | str | ✅ | — | SKILL 文本；多行建议用 `let(...)` / `progn(...)` 包起来 |

**返回**（`data.result`）

| 字段 | 类型 | 说明 |
|---|---|---|
| `status` | str | `success` / `error` |
| `output` | str | SKILL 的返回值（字符串形式） |
| `errors` / `warnings` | list[str] | 错误与警告文本 |
| `execution_time` | float | 执行耗时（秒，保留 3 位小数） |
| `CDSlog` | str | 本次调用产生的 CDS.log 增量 |

**示例**

```json
{"operation":"basic.skill.execute","token":"TOKEN","skill_code":"1+2"}
{"operation":"basic.skill.execute","token":"TOKEN","skill_code":"let((v) v=1+2 printf(\"1+2 = %d\\n\" v) v)"}
// 输出（data.result）
{"ok":true,"error":null,"result":{"status":"success","output":"3","errors":[],"warnings":[],
 "execution_time":0.012,"CDSlog":"1+2 = 3\n"}}
```

> 结果只回到调用方，**不会打印在 CIW 里**；要让用户看到，SKILL 自己 `printf`。超时视为"结果未知"。

## 2. `basic.command.run` — 执行 shell 命令

**功能**：在 command 主机上执行一条 shell 命令。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `cmd` | str | ✅ | — | shell 命令；每次都是新 shell，不保留上次的环境 |
| `parallel` | bool | — | `false` | `true` 用独立通道执行，适合并发批量命令 |

**返回**（`data.result`）

| 字段 | 类型 | 说明 |
|---|---|---|
| `returncode` | int | 命令退出码（只有 `kind=command` 时才是命令自己的） |
| `stdout` / `stderr` | str | 标准输出/错误 |
| `kind` | str | `command` / `timeout` / `transport` / `path` / `rejected` / `unknown-effect` 等 |

**示例**

```json
{"operation":"basic.command.run","token":"TOKEN","cmd":"ls -l /home/user/work"}
{"operation":"basic.command.run","token":"TOKEN","cmd":"command -v spectre"}
// 输出（data.result）
{"ok":true,"error":null,"result":{"returncode":0,"stdout":"/cadence/SPECTRE201/bin/spectre\n","stderr":"","kind":"command"}}
```

## 3. `basic.file.upload` — 上传文件

**功能**：把本机文件（或目录）送到目标机器。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `local_path` | str | ✅ | — | 本机路径，如 `C:/work/tb.scs` |
| `remote_path` | str | ✅ | — | 目标机器路径；相对路径按 file 角色根解析 |
| `recursive` | bool | — | `false` | `true` 时传整个目录树 |

**返回**（`data.result`）

| 字段 | 类型 | 说明 |
|---|---|---|
| `returncode` | int | 0 = 成功 |
| `stdout` / `stderr` | str | 输出（失败时看 `stderr`） |
| `kind` | str | `checksum` = 校验和不一致；`path` = 路径问题 |

**示例**

```json
// 输入
{"operation":"basic.file.upload","token":"TOKEN","local_path":"C:/work/tb.scs","remote_path":"/home/user/work/tb.scs"}
// 输出（data.result）
{"ok":true,"error":null,"result":{"returncode":0,"stdout":"","stderr":"","kind":"command"}}
```

## 4. `basic.file.download` — 下载文件

**功能**：把目标机器上的文件（或目录）取回本机。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `remote_path` | str | ✅ | — | 目标机器路径 |
| `local_path` | str | ✅ | — | 本机落点（父目录不存在会报路径错误） |
| `recursive` | bool | — | `false` | `true` 时取整个目录 |

**返回**：同 `basic.file.upload`。

**示例**

```json
// 输入
{"operation":"basic.file.download","token":"TOKEN","remote_path":"/home/user/work/out.raw","local_path":"C:/work/out.raw"}
// 输出（data.result）
{"ok":true,"error":null,"result":{"returncode":0,"stdout":"","stderr":"","kind":"command"}}
```

## 5. `basic.gui.run` — 在 GUI 主机执行命令

**功能**：在 GUI 主机上执行一次性命令（不经过 Virtuoso），主要用于环境诊断。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `cmd` | str | ✅ | — | 如 `xdpyinfo`、`xwininfo -root -tree`、`echo $DISPLAY` |

**返回**：同 `basic.command.run`。

**示例**

```json
// 输入
{"operation":"basic.gui.run","token":"TOKEN","cmd":"xdpyinfo"}
// 输出（data.result，节选）
{"ok":true,"error":null,"result":{"returncode":0,"stdout":"name of display:    :11\n...","stderr":"","kind":"command"}}
```

## 6. `basic.spectre.run` — 在 Spectre 主机执行命令

**功能**：在 Spectre 主机上执行一次性命令，用来确认工具与版本。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `cmd` | str | ✅ | — | 如 `spectre -W`、`spectre -v`、`command -v spectre` |

**返回**：同 `basic.command.run`。

**示例**

```json
// 输入
{"operation":"basic.spectre.run","token":"TOKEN","cmd":"spectre -W"}
// 输出（data.result，节选）
{"ok":true,"error":null,"result":{"returncode":0,"stdout":"spectre 21.1.0.isr4\n","stderr":"","kind":"command"}}
```

## 7. 常见问题

| 现象 | 原因 |
|---|---|
| 路径报 `VB-PATH-NOT-VISIBLE:` | 把本机路径当成了目标机器路径，或目标目录不存在 |
| `kind=transport` | SSH/隧道没通（先确认服务与目标机器可达） |
| SKILL 报错但 `ok=true` | `ok` 来自执行状态；SKILL 内部可能用 `errset` 吞了错误，需要看 `output`/`errors` |
