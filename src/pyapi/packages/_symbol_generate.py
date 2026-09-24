"""Native schematic-to-symbol generation helpers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal, cast

from pyapi.packages import basic

SymbolPinSort = Literal["alphanumeric", "geometric"]
SymbolGenerationAction = Literal["created", "replaced"]

_PIN_SORT_MODES = {"alphanumeric", "geometric"}


def _cleanup_close_skill(variable: str, failure: str) -> str:
    escaped_failure = basic.escape_skill_string(failure)
    return (
        f"when({variable} "
        f"vbCleanup = errset(dbClose({variable}) nil) "
        "unless(vbCleanup && car(vbCleanup) "
        f'vbCleanupFailures = cons("{escaped_failure}" vbCleanupFailures)) '
        f"{variable} = nil) "
    )


@dataclass(frozen=True)
class SymbolGenerationResult:
    """Verified source, destination, action, and terminal readback."""

    lib: str
    cell: str
    schematic_view: str
    symbol_view: str
    action: SymbolGenerationAction
    terminal_names: tuple[str, ...]
    pin_order: tuple[str, ...]


def generate_skill(
    lib: str,
    cell: str,
    *,
    schematic_view: str = "schematic",
    symbol_view: str = "symbol",
    sort_pins: SymbolPinSort | None = None,
    overwrite: bool = False,
) -> str:
    """Build SKILL for Cadence's native schematic-to-symbol pipeline."""
    _validate_sort_pins(sort_pins)
    if schematic_view == symbol_view:
        raise ValueError("schematic_view and symbol_view must differ")
    escaped_lib = basic.escape_skill_string(lib)
    escaped_cell = basic.escape_skill_string(cell)
    escaped_schematic_view = basic.escape_skill_string(schematic_view)
    escaped_symbol_view = basic.escape_skill_string(symbol_view)
    escaped_temp_view = basic.escape_skill_string(f"__vb_symbol_{uuid.uuid4().hex}")
    escaped_backup_view = basic.escape_skill_string(f"__vb_symbol_backup_{uuid.uuid4().hex}")
    overwrite_expr = "t" if overwrite else "nil"

    sort_capture = ""
    sort_setup = ""
    sort_finalize = ""
    sort_restore = ""
    if sort_pins is not None:
        escaped_sort = basic.escape_skill_string(sort_pins)
        sort_capture = 'vbOldSort = schGetEnv("ssgSortPins") '
        sort_setup = (
            f'vbSortChanged = schSetEnv("ssgSortPins" "{escaped_sort}") '
            'unless(vbSortChanged error("failed to set ssgSortPins")) '
        )
        sort_finalize = (
            "when(vbSortChanged "
            'vbCleanup = errset(schSetEnv("ssgSortPins" vbOldSort) nil) '
            'unless(vbCleanup && car(vbCleanup) error("failed to restore ssgSortPins")) '
            "vbSortChanged = nil) "
        )
        sort_restore = (
            "when(vbSortChanged "
            'vbCleanup = errset(schSetEnv("ssgSortPins" vbOldSort) nil) '
            "unless(vbCleanup && car(vbCleanup) "
            'vbCleanupFailures = cons("failed to restore ssgSortPins" '
            "vbCleanupFailures)) "
            "vbSortChanged = nil) "
        )

    return (
        "let((vbSourceCv vbTargetObj vbTempObj vbTempCv vbTargetCv vbPinList vbGenerated "
        "vbReplacing vbAction vbExpectedTerms vbActualTerms vbExpectedTerm vbOldSort "
        "vbExpectedOrder vbActualOrder vbFinalTerms vbFinalOrder vbBackupSourceCv "
        "vbOriginalTerms vbOriginalOrder vbBackupCv vbBackupObj vbSortChanged vbCleanup "
        "vbCleanupFailures vbBodyResult vbBodyAttempt vbBodyFailure vbResult vbBackupReady "
        "vbInstallAttempted vbInstalled vbCommitOk vbRollback vbRollbackSucceeded "
        "vbTargetOpenCv) "
        f'vbTargetObj = ddGetObj("{escaped_lib}" "{escaped_cell}" "{escaped_symbol_view}") '
        "vbReplacing = if(vbTargetObj t nil) "
        'vbAction = if(vbReplacing "replaced" "created") '
        "when(vbTargetObj ddReleaseObj(vbTargetObj) vbTargetObj = nil) "
        f'when(vbReplacing && !{overwrite_expr} error("target symbol exists")) '
        f'vbTempObj = ddGetObj("{escaped_lib}" "{escaped_cell}" "{escaped_temp_view}") '
        'when(vbTempObj unless(ddDeleteObj(vbTempObj) error("temporary symbol delete failed"))) '
        f'vbBackupObj = ddGetObj("{escaped_lib}" "{escaped_cell}" "{escaped_backup_view}") '
        'when(vbBackupObj unless(ddDeleteObj(vbBackupObj) error("symbol backup delete failed"))) '
        f"{sort_capture}"
        'vbBodyFailure = "symbol generation failed" '
        "vbBodyResult = unwindProtect(progn("
        "vbBodyAttempt = errset(progn("
        f'vbSourceCv = dbOpenCellViewByType("{escaped_lib}" "{escaped_cell}" '
        f'"{escaped_schematic_view}" "schematic" "r") '
        'unless(vbSourceCv error("source schematic not found")) '
        "vbExpectedTerms = mapcar(lambda((vbTerm) "
        'list(vbTerm~>name if(vbTerm~>direction vbTerm~>direction "inputOutput") '
        "if(vbTerm~>numBits vbTerm~>numBits 1))) vbSourceCv~>terminals) "
        "vbExpectedOrder = schGetPinOrder(vbSourceCv) "
        'unless(dbClose(vbSourceCv) error("source schematic close failed")) '
        "vbSourceCv = nil "
        f"{sort_setup}"
        f'vbPinList = schSchemToPinList("{escaped_lib}" "{escaped_cell}" "{escaped_schematic_view}") '
        'unless(vbPinList error("schematic to pin list failed")) '
        "vbGenerated = nil "
        "when(isCallable('schPinListToSymbolGen) "
        f"  vbGenerated = schPinListToSymbolGen(\"{escaped_lib}\" "
        f"\"{escaped_cell}\" \"{escaped_temp_view}\" vbPinList)) "
        "unless(vbGenerated "
        f"  vbGenerated = schPinListToSymbol(\"{escaped_lib}\" "
        f"\"{escaped_cell}\" \"{escaped_temp_view}\" vbPinList)) "
        'unless(vbGenerated error("symbol generation failed")) '
        f'vbTempCv = dbOpenCellViewByType("{escaped_lib}" "{escaped_cell}" '
        f'"{escaped_temp_view}" "schematicSymbol" "r") '
        'unless(vbTempCv error("temporary symbol open failed")) '
        "vbActualTerms = mapcar(lambda((vbTerm) "
        'list(vbTerm~>name if(vbTerm~>direction vbTerm~>direction "inputOutput") '
        "if(vbTerm~>numBits vbTerm~>numBits 1))) vbTempCv~>terminals) "
        "vbActualOrder = schGetPinOrder(vbTempCv) "
        "unless(length(vbExpectedTerms) == length(vbActualTerms) "
        'error("generated symbol terminals mismatch")) '
        "foreach(vbExpectedTerm vbExpectedTerms "
        "unless(member(vbExpectedTerm vbActualTerms) "
        'error("generated symbol terminals mismatch"))) '
        'unless(equal(vbExpectedOrder vbActualOrder) error("generated symbol pin order mismatch")) '
        f"{sort_finalize}"
        "unless(isCallable('dbCopyCellView) error(\"dbCopyCellView API unavailable\")) "
        f'vbTargetOpenCv = dbFindOpenCellViewByName("{escaped_lib}" "{escaped_cell}" '
        f'"{escaped_symbol_view}") '
        "when(vbTargetOpenCv && (vbTargetOpenCv~>mode == \"a\" || "
        "vbTargetOpenCv~>mode == \"w\") error(\"target symbol is open in edit mode\")) "
        "when(vbTargetOpenCv errset(dbClose(vbTargetOpenCv) nil)) "
        "vbTargetOpenCv = nil "
        "when(vbReplacing "
        f'vbBackupSourceCv = dbOpenCellViewByType("{escaped_lib}" "{escaped_cell}" '
        f'"{escaped_symbol_view}" "schematicSymbol" "r") '
        'unless(vbBackupSourceCv error("target symbol backup source open failed")) '
        "vbOriginalTerms = mapcar(lambda((vbTerm) "
        'list(vbTerm~>name if(vbTerm~>direction vbTerm~>direction "inputOutput") '
        "if(vbTerm~>numBits vbTerm~>numBits 1))) vbBackupSourceCv~>terminals) "
        "vbOriginalOrder = schGetPinOrder(vbBackupSourceCv) "
        f'vbBackupCv = dbCopyCellView(vbBackupSourceCv "{escaped_lib}" "{escaped_cell}" '
        f'"{escaped_backup_view}" nil nil nil) '
        'unless(vbBackupCv error("target symbol backup failed")) '
        "vbBackupReady = t "
        'unless(dbClose(vbBackupCv) error("target symbol backup close failed")) '
        "vbBackupCv = nil "
        'unless(dbClose(vbBackupSourceCv) error("target symbol backup source close failed")) '
        "vbBackupSourceCv = nil) "
        "vbInstallAttempted = t "
        f'vbTargetCv = dbCopyCellView(vbTempCv "{escaped_lib}" "{escaped_cell}" '
        f'"{escaped_symbol_view}" nil nil {overwrite_expr}) '
        'unless(vbTargetCv error("target symbol copy failed")) '
        "vbInstalled = t "
        "vbFinalTerms = mapcar(lambda((vbTerm) "
        'list(vbTerm~>name if(vbTerm~>direction vbTerm~>direction "inputOutput") '
        "if(vbTerm~>numBits vbTerm~>numBits 1))) vbTargetCv~>terminals) "
        "vbFinalOrder = schGetPinOrder(vbTargetCv) "
        "unless(length(vbExpectedTerms) == length(vbFinalTerms) "
        'error("installed symbol terminals mismatch")) '
        "foreach(vbExpectedTerm vbExpectedTerms "
        "unless(member(vbExpectedTerm vbFinalTerms) "
        'error("installed symbol terminals mismatch"))) '
        'unless(equal(vbExpectedOrder vbFinalOrder) error("installed symbol pin order mismatch")) '
        'unless(dbSave(vbTargetCv) error("installed symbol save failed")) '
        'unless(dbClose(vbTargetCv) error("installed symbol close failed")) '
        "vbTargetCv = nil "
        'unless(dbClose(vbTempCv) error("temporary symbol close failed")) '
        "vbTempCv = nil "
        'vbResult = list("generated" vbAction vbFinalTerms vbFinalOrder) '
        "vbCommitOk = t "
        "vbResult) nil) "
        'unless(vbBodyAttempt vbBodyFailure = sprintf(nil "%L" errset.errset)) '
        "vbBodyAttempt) "
        "progn("
        f"{sort_restore}"
        f'{_cleanup_close_skill("vbSourceCv", "source schematic cleanup close failed")}'
        f'{_cleanup_close_skill("vbTargetCv", "target symbol cleanup close failed")}'
        f'{_cleanup_close_skill("vbTempCv", "temporary symbol cleanup close failed")}'
        f'{_cleanup_close_skill("vbBackupSourceCv", "symbol backup source cleanup close failed")}'
        f'{_cleanup_close_skill("vbBackupCv", "symbol backup cleanup close failed")}'
        f'vbTempObj = ddGetObj("{escaped_lib}" "{escaped_cell}" "{escaped_temp_view}") '
        "when(vbTempObj "
        "vbCleanup = errset(ddDeleteObj(vbTempObj) nil) "
        "unless(vbCleanup && car(vbCleanup) "
        'vbCleanupFailures = cons("temporary symbol cleanup failed" vbCleanupFailures))) '
        "when(!vbCommitOk || vbCleanupFailures "
        "when(vbInstallAttempted "
        "if(vbReplacing "
        "then if(vbBackupReady "
        "then vbRollback = errset(progn("
        f'vbBackupCv = dbOpenCellViewByType("{escaped_lib}" "{escaped_cell}" '
        f'"{escaped_backup_view}" "schematicSymbol" "r") '
        'unless(vbBackupCv error("symbol backup open failed")) '
        f'vbTargetCv = dbCopyCellView(vbBackupCv "{escaped_lib}" "{escaped_cell}" '
        f'"{escaped_symbol_view}" nil nil t) '
        'unless(vbTargetCv error("target symbol rollback copy failed")) '
        "vbActualTerms = mapcar(lambda((vbTerm) "
        'list(vbTerm~>name if(vbTerm~>direction vbTerm~>direction "inputOutput") '
        "if(vbTerm~>numBits vbTerm~>numBits 1))) vbTargetCv~>terminals) "
        "vbActualOrder = schGetPinOrder(vbTargetCv) "
        "unless(length(vbOriginalTerms) == length(vbActualTerms) "
        'error("target symbol rollback terminals mismatch")) '
        "foreach(vbExpectedTerm vbOriginalTerms "
        "unless(member(vbExpectedTerm vbActualTerms) "
        'error("target symbol rollback terminals mismatch"))) '
        'unless(equal(vbOriginalOrder vbActualOrder) '
        'error("target symbol rollback pin order mismatch")) '
        'unless(dbSave(vbTargetCv) error("target symbol rollback save failed")) '
        'unless(dbClose(vbTargetCv) error("target symbol rollback close failed")) '
        "vbTargetCv = nil "
        'unless(dbClose(vbBackupCv) error("symbol backup close failed")) '
        "vbBackupCv = nil t) nil) "
        "if(vbRollback && car(vbRollback) "
        "then vbRollbackSucceeded = t "
        "else vbCleanupFailures = cons("
        f'sprintf(nil "target symbol rollback failed; backup retained as %s" '
        f'"{escaped_backup_view}") vbCleanupFailures)) '
        "else vbCleanupFailures = cons("
        '"target symbol rollback failed; backup unavailable" vbCleanupFailures)) '
        "else when(vbInstalled "
        f'vbTargetObj = ddGetObj("{escaped_lib}" "{escaped_cell}" "{escaped_symbol_view}") '
        "if(vbTargetObj "
        "then vbRollback = errset(ddDeleteObj(vbTargetObj) nil) "
        "if(vbRollback && car(vbRollback) "
        "then vbRollbackSucceeded = t "
        "else vbCleanupFailures = cons("
        '"created symbol rollback failed" vbCleanupFailures)) '
        "else vbRollbackSucceeded = t))))) "
        "when(vbBackupReady && "
        "(!vbInstallAttempted || (vbCommitOk && !vbCleanupFailures) || "
        "vbRollbackSucceeded) "
        f'vbBackupObj = ddGetObj("{escaped_lib}" "{escaped_cell}" "{escaped_backup_view}") '
        "when(vbBackupObj "
        "vbCleanup = errset(ddDeleteObj(vbBackupObj) nil) "
        "unless(vbCleanup && car(vbCleanup) "
        "vbCleanupFailures = cons("
        f'sprintf(nil "symbol backup cleanup failed; backup retained as %s" '
        f'"{escaped_backup_view}") vbCleanupFailures)))) '
        ") "
        ") "
        "if(vbBodyResult && vbCommitOk && !vbCleanupFailures "
        "then car(vbBodyResult) "
        "else list(\"failed\" if(vbBodyResult nil vbBodyFailure) "
        "reverse(vbCleanupFailures))))"
    )


def _validate_sort_pins(sort_pins: str | None) -> None:
    if sort_pins is not None and sort_pins not in _PIN_SORT_MODES:
        choices = ", ".join(sorted(_PIN_SORT_MODES))
        raise ValueError(f"sort_pins must be one of: {choices}")


def parse_generation_output(
    output: str,
) -> tuple[SymbolGenerationAction, dict[str, tuple[str, int]], tuple[str, ...]]:
    text = (output or "").strip()
    if not basic.is_single_complete_skill_list(text):
        raise RuntimeError(
            "symbol generation output must be a single complete SKILL list"
        )
    parsed = basic.parse_sexpr(text)
    if isinstance(parsed, list) and len(parsed) >= 3 and parsed[0] == "failed":
        body_failure = parsed[1]
        cleanup_failures = parsed[2]
        if cleanup_failures is None:
            cleanup_failures = []
        if not isinstance(cleanup_failures, list):
            raise RuntimeError(f"unexpected symbol generation failure output: {output}")
        cleanup_detail = ", ".join(str(item) for item in cleanup_failures)
        if body_failure is not None:
            detail = f"symbol generation failed: {body_failure}"
            if cleanup_detail:
                detail += f"; cleanup failed: {cleanup_detail}"
            raise RuntimeError(detail)
        if cleanup_detail:
            raise RuntimeError(f"symbol generation cleanup failed: {cleanup_detail}")
        raise RuntimeError(f"symbol generation failed without details: {output}")
    if not isinstance(parsed, list) or len(parsed) < 3 or parsed[0] != "generated":
        raise RuntimeError(f"unexpected symbol generation output: {output}")
    action = str(parsed[1])
    if action not in {"created", "replaced"}:
        raise RuntimeError(f"unexpected symbol generation action: {action}")
    raw_records = parsed[2]
    if raw_records is None:
        records = []
    elif isinstance(raw_records, list):
        records = raw_records
    else:
        raise RuntimeError(f"unexpected final terminal payload: {raw_records}")
    expected_terms: dict[str, tuple[str, int]] = {}
    for record in records:
        if not isinstance(record, list) or len(record) != 3:
            raise RuntimeError(f"unexpected final terminal record: {record}")
        name, direction, raw_width = record
        if not isinstance(name, str) or not isinstance(direction, str):
            raise RuntimeError(f"unexpected final terminal record: {record}")
        if name in expected_terms:
            raise RuntimeError(f"duplicate final terminal: {name}")
        try:
            width = int(raw_width)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"invalid final terminal width: {raw_width}") from exc
        if width < 1:
            raise RuntimeError(f"invalid final terminal width: {raw_width}")
        expected_terms[name] = (direction, width)
    if len(parsed) < 4:
        raise RuntimeError("unexpected final pin order payload: missing")
    raw_order = parsed[3]
    if raw_order is None:
        expected_order: tuple[str, ...] = ()
    elif isinstance(raw_order, list):
        expected_order = tuple(str(item) for item in raw_order)
    else:
        raise RuntimeError(f"unexpected final pin order payload: {raw_order}")
    return cast(SymbolGenerationAction, action), expected_terms, expected_order


__all__ = [
    "SymbolGenerationAction",
    "SymbolGenerationResult",
    "SymbolPinSort",
    "generate_skill",
    "parse_generation_output",
]
