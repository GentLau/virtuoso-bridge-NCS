"""`calibre.lvs` 源网表参数合同（C07）：spec 已收口为 `source` 口径，实现未跟。

spec `spec/design-concepts/上层/12-calibre.md`（commit `6b1b855`，2026-09-29）把
独立操作 `calibre.export_cdl` 折进 `calibre.lvs` 的 `source` 参数：

* §4.3 参数表：`source`（`kind=cdl|schematic`）、`emit_cdl`、`cds_lib`；
* §4.3.2：`source.kind=schematic` 走官方 auCdl 现产（run dir 内完成，作为本次 LVS 源）；
* §8 验收：`source.kind=cdl` 直接用已有 CDL；`source.kind=schematic` 现产 + `emit_cdl`。

实现已折叠到 `RunRequest`/`calibre.lvs`；本文件钉住请求侧合同，真机闭环见
`test/live/packages/calibre_e2e_tests.py`。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from pyapi.packages import calibre as CAL  # noqa: E402


def _request(**extra):
    return CAL.RunRequest(token="t", deck="/remote/deck", **extra)


def test_lvs_accepts_source_kind_cdl():
    """spec §8「LVS 源」：source.kind=cdl 直接用已有 CDL。"""
    _request(source={"kind": "cdl", "path": "/remote/x.cdl"})


def test_lvs_accepts_source_kind_schematic_with_options():
    """spec §8「LVS 闭环」：source.kind=schematic 现产 + emit_cdl=true 返回 cdl_path。"""
    _request(
        source={"kind": "schematic", "library": "L", "cell": "C", "view": "schematic"},
        emit_cdl=True,
        cds_lib="/remote/cds.lib",
    )


def test_lvs_rejects_source_with_cdl_and_runset():
    import pytest

    with pytest.raises(ValueError):
        _request(cdl="/remote/x.cdl", source={"kind": "cdl", "path": "/remote/y.cdl"})
    with pytest.raises(ValueError):
        _request(runset="/remote/x.lvs", source={"kind": "cdl", "path": "/remote/y.cdl"})


def test_lvs_rejects_schematic_options_on_cdl_source():
    import pytest

    with pytest.raises(ValueError):
        _request(source={"kind": "cdl", "path": "/remote/x.cdl"}, emit_cdl=True)
    with pytest.raises(ValueError):
        _request(source={"kind": "cdl", "path": "/remote/x.cdl"}, cds_lib="/remote/cds.lib")
