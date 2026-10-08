"""共享的 cellview 截图 SKILL 模板（P-130 收敛）。

schematic / symbol / layout 三包的截图模板此前各自实现、结构同型但已有
细微漂移（viewType 取值、not-found 文案、window_id 解析、zoom 坐标语法）。
这里收敛为一份实现，差异通过参数保留——各包生成的 SKILL 文本逐字不变：

* ``ensure_window_skill``：找/开窗口，返回 ``"opened"``/``"existing"``；
* ``close_window_skill``：三包同一实现；
* ``screenshot_skill``：``hiWindowSaveImage`` + 可选 zoom + 关闭自开窗口，
  返回 ``"saved"``/``"capture-failed"``。

gui 包的截图是另一机制（X11 ``XGetImage`` 直抓，不经过 SKILL），不在本
模块的收敛范围（P-130 明确豁免，见卡底结论）。
"""
from __future__ import annotations

from typing import Any

from pyapi.packages import basic


def ensure_window_skill(
    request: Any,
    *,
    view_type_expr: str,
    not_found_message: str,
) -> str:
    """SKILL：按 lib/cell/view 找窗口，找不到就 geOpen（只读）。"""
    return (
        "let((vbW vbOpened) vbOpened = nil "
        "vbW = car(setof(x hiGetWindowList() x~>cellView && "
        f"x~>cellView~>libName == {basic.q(request.library)} && "
        f"x~>cellView~>cellName == {basic.q(request.cell)} && "
        f"x~>cellView~>viewName == {basic.q(request.view)})) "
        "unless(vbW progn(vbW = geOpen(?lib "
        f"{basic.q(request.library)} ?cell {basic.q(request.cell)} "
        f"?view {basic.q(request.view)} ?viewType {view_type_expr} "
        '?mode "r") vbOpened = t)) '
        'if(vbW if(vbOpened "opened" "existing") '
        f'error("{not_found_message}")))'
    )


def close_window_skill(request: Any) -> str:
    """SKILL：关闭按 lib/cell/view 找到的窗口（没有则无操作）。"""
    return (
        "let((vbW) vbW = car(setof(x hiGetWindowList() x~>cellView && "
        f"x~>cellView~>libName == {basic.q(request.library)} && "
        f"x~>cellView~>cellName == {basic.q(request.cell)} && "
        f"x~>cellView~>viewName == {basic.q(request.view)})) "
        "when(vbW hiCloseWindow(vbW)) t)"
    )


def screenshot_skill(
    request: Any,
    remote_path: str,
    *,
    region: tuple[float, float, float, float] | None,
    not_found_message: str,
    view_type_expr: str,
    window_id_style: str = "loop",
    zoom_style: str = "pair",
) -> str:
    """SKILL：保存目标窗口为 PNG，返回 ``"saved"``/``"capture-failed"``。

    ``window_id_style``：``"window_call"``（schematic 的 ``window(N)``）或
    ``"loop"``（symbol/layout 遍历 ``windowNum``）；``zoom_style``：
    ``"pair"``（``x:y x:y``）或 ``"nested"``（``list(x y) list(x y)``，
    layout）。
    """
    if request.window_id is not None:
        if window_id_style == "window_call":
            target = f"window({int(request.window_id)})"
        else:
            target = (
                "let((vbW) foreach(w hiGetWindowList() "
                f"when(w~>windowNum == {int(request.window_id)} vbW = w)) vbW)"
            )
    else:
        target = (
            "let((vbTmp) vbTmp = car(setof(x hiGetWindowList() "
            "x~>cellView && "
            f"x~>cellView~>libName == {basic.q(request.library)} && "
            f"x~>cellView~>cellName == {basic.q(request.cell)} && "
            f"x~>cellView~>viewName == {basic.q(request.view)})) "
            "unless(vbTmp progn(vbTmp = geOpen(?lib "
            f"{basic.q(request.library)} ?cell {basic.q(request.cell)} "
            f"?view {basic.q(request.view)} ?viewType {view_type_expr} "
            '?mode "r") vbOpened = t)) vbTmp)'
        )
    zoom = ""
    if region is not None:
        x0, y0, x1, y1 = region
        if zoom_style == "nested":
            zoom = (
                f"hiZoomIn(vbW list(list({x0:g} {y0:g}) "
                f"list({x1:g} {y1:g}))) "
            )
        else:
            zoom = f"hiZoomIn(vbW list({x0:g}:{y0:g} {x1:g}:{y1:g})) "
    return (
        "let((vbW vbRc vbOpened) "
        "vbOpened = nil "
        f"vbW = {target} "
        f'unless(vbW error("{not_found_message}")) '
        f"{zoom}"
        f"vbRc = hiWindowSaveImage(?target vbW ?path {basic.q(remote_path)} "
        f'?format "png" ?toplevel {"t" if request.toplevel else "nil"} '
        f'?centralWidget {"t" if request.central_widget else "nil"}) '
        f'unless({"t" if request.leave_open else "nil"} '
        "when(vbOpened hiCloseWindow(vbW))) "
        'if(vbRc "saved" "capture-failed"))'
    )
