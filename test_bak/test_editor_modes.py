from __future__ import annotations

import pytest

from virtuoso_bridge.virtuoso.layout import LayoutOps
from virtuoso_bridge.virtuoso.schematic import SchematicOps
from virtuoso_bridge.virtuoso.symbol import SymbolOps


def _open_command(editor: object) -> str:
    entered = editor.__enter__()  # type: ignore[attr-defined]
    assert entered is editor
    return editor.commands[0]  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("ops_type", "view", "view_type"),
    [
        (SchematicOps, "schematic", "schematic"),
        (LayoutOps, "layout", "maskLayout"),
        (SymbolOps, "symbol", "schematicSymbol"),
    ],
)
def test_create_and_modify_make_overwrite_intent_explicit(
    ops_type: type[object],
    view: str,
    view_type: str,
) -> None:
    ops = ops_type(object())

    create_command = _open_command(ops.create("demoLib", "demoCell"))  # type: ignore[attr-defined]
    modify_command = _open_command(ops.modify("demoLib", "demoCell"))  # type: ignore[attr-defined]

    open_prefix = f'dbOpenCellViewByType("demoLib" "demoCell" "{view}" "{view_type}" '
    assert open_prefix + '"w")' in create_command
    assert open_prefix + '"a")' in modify_command


@pytest.mark.parametrize("ops_type", [SchematicOps, LayoutOps, SymbolOps])
def test_legacy_edit_is_deprecated_and_defaults_to_safe_append(ops_type: type[object]) -> None:
    ops = ops_type(object())

    with pytest.deprecated_call(match=r"use create\(\) or modify\(\) explicitly"):
        editor = ops.edit("demoLib", "demoCell")  # type: ignore[attr-defined]

    assert editor.mode == "a"  # type: ignore[attr-defined]
