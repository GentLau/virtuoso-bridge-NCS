from __future__ import annotations

from virtuoso_bridge.virtuoso.maestro.reader.snapshot import (
    _DEFAULT_NETLIST_FILES,
    _per_point_list,
)


def test_snapshot_netlist_whitelist_keeps_expr_outputs_json() -> None:
    assert "exprOutputs.json" in _DEFAULT_NETLIST_FILES
    assert "exprOutputs.json" in _per_point_list("netlist", _DEFAULT_NETLIST_FILES)
