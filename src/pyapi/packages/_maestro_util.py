"""Internal helpers for the ``maestro`` business package.

This module is deliberately transport-free and side-effect-free: it only
parses SKILL/CSV/OCEAN text and builds small SKILL literal fragments.  The
business package owns all middle-interface calls.
"""
from __future__ import annotations

import csv
import math
import re
from typing import Any


# ---------------------------------------------------------------------------
# SKILL string / literal helpers
# ---------------------------------------------------------------------------

from pyapi.packages.basic import (
    parse_sexpr,
    q,
    tokenize_top_level,
)


def unquote(raw: str) -> str:
    """Best-effort removal of one pair of SKILL string quotes."""
    text = (raw or "").strip()
    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    return text.replace('\\"', '"').replace("\\\\", "\\")


def decode_skill_text(raw: str) -> str:
    """Decode the escaped ``\\n``/``\\t`` sequences a daemon result carries."""
    return unquote(raw).replace("\\n", "\n").replace("\\t", "\t")


def parse_bool(raw: Any) -> bool | None:
    """Map a SKILL ``t``/``nil`` atom to Python bool, else ``None``."""
    if isinstance(raw, bool):
        return raw
    text = str(raw or "").strip().strip('"').lower()
    if text == "t":
        return True
    if text == "nil":
        return False
    return None


def skill_value(value: Any) -> str:
    """Serialize a Python value to a SKILL literal."""
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "t" if value else "nil"
    if isinstance(value, (int, float)):
        return f"{value:g}" if isinstance(value, float) else str(value)
    if isinstance(value, str):
        return q(value)
    if isinstance(value, dict):
        return "(" + " ".join(
            f"({skill_value(k)} {skill_value(v)})" for k, v in value.items()
        ) + ")"
    if isinstance(value, (list, tuple)):
        return "(" + " ".join(skill_value(item) for item in value) + ")"
    raise TypeError(
        f"cannot serialize {type(value).__name__} as a SKILL literal")


def skill_alist(value: Any, *, name: str = "options") -> str | None:
    """Build a quoted SKILL assoc-list fragment (without the backquote)."""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        return text
    if isinstance(value, dict):
        items = [(str(k), v) for k, v in value.items()]
    elif isinstance(value, (list, tuple)):
        items = []
        for index, item in enumerate(value):
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                raise ValueError(f"{name}[{index}] must be a [name, value] pair")
            items.append((str(item[0]), item[1]))
    else:
        raise ValueError(f"{name} must be an alist string, mapping, or list of pairs")
    return "(" + " ".join(f"({q(k)} {skill_value(v)})" for k, v in items) + ")"


# ---------------------------------------------------------------------------
# Monte Carlo run options
# ---------------------------------------------------------------------------

MC_RUN_MODE = "Monte Carlo Sampling"
MC_RUN_OPTIONS: tuple[str, ...] = (
    "mcmethod",
    "mcnumpoints",
    "mcnumbins",
    "samplingmode",
    "montecarloseed",
    "mcstartingrunnumber",
    "dutsummary",
    "ignoreflag",
    "mcreferencepoint",
    "donominal",
    "saveprocess",
    "savemismatch",
    "saveallplots",
    "mcStopEarly",
    "mcStopMethod",
    "mcYieldTarget",
    "mcYieldAlphaLimit",
)

_MC_ENUMS: dict[str, frozenset[str]] = {
    # Live-verified aliases: ADE accepts both the maeSKILLref spelling
    # (process) and the OCEAN XL spelling (global).
    "mcmethod": frozenset({"process", "mismatch", "all", "global"}),
    "samplingmode": frozenset({"random", "standard", "orthogonal", "lhs", "lds"}),
}
_MC_BOOL_FLAGS = frozenset({
    "ignoreflag",
    "mcreferencepoint",
    "donominal",
    "saveprocess",
    "savemismatch",
    "saveallplots",
})
_MC_POSITIVE_INTS = frozenset({"mcnumpoints", "mcstartingrunnumber"})
_MC_NONNEG_INTS = frozenset({"mcnumbins", "montecarloseed"})


def _as_int(value: Any, *, name: str, minimum: int | None = None) -> int:
    if isinstance(value, bool):
        raise ValueError(f"run option {name} must be an integer")
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
        number = int(value.strip())
    else:
        raise ValueError(f"run option {name} must be an integer")
    if minimum is not None and number < minimum:
        raise ValueError(f"run option {name} must be >= {minimum}")
    return number


def _as_flag01(value: Any, *, name: str) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int) and value in (0, 1):
        return str(value)
    text = str(value).strip().lower()
    if text in ("1", "t", "true", "yes", "on"):
        return "1"
    if text in ("0", "nil", "false", "no", "off"):
        return "0"
    raise ValueError(f"run option {name} must be a boolean (0/1)")


def _as_switch(value: Any, *, name: str) -> str:
    if isinstance(value, bool):
        return "t" if value else "nil"
    if isinstance(value, int) and value in (0, 1):
        return "t" if value else "nil"
    text = str(value).strip().lower()
    if text in ("1", "t", "true", "yes", "on"):
        return "t"
    if text in ("0", "nil", "false", "no", "off"):
        return "nil"
    raise ValueError(f"run option {name} must be a boolean (t/nil)")


def _as_number(value: Any, *, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"run option {name} must be numeric")
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError as exc:
            raise ValueError(f"run option {name} must be numeric") from exc
    else:
        raise ValueError(f"run option {name} must be numeric")
    if not math.isfinite(number):
        raise ValueError(f"run option {name} must be finite")
    return number


def _format_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else format(value, ".15g")


def normalize_run_option(name: str, value: Any) -> str:
    """Validate one MC run option and return its ADE string representation.

    The write layer stores arbitrary strings, so typo/value errors otherwise
    surface only during simulation.  This is the package-level guard.
    `mcmethod` / `samplingmode` accept the spellings observed in both the
    ADE SKILL reference and the OCEAN XL reference; the remaining options
    use their documented or live-verified types.
    """
    if name not in MC_RUN_OPTIONS:
        raise ValueError(f"unsupported Monte Carlo run option: {name}")
    if name in _MC_ENUMS:
        text = str(value).strip().lower()
        allowed = _MC_ENUMS[name]
        if text not in allowed:
            raise ValueError(
                f"run option {name} must be one of {sorted(allowed)}"
            )
        return text
    if name in _MC_POSITIVE_INTS:
        return str(_as_int(value, name=name, minimum=1))
    if name in _MC_NONNEG_INTS:
        if name == "mcnumbins" and (
            value is None or (isinstance(value, str) and not value.strip())
        ):
            return ""
        return str(_as_int(value, name=name, minimum=0))
    if name in _MC_BOOL_FLAGS:
        return _as_flag01(value, name=name)
    if name == "mcStopEarly":
        return _as_switch(value, name=name)
    if name in ("dutsummary", "mcStopMethod"):
        if not isinstance(value, str):
            raise ValueError(f"run option {name} must be a string")
        return value.strip() if name == "mcStopMethod" else value
    if name == "mcYieldTarget":
        number = _as_number(value, name=name)
        if number <= 0:
            raise ValueError("run option mcYieldTarget must be > 0")
        return _format_number(number)
    if name == "mcYieldAlphaLimit":
        number = _as_number(value, name=name)
        if not 0 < number < 100:
            raise ValueError("run option mcYieldAlphaLimit must be in (0, 100)")
        return _format_number(number)
    raise ValueError(f"unsupported Monte Carlo run option: {name}")


def skill_string_list(values: list[str]) -> str:
    """Return a SKILL list of strings, e.g. ``("AC" "TRAN")``."""
    return "(" + " ".join(q(value) for value in values) + ")"


def pairs_to_dict(value: Any) -> dict[str, Any]:
    """Turn a parsed SKILL alist ``[[key, value], ...]`` into a dict."""
    result: dict[str, Any] = {}
    if not isinstance(value, list):
        return result
    for item in value:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            result[str(item[0])] = item[1]
    return result


def parse_skill_str_leaves(raw: str) -> list[str]:
    """Parse all string leaves of a SKILL list/atom text.

    Unlike ``basic.parse_skill_str_list``（只收双引号字符串字面量），本函数
    与 maestro 读回契约一致：列表里的符号原子也作为字符串叶子收集。
    """
    text = (raw or "").strip()
    if not text or text == "nil":
        return []
    values: list[str] = []
    for token in tokenize_top_level(
        text,
        include_groups=True,
        include_strings=True,
        include_atoms=False,
    ):
        values.extend(_collect_strings(parse_sexpr(token)))
    return values


def _collect_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(_collect_strings(item))
        return values
    return []


# Result/history parsing
# ---------------------------------------------------------------------------

_HISTORY_RDB_RE = re.compile(r"^(.+)\.rdb$")
_HISTORY_DIR_RE = re.compile(r"^(?:Interactive|MonteCarlo|ExplorerRun)\.\d+$")


def history_name_for_file(filename: str) -> str | None:
    """Return the history name a results-directory entry belongs to."""
    name = (filename or "").strip()
    if not name:
        return None
    if name.endswith(".msg.db"):
        return name[: -len(".msg.db")]
    if name.endswith(".log"):
        return name[:-4]
    match = _HISTORY_RDB_RE.match(name)
    if match:
        return match.group(1)
    if _HISTORY_DIR_RE.match(name):
        return name
    return None


def natural_sort_key(value: str) -> list[tuple[int, str]]:
    return [
        (int(token) if token.isdigit() else 0, token)
        for token in re.findall(r"\d+|\D+", value)
    ]


def natural_sort_histories(filenames: list[str]) -> list[str]:
    """Extract and naturally sort history names from a directory listing."""
    seen: set[str] = set()
    for name in filenames:
        history = history_name_for_file(name)
        if history is not None:
            seen.add(history)
    return sorted(seen, key=natural_sort_key)


def parse_detail_csv(text: str, *, history: str = "") -> dict[str, Any]:
    """Parse ``maeExportOutputView(?view "Detail")`` CSV text.

    Mirrors the old upper-layer parser: supports both the multi-point layout
    (``Point,Test,Output,...``) and the single-point layout where the Point
    column is absent.
    """
    points: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    tests_seen: set[str] = set()
    no_point_detail = False

    reader = csv.reader(text.splitlines())
    for row in reader:
        if not row or not any(cell.strip() for cell in row):
            continue
        first = (row[0] or "").strip()
        header = [cell.strip() for cell in row[:6]]
        if header == ["Test", "Output", "Nominal", "Spec", "Weight", "Pass/Fail"]:
            no_point_detail = True
            continue
        if first.startswith("Parameters:"):
            parts = [first[len("Parameters:"):].strip()]
            parts += [cell.strip() for cell in row[1:] if cell.strip()]
            params_text = ",".join(part for part in parts if part)
            params: dict[str, str] = {}
            for item in params_text.split(","):
                item = item.strip()
                if "=" in item:
                    key, _, value = item.partition("=")
                    params[key.strip()] = value.strip()
            current = {"point": len(points) + 1, "parameters": params, "outputs": {}}
            points.append(current)
            continue
        if first in ("", "Point", "Test"):
            if first == "Point":
                no_point_detail = False
            continue
        if not first.isdigit():
            if not no_point_detail:
                continue
            columns = row + [""] * (6 - len(row))
            test_name, name, value, spec, weight, pass_fail = columns[:6]
            if not name.strip():
                continue
            if current is None:
                current = {"point": 1, "parameters": {}, "outputs": {}}
                points.append(current)
            if test_name:
                tests_seen.add(test_name.strip())
            current["outputs"][name.strip()] = {
                "value": value.strip(),
                "spec": spec.strip(),
                "weight": weight.strip(),
                "pass_fail": pass_fail.strip(),
            }
            continue
        if current is None:
            current = {"point": int(first), "parameters": {}, "outputs": {}}
            points.append(current)
        columns = row + [""] * (7 - len(row))
        _, test_name, name, value, spec, weight, pass_fail = columns[:7]
        if test_name:
            tests_seen.add(test_name.strip())
        if name.strip():
            current["outputs"][name.strip()] = {
                "value": value.strip(),
                "spec": spec.strip(),
                "weight": weight.strip(),
                "pass_fail": pass_fail.strip(),
            }

    flat_outputs: list[dict[str, Any]] = []
    for point in points:
        for name, info in point["outputs"].items():
            flat_outputs.append({
                "point": point["point"],
                "name": name,
                "value": info["value"],
                "spec_status": info["pass_fail"],
            })

    return {
        "history": history,
        "tests": sorted(tests_seen),
        "points": points,
        "outputs": flat_outputs,
    }


def _csv_cell(row: list[str], index: int | None) -> str:
    if index is None or index < 0 or index >= len(row):
        return ""
    return (row[index] or "").strip().lstrip("\ufeff")


def _number_or_none(value: Any) -> int | float | None:
    text = str(value or "").strip()
    if not text or text.lower() in ("nan", "inf", "+inf", "-inf"):
        return None
    if re.fullmatch(r"[+-]?\d+", text):
        return int(text)
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _target_number(value: str) -> float | None:
    match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", value)
    if not match:
        return None
    try:
        number = float(match.group(0))
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _yield_counts(value: str) -> tuple[float | None, int | None, int | None]:
    match = re.match(
        r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*%\s*"
        r"\(\s*(\d+)\s*/\s*(\d+)\s*\)",
        (value or "").strip(),
    )
    if not match:
        return None, None, None
    return float(match.group(1)), int(match.group(2)), int(match.group(3))


def parse_yield_csv(
    text: str,
    *,
    history: str = "",
    corners: list[str] | None = None,
) -> dict[str, Any]:
    """Parse ``maeExportOutputView(?view "Yield")`` CSV text.

    The Yield view is the stable way to obtain per-output statistics
    (Yield / Min / Target / Max / Mean / Std Dev / Cpk / Errors).  It is
    test-first, but includes a global ``Yield Estimate:`` line and mixes
    aggregate rows (``<name>(summary)``) with per-corner rows.  Corners are
    encoded as a name suffix, e.g. ``gain_db_vdd_high``; callers that know
    the setup's corner names can pass them via ``corners`` so the suffix is
    separated from the measurement name.
    """
    rows = [
        row for row in csv.reader((text or "").splitlines())
        if row and any((cell or "").strip() for cell in row)
    ]
    result: dict[str, Any] = {
        "history": history,
        "corners": [str(item) for item in (corners or [])],
        "tests": [],
        "overall": {},
        "outputs": [],
    }
    if not rows:
        return result

    header = [
        "Test", "Name", "Yield", "Min", "Target", "Max",
        "Mean", "Std Dev", "Cpk", "Errors",
    ]
    data_start = 0
    for index, row in enumerate(rows):
        cells = [(cell or "").strip().lstrip("\ufeff") for cell in row]
        if cells[:2] == ["Test", "Name"] and "Yield" in cells:
            header = cells
            data_start = index + 1
            break
    wanted = {
        "test": "test",
        "name": "name",
        "yield": "yield",
        "min": "min",
        "target": "target",
        "max": "max",
        "mean": "mean",
        "std dev": "std dev",
        "cpk": "cpk",
        "errors": "errors",
    }
    columns: dict[str, int] = {}
    for index, cell in enumerate(header):
        key = re.sub(r"\s+", " ", (cell or "").strip().lower())
        if key in wanted:
            columns[wanted[key]] = index
    # Fallback to the live-verified column order when a header is absent.
    for index, key in enumerate(
        ["test", "name", "yield", "min", "target", "max",
         "mean", "std dev", "cpk", "errors"]
    ):
        columns.setdefault(key, index)

    current_test = ""
    known_corners = sorted(
        (
            str(item).strip()
            for item in (corners or [])
            if str(item).strip() and str(item).strip() != "_default"
        ),
        key=len,
        reverse=True,
    )
    for row in rows[data_start:]:
        first = _csv_cell(row, columns.get("test"))
        raw_name = _csv_cell(row, columns.get("name"))
        if first.startswith("Yield Estimate:"):
            overall = result["overall"]
            overall["text"] = first
            match = re.search(
                r"Yield Estimate:\s*"
                r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*%\s*"
                r"\(\s*(\d+)\s*passed\s*/\s*(\d+)\s*pts\s*\)",
                first,
            )
            if match:
                overall["yield"] = float(match.group(1))
                overall["passed_points"] = int(match.group(2))
                overall["total_points"] = int(match.group(3))
                overall["error_points"] = max(
                    0, int(match.group(3)) - int(match.group(2)))
            confidence = re.search(
                r"Confidence Level:\s*(.*?)(?:\s+Filter:|$)", first,
            )
            if confidence:
                text_value = confidence.group(1).strip()
                overall["confidence_level"] = (
                    None if text_value.lower() in ("<not set>", "not set", "")
                    else text_value
                )
            filter_match = re.search(r"Filter:\s*(.*)$", first)
            if filter_match:
                text_value = filter_match.group(1).strip()
                overall["filter"] = (
                    None if text_value.lower() in ("<not set>", "not set", "")
                    else text_value
                )
            continue
        if first and not raw_name:
            current_test = first
            if first not in result["tests"]:
                result["tests"].append(first)
            continue
        if not raw_name:
            continue

        summary = raw_name.endswith("(summary)")
        name = raw_name[: -len("(summary)")] if summary else raw_name
        corner: str | None = None
        for candidate in known_corners:
            suffix = "_" + candidate
            if name.endswith(suffix) and len(name) > len(suffix):
                name = name[: -len(suffix)]
                corner = candidate
                break

        yield_text = _csv_cell(row, columns.get("yield"))
        yield_value, passed_points, total_points = _yield_counts(yield_text)
        target_text = _csv_cell(row, columns.get("target"))
        result["outputs"].append({
            "test": first or current_test or None,
            "name": name,
            "raw_name": raw_name,
            "summary": summary,
            "corner": corner,
            "yield": yield_value,
            "yield_text": yield_text,
            "passed_points": passed_points,
            "total_points": total_points,
            "min": _number_or_none(_csv_cell(row, columns.get("min"))),
            "target": target_text,
            "target_value": _target_number(target_text),
            "max": _number_or_none(_csv_cell(row, columns.get("max"))),
            "mean": _number_or_none(_csv_cell(row, columns.get("mean"))),
            "std_dev": _number_or_none(_csv_cell(row, columns.get("std dev"))),
            "cpk": _number_or_none(_csv_cell(row, columns.get("cpk"))),
            "errors": _number_or_none(_csv_cell(row, columns.get("errors"))),
        })
        test_name = first or current_test
        if test_name and test_name not in result["tests"]:
            result["tests"].append(test_name)
    return result


def parse_ocn_text(text: str) -> list[dict[str, Any]]:
    """Parse OCEAN ``ocnPrint`` whitespace text into numeric points."""
    points: list[dict[str, Any]] = []
    for line in (text or "").splitlines():
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        try:
            x = float(parts[0])
        except ValueError:
            continue
        try:
            if len(parts) >= 3:
                try:
                    real = float(parts[1])
                    imag = float(parts[2])
                    points.append({"x": x, "y": complex(real, imag)})
                    continue
                except ValueError:
                    pass
            points.append({"x": x, "y": float(parts[1])})
        except ValueError:
            continue
    return points


def parse_overall_yield(raw: str) -> dict[str, Any]:
    """Convert ``maeGetOverallYield`` output to a name/value dict."""
    parsed = parse_sexpr((raw or "").strip())
    result: dict[str, Any] = {}
    if isinstance(parsed, list):
        i = 0
        while i + 1 < len(parsed):
            key = parsed[i]
            if isinstance(key, str) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
                value = parsed[i + 1]
                if isinstance(value, str):
                    try:
                        value = int(value)
                    except ValueError:
                        try:
                            value = float(value)
                        except ValueError:
                            pass
                result[key] = value
                i += 2
            else:
                i += 1
    return result


__all__ = [
    "MC_RUN_MODE",
    "MC_RUN_OPTIONS",
    "decode_skill_text",
    "history_name_for_file",
    "natural_sort_histories",
    "natural_sort_key",
    "normalize_run_option",
    "pairs_to_dict",
    "parse_bool",
    "parse_detail_csv",
    "parse_ocn_text",
    "parse_overall_yield",
    "parse_yield_csv",
    "parse_skill_str_leaves",
    "skill_alist",
    "skill_string_list",
    "skill_value",
    "unquote",
]
