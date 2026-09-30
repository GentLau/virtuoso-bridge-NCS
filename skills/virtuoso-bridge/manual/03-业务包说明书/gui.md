# gui —— 窗口、按键、截屏

处理人机界面层面的问题：看有哪些窗口、往窗口发按键、自动关掉挡路的对话框、截屏。

## 1. `virtuoso.gui.list_windows` — 列窗口

**功能**：列出当前 Virtuoso 相关窗口，拿到 `window_id` 供后续发按键使用。

**输入参数**：除公共参数（`token`/`timeout`/`step_details`）外无。

**返回**（`data.windows`）

| 字段 | 类型 | 说明 |
|---|---|---|
| `windows` | list | 每个窗口的 id、标题、进程等信息 |

**示例**

```json
// 输入
{"operation":"virtuoso.gui.list_windows","token":"TOKEN"}
// 输出（data 内容）
{"ok":true,"error":null,"windows":[{"window_id":"0x2200008","title":"Virtuoso Schematic Editor","mapped":true}]}
```

## 2. `virtuoso.gui.send_key` — 发按键

**功能**：往指定窗口发一个按键（常用于确认/关闭对话框）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `window_id` | str | ✅ | — | 来自 `list_windows` |
| `key` | str | — | `enter` | 键名，如 `enter` / `escape` |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `still_mapped` | bool | 发键后窗口是否仍然存在 |

**示例**

```json
// 输入
{"operation":"virtuoso.gui.send_key","token":"TOKEN","window_id":"0x2200008","key":"enter"}
// 输出（data 内容）
{"ok":true,"error":null,"still_mapped":true}
```

## 3. `virtuoso.gui.auto_dismiss` — 自动关弹窗

**功能**：把挡路的模态对话框自动关掉，让后续操作能继续。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `max_attempts` | int | — | `2` | 最多尝试关几次 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `dismissed` | list | 本次关掉的窗口 |

**示例**

```json
// 输入
{"operation":"virtuoso.gui.auto_dismiss","token":"TOKEN"}
// 输出（data 内容）
{"ok":true,"error":null,"dismissed":[{"window_id":"0x2200012","title":"Warning"}]}
```

## 4. `virtuoso.gui.screenshot` — 截屏

**功能**：把 CIW、整个桌面或指定窗口截下来，并送回本机。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `output_path` | str | ✅ | — | 本机落点 |
| `target` | str | — | `ciw` | `ciw` / `display`（整屏）/ `0x...` 窗口号 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `local_path` | str | 实际落盘路径 |

**示例**

```json
// 输入
{"operation":"virtuoso.gui.screenshot","token":"TOKEN","output_path":"C:/work/ciw.ppm","target":"ciw"}
// 输出（data 内容）
{"ok":true,"error":null,"local_path":"C:/work/ciw.ppm"}
```

## 5. 使用建议

- 截图前确认 GUI 主机的 `DISPLAY` 配置正确，否则会黑图或失败。
- 旧的 `window_id` 可能失效，发按键前重新 `list_windows`。
- 有弹窗时先 `auto_dismiss`，再发业务请求。
