# gui —— 窗口、按键、截屏

处理"人机界面"层面的问题：看看有哪些窗口、往窗口里发按键、自动关掉挡路的对话框、截屏。

## 1. `virtuoso.gui.list_windows` — 列窗口

除 `token`/`timeout` 外无参数。

返回 `data.windows`：窗口列表（含 `window_id`、标题、所属进程等）。后面发按键要用这里的 `window_id`。

## 2. `virtuoso.gui.send_key` — 发按键

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `window_id` | str | ✅ | — | 目标窗口，来自 `list_windows` |
| `key` | str | — | `enter` | 键名，如 `enter` / `escape` / `Return` |

返回 `data.still_mapped`：发键之后窗口是否仍然存在。

## 3. `virtuoso.gui.auto_dismiss` — 自动关弹窗

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `max_attempts` | int | — | `2` | 最多尝试关几次 |

返回 `data.dismissed`：本次关掉了哪些窗口。

> 用途：CIW 卡在提示框时，后续操作都会失败。先跑一次 `auto_dismiss` 再继续。

## 4. `virtuoso.gui.screenshot` — 截屏

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `output_path` | str | ✅ | — | 截图在本机的落点 |
| `target` | str | — | `ciw` | `ciw`（只截 CIW）、`display`（整个桌面）、或 `0x...` 窗口号 |

返回 `data.local_path`：实际落盘路径。

```json
{"operation":"virtuoso.gui.screenshot","token":"TOKEN","output_path":"C:/work/screen.ppm","target":"ciw"}
```

## 5. 使用建议

- 截图前确认 GUI 主机上的 `DISPLAY` 配置正确（配置不对会截出黑图或直接失败）。
- 先 `list_windows` 拿最新 `window_id`，旧的 id 可能已经失效。
- 弹窗处理完（`auto_dismiss`）再发业务请求，能省掉大量莫名其妙的失败。
