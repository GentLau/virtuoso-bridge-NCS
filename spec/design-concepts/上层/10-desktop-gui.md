# 上层业务包：desktop_gui

> 版本：Draft v1（终版）
> 日期：2026-09-17
> 状态：Draft（待纳入 README 治理）
> Supersedes：无
> 定位：业务包/业务操作一般契约见[1-上层.md](1-上层.md)；五业务接口见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)。

## 1. 业务操作

窗口处理面向“卡住弹窗的恢复”：唯一清单入口是 X11 顶层窗口列表，动作只接受显式 `window_id`。

### 1.1 读操作（不改变业务服务器状态）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| list_windows | 返回 X11 顶层窗口列表（含分类、suggested_action） | xwininfo 树 → 解析/去重/分类 | G |
| screenshot | 截图并取回：`target∈{ciw, window_id, display}` | 解析 DISPLAY → 截图 → 下载 | G+D |

### 1.2 写操作（改变业务服务器状态）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| send_key | 对指定窗口注入按键：`key∈{enter, escape}` | 注入 XTest 按键 → 校验 still_mapped | G |
| auto_dismiss | 自动发现 modal/dialog 并逐个恢复 | 清单 → 分类 → 逐个 send_key → 逐窗口证据 | G |

接口简写：S=execute_skill、C=run_command、U=upload_file、D=download_file、G=run_gui_command、Sp=run_spectre_command。

## 2. 约定

- 唯一清单入口：`list_windows` 只列 X11 顶层窗口，不再提供 SKILL 会话内清单；
- 动作必须带显式 `window_id`，不存在“当前/最近窗口”隐式目标；
- 按键白名单只含 `enter` / `escape`，不做任意按键与坐标点击；
- 每次动作后校验 `still_mapped`，返回确定证据；
- `auto_dismiss` 只处理分类为 modal/dialog 的窗口，设次数上限并保留逐窗口证据。

## 3. 不在本包

- bootstrap（首次 CIW 载入 setup.il）——删除；
- focused_snapshot（聚焦窗口的领域数据）——移出，归 maestro 包的 read_focused。