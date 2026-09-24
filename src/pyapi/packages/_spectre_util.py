"""Pure-Python helpers for the ``spectre`` business package.

This module deliberately has no middle/transport imports.  It owns the PSF
ASCII parser, raw-directory/sweep layout discovery, and the small metric
calculator used by ``spectre.read_results`` and ``spectre.measure``.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any


_SECTION_MARKERS = {"HEADER", "TYPE", "SWEEP", "TRACE", "VALUE", "END"}


# ---------------------------------------------------------------------------
# JSON-safe value conversion
# ---------------------------------------------------------------------------

def psf_external(value: Any) -> Any:
    """Convert parser values to the JSON-safe shape used by the API.

    A complex vector becomes ``{"re": [...], "im": [...]}`` and a complex
    scalar becomes ``{"re": ..., "im": ...}``.  Real PSF vectors stay lists of
    numbers, so transient consumers keep the historical ``data["signal"]``
    shape.

    对外边界（spec 7-spectre §9）：**非有限值一律 `null`**——缺失点（哨兵 `None`）
    与任何 NaN/±Inf 都在这里收敛成 JSON-safe，内部语义不变。
    """
    if isinstance(value, list):
        has_complex = any(isinstance(item, complex) for item in value)
        all_numeric = all(
            item is None
            or (
                not isinstance(item, bool)
                and isinstance(item, (int, float, complex))
            )
            for item in value
        )
        if has_complex and all_numeric:
            real: list[float | None] = []
            imag: list[float | None] = []
            for item in value:
                if item is None:
                    real.append(None)
                    imag.append(None)
                elif isinstance(item, complex):
                    real.append(_finite(item.real))
                    imag.append(_finite(item.imag))
                else:
                    real.append(_finite(float(item)))
                    imag.append(0.0)
            return {"re": real, "im": imag}
        return [psf_external(item) for item in value]
    if isinstance(value, complex):
        return {"re": _finite(value.real), "im": _finite(value.imag)}
    if isinstance(value, dict):
        return {str(key): psf_external(item) for key, item in value.items()}
    if isinstance(value, float):
        return _finite(value)
    if value is None or isinstance(value, (bool, int, str)):
        return value
    return str(value)


def _finite(value: float) -> float | None:
    """NaN/±Inf → ``None``（JSON-safe）；有限值原样返回。"""
    return value if math.isfinite(value) else None


# ---------------------------------------------------------------------------
# PSF ASCII parser
# ---------------------------------------------------------------------------

def _parse_header(content: str) -> dict[str, str]:
    header: dict[str, str] = {}
    in_header = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "HEADER":
            in_header = True
            continue
        if not in_header:
            continue
        if stripped in _SECTION_MARKERS:
            break
        match = re.match(r'"([^"]+)"\s+"([^"]*)"', stripped)
        if match:
            header[match.group(1)] = match.group(2)
            continue
        match = re.match(r'"([^"]+)"\s+(\S+)', stripped)
        if match:
            header[match.group(1)] = match.group(2)
    return header


def _section_lines(lines: list[str]) -> dict[str, int]:
    sections: dict[str, int] = {}
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped in _SECTION_MARKERS:
            sections[stripped] = index
    return sections


def _sweep_variable(lines: list[str], sections: dict[str, int], n: int) -> str:
    end = sections.get("TRACE", sections.get("VALUE", n))
    for line in lines[sections["SWEEP"] + 1 : end]:
        stripped = line.strip()
        if not stripped or stripped in ("TRACE", "VALUE", "END"):
            break
        match = re.match(r'"([^"]+)"', stripped)
        if match:
            return match.group(1)
    return ""


def _trace_mapping(
    lines: list[str], sections: dict[str, int], n: int
) -> tuple[list[str], dict[str, str]]:
    names: list[str] = []
    group_to_name: dict[str, str] = {}
    current_group: str | None = None
    end = sections.get("VALUE", n)
    for line in lines[sections["TRACE"] + 1 : end]:
        stripped = line.strip()
        if not stripped or stripped in ("VALUE", "END"):
            break
        group_match = re.match(r'"(\s*\d+)"\s+GROUP\s+\d+', stripped)
        if group_match:
            current_group = group_match.group(1)
            continue
        signal_match = re.match(r'"([^"]+)"\s+"[^"]*"', stripped)
        if signal_match:
            name = signal_match.group(1)
            names.append(name)
            if current_group is not None:
                group_to_name[current_group] = name
            current_group = None
            continue
        bare_match = re.match(r'"([^"]+)"', stripped)
        if bare_match:
            names.append(bare_match.group(1))
    return names, group_to_name


def _parse_swept_data(lines: list[str], sections: dict[str, int], n: int) -> dict[str, Any]:
    sweep_var = _sweep_variable(lines, sections, n)
    if not sweep_var:
        return {}
    trace_names, group_to_name = _trace_mapping(lines, sections, n)
    if "VALUE" not in sections:
        return {}

    value_start = sections["VALUE"] + 1
    value_end = sections.get("END", n)
    raw_entries: list[tuple[str | None, float | complex]] = []

    for line in lines[value_start:value_end]:
        stripped = line.strip()
        if not stripped or stripped == "END":
            break

        complex_match = re.match(
            r'"([^"]+)"\s+\(\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*\)', stripped
        )
        if complex_match:
            raw_key = complex_match.group(1)
            signal_name = group_to_name.get(raw_key, raw_key)
            try:
                value: float | complex = complex(
                    float(complex_match.group(2)), float(complex_match.group(3))
                )
            except ValueError:
                continue
            raw_entries.append((signal_name, value))
            continue

        scalar_match = re.match(r'"([^"]+)"\s+(\S+)', stripped)
        if not scalar_match:
            continue
        raw_key = scalar_match.group(1)
        try:
            scalar_value = float(scalar_match.group(2))
        except ValueError:
            continue
        if raw_key == sweep_var:
            raw_entries.append((None, scalar_value))
        else:
            signal_name = group_to_name.get(raw_key, raw_key)
            raw_entries.append((signal_name, scalar_value))

    time_values: list[float | complex] = []
    signal_state: dict[str, float | complex] = {}
    signal_series: dict[str, list[float | complex | None]] = {
        name: [] for name in trace_names
    }

    for key, value in raw_entries:
        if key is None:
            if time_values:
                for name in trace_names:
                    signal_series[name].append(signal_state.get(name))
            time_values.append(value)
        else:
            signal_state[key] = value

    if time_values:
        for name in trace_names:
            signal_series[name].append(signal_state.get(name))

    data: dict[str, Any] = {sweep_var: time_values}
    data.update(signal_series)
    return data


def _parse_struct_types(
    lines: list[str], start: int, end: int
) -> dict[str, list[str]]:
    structs: dict[str, list[str]] = {}
    current_type: str | None = None
    depth = 0
    for line in lines[start:end]:
        stripped = line.strip()
        if current_type is None:
            match = re.match(r'^"([^"]+)"\s+STRUCT\($', stripped)
            if match:
                current_type = match.group(1)
                structs[current_type] = []
                depth = 1
            continue
        member = re.match(
            r'^"([^"]+)"\s+[A-Z]+(?:\s+[A-Z]+)?(?:\s+PROP\()?$', stripped
        )
        if depth == 1 and member:
            structs[current_type].append(member.group(1))
        depth += stripped.count("(") - stripped.count(")")
        if depth <= 0:
            current_type = None
            depth = 0
    return structs


def _scalar(raw_value: str) -> Any:
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    try:
        return float(value)
    except ValueError:
        return value


def _parse_non_swept_data(
    lines: list[str], sections: dict[str, int], n: int
) -> dict[str, Any]:
    data: dict[str, Any] = {}
    type_start = sections.get("TYPE", 0) + 1
    value_end = sections.get("END", n)
    struct_fields = _parse_struct_types(lines, type_start, value_end)
    struct_depth = 0

    for index in range(sections["VALUE"] + 1, value_end):
        stripped = lines[index].strip()
        if not stripped or stripped == "END":
            break
        if struct_depth:
            struct_depth += stripped.count("(") - stripped.count(")")
            if struct_depth <= 0:
                struct_depth = 0
            continue

        struct_match = re.match(r'^"([^"]+)"\s+"([^"]+)"\s+\($', stripped)
        if struct_match and struct_match.group(2) in struct_fields:
            instance, type_name = struct_match.groups()
            values: list[Any] = []
            for value_line in lines[index + 1 : value_end]:
                line = value_line.strip()
                if line == ")" or line.startswith(") PROP("):
                    break
                if line:
                    values.append(_scalar(line))
            for field, value in zip(struct_fields[type_name], values):
                data[f"{instance}:{field}"] = value
            struct_depth = stripped.count("(") - stripped.count(")")
            continue

        typed_match = re.match(
            r'^"([^"]+)"\s+(?:"[^"]+"\s+)([-+0-9.eE]+)', stripped
        )
        if typed_match:
            try:
                data[typed_match.group(1)] = float(typed_match.group(2))
            except ValueError:
                pass
            continue

        number_match = re.match(r'^"([^"]+)"\s+([-+0-9.eE]+)', stripped)
        if number_match:
            try:
                data[number_match.group(1)] = float(number_match.group(2))
            except ValueError:
                pass
            continue

        legacy_match = re.match(r'^"([^"]+)"\s+(\S+)', stripped)
        if legacy_match:
            name, raw_value = legacy_match.groups()
            data[name] = _scalar(raw_value)
    return data


def parse_psf_file(path: Path) -> tuple[dict[str, str], dict[str, Any]]:
    """Parse one PSF ASCII file into ``(header, JSON-safe data)``."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"PSF file not found: {path}")
    content = path.read_text(encoding="utf-8", errors="replace")
    if not content.strip():
        raise ValueError(f"PSF ASCII file is empty: {path}")

    lines = content.splitlines()
    n = len(lines)
    sections = _section_lines(lines)
    if "VALUE" not in sections:
        raise ValueError(f"PSF ASCII file has no VALUE section: {path}")

    header = _parse_header(content)
    if "SWEEP" in sections:
        raw_data = _parse_swept_data(lines, sections, n)
    else:
        raw_data = _parse_non_swept_data(lines, sections, n)
    if not raw_data:
        raise ValueError(f"no PSF data parsed from: {path}")
    return header, psf_external(raw_data)


# ---------------------------------------------------------------------------
# Raw directory / sweep layout discovery
# ---------------------------------------------------------------------------

def _has_psf_files(path: Path) -> bool:
    return (
        any(path.glob("*.dc"))
        or any(path.glob("*.info"))
        or any(path.glob("*.tran*"))
        or any(path.glob("*.ac*"))
        or (path / "logFile").is_file()
    )


def _psf_scan_root(raw_dir: Path) -> Path:
    raw_dir = Path(raw_dir)
    if not raw_dir.is_dir():
        return raw_dir
    inner = raw_dir / raw_dir.name
    if inner.is_dir() and _has_psf_files(inner):
        return inner
    for child in sorted(raw_dir.iterdir(), key=lambda item: item.name):
        if not child.is_dir():
            continue
        if child.name.startswith("sw") and ".sweep" in child.name:
            continue
        if child.name == "psf" or child.name.endswith(".raw"):
            if _has_psf_files(child):
                return _psf_scan_root(child)
            continue
        if (
            _has_psf_files(child)
            and (
                any(child.glob("*.dc"))
                or any(child.glob("*.info"))
                or (child / "logFile").is_file()
            )
        ):
            return _psf_scan_root(child)
    return raw_dir


def _candidate(root: Path, names: tuple[str, ...], pattern: str) -> Path | None:
    for name in names:
        path = root / name
        if path.is_file():
            return path
    hits = sorted(root.glob(pattern))
    return hits[0] if hits else None


def _merge_file(
    data: dict[str, Any], files: list[str], root: Path, path: Path, prefix: str
) -> None:
    _, parsed = parse_psf_file(path)
    for key, value in parsed.items():
        data[f"{prefix}{key}"] = value
    files.append(str(path.relative_to(root)))


def parse_psf_directory(path: Path, analysis: str = "all") -> dict[str, Any]:
    """Parse one raw directory and merge the requested analysis families."""
    root = _psf_scan_root(path)
    data: dict[str, Any] = {}
    analyses: list[str] = []
    files: list[str] = []

    if analysis in ("all", "tran"):
        found = _candidate(
            root, ("tran.tran.tran", "tran.tran"), "*.tran.tran"
        )
        if found:
            _merge_file(data, files, root, found, "")
            analyses.append("tran")

    if analysis in ("all", "dc"):
        found = _candidate(root, ("dc.dc", "dcOp.dc", "spectre.dc"), "*.dc")
        if found:
            _merge_file(data, files, root, found, "dc_")
            analyses.append("dc")

    if analysis in ("all", "ac"):
        found = _candidate(root, ("ac.ac", "ac.ac.ac"), "*.ac.ac")
        if found is None:
            # spectre 按分析名落盘（默认 ac1 等），文件名为 <分析名>.ac
            found = _candidate(root, (), "*.ac")
        if found:
            _merge_file(data, files, root, found, "ac_")
            analyses.append("ac")

    if analysis in ("all", "info"):
        info_files = sorted(root.glob("*.info"))
        for info_file in info_files:
            prefix = info_file.stem.replace(".", "_") + "_"
            _merge_file(data, files, root, info_file, prefix)
        if info_files:
            analyses.append("info")

    if not analyses:
        raise ValueError(f"no PSF analysis found below {path} (analysis={analysis})")
    return {
        "data": data,
        "analyses": analyses,
        "files": sorted(set(files)),
    }


def _is_result_file(path: Path) -> bool:
    name = path.name
    return (
        name.endswith((".tran", ".dc", ".ac", ".info"))
        or ".tran." in name
        or ".dc." in name
        or ".ac." in name
        or ".info." in name
    )


def list_result_files(path: Path) -> list[str]:
    root = _psf_scan_root(path)
    return sorted(
        str(item.relative_to(root))
        for item in root.rglob("*")
        if item.is_file() and _is_result_file(item)
    )


def parse_sweep_directory(path: Path) -> dict[str, Any]:
    """Parse classic ``sw*.sweep*/N/`` or X/LX flat sweep output."""
    root = _psf_scan_root(path)
    points: dict[int, dict[str, Any]] = {}
    layout: str | None = None

    for sweep_dir in sorted(root.glob("sw*.sweep*")):
        if not sweep_dir.is_dir():
            continue
        for point_dir in sorted(sweep_dir.iterdir()):
            if not point_dir.is_dir():
                continue
            try:
                point_index = int(point_dir.name)
            except ValueError:
                continue
            parsed = parse_psf_directory(point_dir, "all")
            points[point_index] = parsed["data"]
            layout = layout or "classic"

    if not points:
        for psf_file in sorted(root.glob("sw*-[0-9]*_*")):
            match = re.match(r"sw\d+-(\d+)_.+", psf_file.name)
            if not match:
                continue
            _, parsed = parse_psf_file(psf_file)
            points[int(match.group(1)) + 1] = parsed
        if points:
            layout = "flat"

    if not points:
        raise ValueError(f"no sweep layout recognized below {path}")

    signals = sorted({key for point in points.values() for key in point})
    return {
        "layout": layout,
        "points": points,
        "point_count": len(points),
        "signals": signals,
        "files": list_result_files(root),
    }


def detect_layout(path: Path) -> str:
    """Return ``single`` / ``raw`` / ``sweep`` for a local result path."""
    path = Path(path)
    if path.is_file():
        return "single"
    if not path.is_dir():
        raise FileNotFoundError(f"result path not found: {path}")
    root = _psf_scan_root(path)
    if any(root.glob("sw*.sweep*")) or any(root.glob("sw*-[0-9]*_*")):
        return "sweep"
    return "raw"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _resolve_key(data: dict[str, Any], name: str) -> str:
    """Exact key first; otherwise the unique ``<prefix>_<name>`` key (e.g. ``ac_freq``)."""
    if name in data:
        return name
    suffix = "_" + name
    candidates = [key for key in data
                  if isinstance(key, str) and key.endswith(suffix)]
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError(f"signal '{name}' is missing")


def _real_vector(data: dict[str, Any], name: str) -> list[float]:
    key = _resolve_key(data, name)
    raw = data[key]
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"signal '{name}' must be a non-empty vector")
    try:
        return [float(item) for item in raw]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"signal '{name}' is not a real vector") from exc


def _complex_vector(data: dict[str, Any], name: str) -> list[complex]:
    key = _resolve_key(data, name)
    raw = data[key]
    try:
        if isinstance(raw, dict) and "re" in raw and "im" in raw:
            real = [float(item) for item in raw["re"]]
            imag = [float(item) for item in raw["im"]]
            if len(real) != len(imag) or not real:
                raise ValueError
            return [complex(item, imag[index]) for index, item in enumerate(real)]
        if isinstance(raw, list) and raw:
            return [complex(float(item)) for item in raw]
    except (TypeError, ValueError, KeyError) as exc:
        raise ValueError(f"signal '{name}' is not a numeric vector") from exc
    raise ValueError(f"signal '{name}' must be a non-empty numeric vector")


def _indices_in_range(values: list[float], start: Any, stop: Any) -> list[int]:
    indexes = []
    for index, value in enumerate(values):
        if start is not None and value < float(start):
            continue
        if stop is not None and value > float(stop):
            break
        indexes.append(index)
    return indexes


def _crossing_time(
    data: dict[str, Any],
    signal: str,
    threshold: Any,
    direction: str,
    edge: int,
    start: Any,
    stop: Any,
    x_name: str,
) -> float:
    x_values = _real_vector(data, x_name)
    y_values = [abs(item) for item in _complex_vector(data, signal)]
    indexes = _indices_in_range(x_values, start, stop)
    threshold = float(threshold)
    found = 0
    for left, right in zip(indexes, indexes[1:]):
        y0, y1 = y_values[left], y_values[right]
        if direction == "rise" and not (y0 <= threshold < y1):
            continue
        if direction == "fall" and not (y0 >= threshold > y1):
            continue
        found += 1
        if found != edge:
            continue
        denominator = y1 - y0
        if denominator == 0.0:
            raise ValueError("threshold crossing has a flat segment")
        fraction = (threshold - y0) / denominator
        return x_values[left] + fraction * (x_values[right] - x_values[left])
    raise ValueError(
        f"crossing edge {edge} not found for '{signal}' "
        f"(direction={direction}, threshold={threshold})"
    )


def _metric_error(type_name: str, exc: BaseException) -> dict[str, Any]:
    return {"type": type_name, "ok": False, "value": None, "unit": None,
            "detail": f"{type(exc).__name__}: {exc}"}


def _compute_threshold(data: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    type_name = "threshold_crossing"
    try:
        value = _crossing_time(
            data,
            spec["signal"],
            spec["threshold"],
            spec.get("direction", "rise"),
            int(spec.get("edge", 1)),
            spec.get("start"),
            spec.get("stop"),
            spec.get("x", "time"),
        )
        return {"type": type_name, "ok": True, "value": value, "unit": "s",
                "detail": None}
    except Exception as exc:
        return _metric_error(type_name, exc)


def _compute_delay(data: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    type_name = "delay"
    try:
        x_name = spec.get("x", "time")
        threshold = spec["threshold"]
        direction = spec.get("direction", "rise")
        start = spec.get("start")
        stop = spec.get("stop")
        edge = int(spec.get("edge", 1))
        t_from = _crossing_time(
            data, spec["from_signal"], threshold, direction, edge,
            start, stop, x_name,
        )
        t_to = _crossing_time(
            data, spec["to_signal"], threshold, direction, edge,
            start, stop, x_name,
        )
        return {"type": type_name, "ok": True, "value": t_to - t_from,
                "unit": "s", "detail": None}
    except Exception as exc:
        return _metric_error(type_name, exc)


def _window_values(
    data: dict[str, Any], signal: str, start: Any, stop: Any, x_name: str
) -> tuple[list[float], list[float]]:
    x_values = _real_vector(data, x_name)
    y_values = [abs(item) for item in _complex_vector(data, signal)]
    indexes = _indices_in_range(x_values, start, stop)
    return [x_values[index] for index in indexes], [
        y_values[index] for index in indexes
    ]


def _compute_statistic(data: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    type_name = str(spec.get("type", ""))
    try:
        _, values = _window_values(
            data, spec["signal"], spec.get("start"), spec.get("stop"),
            spec.get("x", "time"),
        )
        if not values:
            raise ValueError("signal window is empty")
        if type_name == "min":
            value: float = min(values)
        elif type_name == "max":
            value = max(values)
        elif type_name == "mean":
            value = sum(values) / len(values)
        elif type_name == "rms":
            value = math.sqrt(sum(item * item for item in values) / len(values))
        else:
            raise ValueError(f"unsupported statistic: {type_name}")
        return {"type": type_name, "ok": True, "value": value, "unit": None,
                "detail": None}
    except Exception as exc:
        return _metric_error(type_name, exc)


def _compute_ac_magnitude(data: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    type_name = "ac_magnitude"
    try:
        x_values = _real_vector(data, spec.get("x", "freq"))
        y_values = _complex_vector(data, spec["signal"])
        target = float(spec["frequency"])
        index = min(range(len(x_values)), key=lambda item: abs(x_values[item] - target))
        magnitude = abs(y_values[index])
        scale = spec.get("scale", "linear")
        value: float
        unit: str | None
        if scale == "db":
            if magnitude <= 0:
                raise ValueError("magnitude must be positive for dB scale")
            value = 20.0 * math.log10(magnitude)
            unit = "dB"
        elif scale == "linear":
            value = magnitude
            unit = None
        else:
            raise ValueError("scale must be 'db' or 'linear'")
        return {"type": type_name, "ok": True, "value": value, "unit": unit,
                "detail": None}
    except Exception as exc:
        return _metric_error(type_name, exc)


def _compute_bandwidth(data: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    type_name = "bandwidth"
    try:
        x_values = _real_vector(data, spec.get("x", "freq"))
        y_values = [abs(item) for item in _complex_vector(data, spec["signal"])]
        if len(x_values) < 2:
            raise ValueError("frequency vector has fewer than two points")
        reference = spec.get("reference", "dc")
        if reference == "dc":
            baseline = y_values[0]
            start_index = 0
        elif reference == "max":
            start_index = max(range(len(y_values)), key=lambda item: y_values[item])
            baseline = y_values[start_index]
        else:
            raise ValueError("reference must be 'dc' or 'max'")
        if baseline <= 0:
            raise ValueError("bandwidth reference magnitude is not positive")
        drop_db = float(spec.get("drop_db", 3.0))
        target = baseline * 10.0 ** (-drop_db / 20.0)
        for index in range(start_index, len(y_values)):
            if y_values[index] <= target:
                return {"type": type_name, "ok": True,
                        "value": x_values[index], "unit": "Hz", "detail": None}
        raise ValueError("bandwidth point not found")
    except Exception as exc:
        return _metric_error(type_name, exc)


def _compute_noise_integral(data: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    type_name = "noise_integral"
    try:
        x_values, y_values = _window_values(
            data, spec["signal"], spec.get("start"), spec.get("stop"),
            spec.get("x", "freq"),
        )
        if not y_values:
            raise ValueError("signal window is empty")
        power = [abs(item) ** 2 for item in y_values]
        total = 0.0
        for index in range(len(power) - 1):
            total += 0.5 * (power[index] + power[index + 1]) * (
                x_values[index + 1] - x_values[index]
            )
        return {"type": type_name, "ok": True, "value": total, "unit": "V^2",
                "detail": None}
    except Exception as exc:
        return _metric_error(type_name, exc)


def compute_metric(data: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one metric spec without raising for domain errors."""
    type_name = str(spec.get("type", "")).strip()
    if type_name in ("threshold_crossing",):
        return _compute_threshold(data, spec)
    if type_name == "delay":
        return _compute_delay(data, spec)
    if type_name in ("min", "max", "mean", "rms"):
        return _compute_statistic(data, spec)
    if type_name == "ac_magnitude":
        return _compute_ac_magnitude(data, spec)
    if type_name == "bandwidth":
        return _compute_bandwidth(data, spec)
    if type_name == "noise_integral":
        return _compute_noise_integral(data, spec)
    return _metric_error(type_name or "unknown", ValueError(f"unsupported metric: {type_name}"))


__all__ = [
    "compute_metric",
    "detect_layout",
    "list_result_files",
    "parse_psf_directory",
    "parse_psf_file",
    "parse_sweep_directory",
    "psf_external",
]
