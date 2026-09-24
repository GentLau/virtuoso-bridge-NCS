"""Internal helpers for the ``maestro`` business package.

This module is deliberately transport-free and side-effect-free: it only
parses SKILL/CSV/OCEAN text and builds small SKILL literal fragments.  The
business package owns all middle-interface calls.
"""
from __future__ import annotations

import csv
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
    "decode_skill_text",
    "history_name_for_file",
    "natural_sort_histories",
    "natural_sort_key",
    "pairs_to_dict",
    "parse_bool",
    "parse_detail_csv",
    "parse_ocn_text",
    "parse_overall_yield",
    "parse_skill_str_leaves",
    "skill_alist",
    "skill_string_list",
    "skill_value",
    "unquote",
]
