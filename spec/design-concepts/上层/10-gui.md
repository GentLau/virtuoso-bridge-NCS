# 上层业务包：gui

> 版本：Draft v2
> 日期：2026-09-22
> 状态：Draft（待纳入 README 治理）
> Supersedes：Draft v1（display 改由 query 读取、顶层窗口过滤、截图机制与环境约定）
> 定位：业务包/业务操作一般契约见[1-上层.md](1-上层.md)；五业务接口见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)。

## 1. 业务操作

窗口处理面向“卡住弹窗的恢复”：唯一清单入口是 X11 顶层窗口列表，动作只接受显式 `window_id`。

### 1.1 读操作（不改变业务服务器状态）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| list_windows | 返回 X11 **顶层**窗口列表（含分类、suggested_action） | `query` 读 `gui.display` → `export DISPLAY` → `xprop _NET_CLIENT_LIST`（无 WM 退 root 直接子窗口）→ `xwininfo -root -tree` → 去重/分类 | Q+G |
| screenshot | 截取任意 X11 窗口或整个显示并取回：`target∈{ciw, window_id, display}` | `query` 读 `gui.display` → `export DISPLAY` → `XGetImage(root/窗口)` → PPM → 下载 | Q+G+D |

### 1.2 写操作（改变业务服务器状态）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| send_key | 对指定窗口注入按键：`key∈{enter, escape}` | 注入 XTest 按键 → 校验 still_mapped | G |
| auto_dismiss | 自动发现 modal/dialog 并逐个恢复 | 清单 → 分类 → 逐个 send_key → 逐窗口证据 | G |

接口简写：Q=query、S=execute_skill、C=run_command、U=upload_file、D=download_file、G=run_gui_command、Sp=run_spectre_command。

## 2. 约定

- 唯一清单入口：`list_windows` 只列 X11 顶层窗口，不再提供 SKILL 会话内清单；
- `list_windows` 只返回 root 的直接子窗口（缩进最浅层）并按 `window_id` 去重，
  嵌套子窗口与匿名子窗口不返回；
- 动作必须带显式 `window_id`，不存在“当前/最近窗口”隐式目标；
- 按键白名单只含 `enter` / `escape`，不做任意按键与坐标点击；
- 每次动作后校验 `still_mapped`，返回确定证据；
- `auto_dismiss` 只处理分类为 dialog 的窗口，设次数上限并保留逐窗口证据；
- `screenshot` 输出二进制 PPM（P6），`target=display` 抓当前 DISPLAY 的 root
  （即整个虚拟屏）；远端存该 token 的 gui role root `screenshots/`，
  本地存调用方给的 `output_path`。

### 2.1 DISPLAY 解析与 headless 环境

- `DISPLAY` 由上层通过只读查询 `middle.query(token)` 读取该 token 的
  `roles.gui.display`，再由本包自行拼 `export DISPLAY=<display>; <cmd>`；
  中层 GUI 一次性命令**不注入** DISPLAY；
- `roles.gui.display` 未配置时上层直接业务失败（`gui display is not configured`），
  不做 /proc 猜测或 :0 兜底；
- 显示可以是无头虚拟屏（如 `Xvfb :99`）或真实桌面（如 `:11`），本包不关心；
- 依赖 GUI 主机有 `xwininfo`、`python3`、`libX11.so.6`、`libXtst.so.6`。

### 2.2 与领域包 screenshot 的关系

本包 `screenshot` 是 **X11 像素级抓取**（任意窗口/整个显示，PPM），面向查看与诊断；
schematic / symbol / layout / maestro 的 `screenshot` 走 SKILL 的
`hiWindowSaveImage`（PNG，按 cellView 定位窗口）。两者是两套机制，
领域包截图失败**不回退**到本包 X11 抓取（见各包 spec）。

## 3. 不在本包

- bootstrap（首次 CIW 载入 setup.il）——删除；
- focused_snapshot（聚焦窗口的领域数据）——移出，归 maestro 包的 read_focused。
