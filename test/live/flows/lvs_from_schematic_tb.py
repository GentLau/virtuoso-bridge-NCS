"""S11-LVS TB：**源网表由 bridge 自读的原理图数据生成**，再跑 Calibre LVS。

与 ``s11_full_flow.py`` 的区别：那份 TB 用的源网表是工程里既有的手写 CDL
（``~/project/test/cmp_top_full.cdl``，2026-08-17 之前就在），因此只能证明
"Calibre 能跑 + 版图与那份网表一致"；本 TB 把源网表这一步也变成**产品数据驱动**：

    bridge.schematic.read(顶层) + bridge.schematic.read(子单元)
        → TB 生成 CDL（器件行 D G S B + l/w/nf/m）
        → bridge 导出 GDS（layout.gds export）
        → bridge 跑 Calibre LVS（calibre.lvs / calibre.read_results）
        → 证据 JSON（含每个文件的 sha256 与 lvs.rep 摘录）

用法::

    python test/live/flows/lvs_from_schematic_tb.py \
        --lib CMP_LIB --cell cmp_top --token d6af595b342647b58ec63ca6 \
        --out test/artifacts/env/scenario-project65/lvs/evidence-lvs-from-schematic.json

约定：器件 cell 名（``nch_25``/``pch_25``）到 Calibre deck 的 DEVICE 名
（``nch``/``pch``）的映射表写在 ``DEVICE_MAP``；依据是 lvs.rep 里的
``TRACE PROPERTY mn(nch)`` / ``mp(pch)`` 行（见 evidence 的 deck_devices 字段）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]

API = "http://127.0.0.1:8127/api/operation"
PDK_CALIBRE = "/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/Calibre"
DEFAULT_DECK = f"{PDK_CALIBRE}/lvs/calibre.lvs"
DEFAULT_CALIBRE_BIN = "/opt/eda/mentor/CALIBRE2025/aok_cal_2025.1_16.10/bin/calibre"
DEFAULT_LAYER_MAP = "/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/tsmcN65/tsmcN65.layermap"

#: 原理图里的器件 model → PDK Calibre deck 的 DEVICE 名。
#: CMP_LIB 用的是库内本地器件（model 就叫 nch/pch）；PROJ65 直接用 tsmcN65 的
#: nch_25/pch_25，两者都要映射到 deck 里的 nch/pch（依据见 lvs.rep 的
#: `TRACE PROPERTY mn(nch) l l 0`）。
DEVICE_MAP = {"nch": "nch", "pch": "pch", "nch_25": "nch", "pch_25": "pch"}


class TbError(RuntimeError):
    pass


def call(payload: dict[str, Any], timeout: float = 1800.0) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        API, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:  # 业务面 4xx 也把 body 读回来
        return json.loads(error.read().decode("utf-8"))


def op(operation: str, token: str, **fields: Any) -> Any:
    response = call({"operation": operation, "token": token, **fields})
    if not response.get("ok"):
        raise TbError(f"{operation}: {response.get('error')}")
    return response.get("data")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cmd_stdout(data: Any) -> str:
    """``basic.command.run`` 的 data.result 是 CommandResult 序列化后的 list。"""
    if isinstance(data, dict):
        result = data.get("result")
        if isinstance(result, list) and len(result) >= 2:
            return str(result[1])
        if isinstance(result, dict):
            return str(result.get("stdout", ""))
    return ""


def read_schematic(token: str, lib: str, cell: str) -> dict[str, Any]:
    data = op("virtuoso.schematic.read", token, library=lib, cell=cell,
              view="schematic", timeout=300)
    value = data.get("value") if isinstance(data, dict) else None
    if not isinstance(value, dict):
        raise TbError(f"schematic.read({lib}/{cell}) 没有返回结构化 value")
    return value


def _ports_from_terms(terms: dict[str, str] | None) -> list[str]:
    return list(terms.keys()) if isinstance(terms, dict) else []


def _pin_names(value: dict[str, Any]) -> list[str]:
    """schematic.read 的 pins 是 [{name, direction}, ...]（也可能是 dict）。"""
    pins = value.get("pins")
    if isinstance(pins, list):
        return [str(pin.get("name")) for pin in pins if isinstance(pin, dict) and pin.get("name")]
    if isinstance(pins, dict):
        return list(pins.keys())
    return []


def _device_line(name: str, terms: dict[str, str], params: dict[str, Any]) -> str | None:
    cell = str(params.get("model") or "").strip()
    model = DEVICE_MAP.get(cell)
    if not model:
        return None
    nodes = [terms.get(key) for key in ("D", "G", "S", "B")]
    if any(node in (None, "") for node in nodes):
        return None
    parts = [f"M{name}", *[str(node) for node in nodes], model]
    for out_key, in_keys in (("l", ("l",)), ("w", ("w", "wf")), ("nf", ("fingers",)),
                             ("m", ("simM", "m"))):
        for in_key in in_keys:
            raw = params.get(in_key)
            if raw not in (None, "", 0, "0"):
                parts.append(f"{out_key}={raw}")
                break
    return " ".join(parts)


def generate_cdl(cells: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    """把读回的单元数据转成 CDL 文本。返回 (cdl, 统计)。"""
    header = "* LVS source netlist auto-generated from bridge schematic.read"
    stats: dict[str, Any] = {"cells": [], "device_lines": 0, "subckt_lines": 0,
                             "skipped_instances": []}
    top, children = cells[0], cells[1:]

    def _is_device(inst: dict[str, Any]) -> bool:
        return (inst.get("params") or {}).get("model") in DEVICE_MAP

    # 每个单元的端口顺序：优先用该单元自己的 pins 顺序；没有就退回"引用它的实例的端子顺序"
    port_order: dict[tuple[str, str], list[str]] = {
        (entry["lib"], entry["cell"]): _pin_names(entry["value"]) for entry in cells}
    for entry in cells:
        parent_key = (entry["lib"], entry["cell"])
        if port_order[parent_key]:
            continue
        for inst in entry["value"].get("instances") or []:
            child_key = (inst.get("lib"), inst.get("cell"))
            if child_key in port_order and not port_order[child_key]:
                port_order[child_key] = _ports_from_terms(inst.get("terms"))

    def _cell_block(entry: dict[str, Any]) -> list[str]:
        key = (entry["lib"], entry["cell"])
        instances = list(entry["value"].get("instances") or [])
        ports = port_order.get(key) or []
        block = [f".SUBCKT {entry['cell']} {' '.join(ports)}".rstrip()]
        for inst in instances:
            if _is_device(inst):
                line = _device_line(str(inst.get("name")), inst.get("terms") or {},
                                    inst.get("params") or {})
                if line is None:
                    stats["skipped_instances"].append(f"{entry['cell']}/{inst.get('name')}")
                    continue
                block.append(line)
                stats["device_lines"] += 1
                continue
            child_key = (inst.get("lib"), inst.get("cell"))
            terms = inst.get("terms") or {}
            child_ports = port_order.get(child_key) or list(terms.keys())
            missing = [port for port in child_ports if port not in terms]
            if missing or not child_ports:
                stats["skipped_instances"].append(f"{entry['cell']}/{inst.get('name')}")
                continue
            block.append(f"X{inst.get('name')} " +
                         " ".join(str(terms[port]) for port in child_ports) +
                         f" {inst.get('cell')}")
        block.append(".ENDS")
        stats["subckt_lines"] += 1
        stats["cells"].append({"lib": entry["lib"], "cell": entry["cell"],
                               "devices": sum(1 for inst in instances if _is_device(inst)),
                               "hier_instances": [inst.get("name") for inst in instances
                                                  if not _is_device(inst)],
                               "ports": ports})
        return block

    blocks: list[list[str]] = []
    for child in reversed(children):  # 子单元在前，顶层在后
        blocks.append(_cell_block(child))
    top_block = _cell_block(top)
    stats["cells"].insert(0, stats["cells"].pop())

    lines = [header]
    for block in blocks + [top_block]:
        lines.extend(block)
    return "\n".join(lines) + "\n", stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lib", default="CMP_LIB")
    parser.add_argument("--cell", default="cmp_top")
    parser.add_argument("--token", default="d6af595b342647b58ec63ca6")
    parser.add_argument("--deck", default=DEFAULT_DECK)
    parser.add_argument("--calibre-bin", default=DEFAULT_CALIBRE_BIN)
    parser.add_argument("--layer-map", default=DEFAULT_LAYER_MAP)
    parser.add_argument("--remote-root", default="/home/Gent/.virtuoso-bridge/calprobe/file/lvs_from_schematic")
    parser.add_argument("--job-id", default="lvs-from-schematic")
    parser.add_argument("--turbo", type=int, default=4)
    parser.add_argument("--local-gds", default="",
                        help="复用一份**已由产品导出的** GDS（当版图被别的 Virtuoso 会话锁住、"
                             "无法再走 layout.gds export 时使用；sha256 会写进证据）")
    parser.add_argument("--out", default=str(ROOT / "test" / "artifacts" /
                                             "scenario-project65" / "lvs" /
                                             "evidence-lvs-from-schematic.json"))
    parser.add_argument("--skip-lvs", action="store_true", help="只生成网表，不跑 Calibre")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    token = args.token
    evidence: dict[str, Any] = {"tb": "lvs_from_schematic_tb", "started": time.strftime(
        "%Y-%m-%dT%H:%M:%S%z"), "lib": args.lib, "cell": args.cell,
        "deck": args.deck, "calibre_bin": args.calibre_bin,
        "device_map": DEVICE_MAP, "steps": []}
    work = Path(args.out).resolve().parent
    work.mkdir(parents=True, exist_ok=True)

    def step(name: str, ok: bool, detail: Any) -> None:
        evidence["steps"].append({"name": name, "ok": ok, "detail": detail})
        flag = "ok " if ok else "FAIL"
        print(f"[{flag}] {name}: {str(detail)[:200]}")

    # 1) 读顶层原理图；对它引用到的**每一层**子单元做 BFS（cmp 里还嵌了 inv2）
    top_value = read_schematic(token, args.lib, args.cell)
    cells: list[dict[str, Any]] = [{"lib": args.lib, "cell": args.cell, "value": top_value}]
    step("schematic-read-top", True,
         {"instances": len(top_value.get("instances") or []), "pins": _pin_names(top_value)})
    seen = {(args.lib, args.cell)}
    queue = list(top_value.get("instances") or [])
    depth = 0
    while queue and depth < 4:
        depth += 1
        next_queue: list[dict[str, Any]] = []
        for inst in queue:
            child_lib, child_cell = inst.get("lib"), inst.get("cell")
            if not child_lib or not child_cell or (child_lib, child_cell) in seen:
                continue
            if (inst.get("params") or {}).get("model") in DEVICE_MAP:
                continue
            child_value = read_schematic(token, child_lib, child_cell)
            seen.add((child_lib, child_cell))
            cells.append({"lib": child_lib, "cell": child_cell, "value": child_value})
            step("schematic-read-child", True,
                 {"lib": child_lib, "cell": child_cell, "depth": depth,
                  "instances": len(child_value.get("instances") or [])})
            next_queue.extend(child_value.get("instances") or [])
        queue = next_queue

    # 2) 生成 CDL
    cdl, cdl_stats = generate_cdl(cells)
    cdl_path = work / f"{args.cell}_from_schematic.cdl"
    cdl_path.write_text(cdl, encoding="utf-8")
    step("cdl-generate", cdl_stats["device_lines"] > 0,
         {"path": str(cdl_path), "bytes": len(cdl.encode("utf-8")),
          "sha256": sha256_text(cdl), **cdl_stats})
    evidence["cdl"] = {"path": str(cdl_path), "sha256": sha256_text(cdl), "text": cdl}
    if cdl_stats["device_lines"] == 0:
        step("abort", False, "生成的 CDL 没有任何器件行（读回的 params.model 不在 DEVICE_MAP 里）")
        Path(args.out).write_text(json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8")
        return 1

    # 3) GDS：默认现导（产品 layout.gds export）；被别的会话锁住时用 --local-gds 复用已导出件
    if args.local_gds:
        local_gds = Path(args.local_gds).resolve()
        step("gds-reuse", local_gds.is_file(),
             {"path": str(local_gds), "bytes": local_gds.stat().st_size if local_gds.is_file() else 0,
              "sha256": sha256_file(local_gds) if local_gds.is_file() else None,
              "note": "复用此前由产品 layout.gds export 导出的 GDS（本次未重新导出）"})
    else:
        local_gds = work / f"{args.cell}_from_bridge.gds"
        op("virtuoso.layout.gds", token, action="export", library=args.lib, cell=args.cell,
           view="layout", file_path=str(local_gds), timeout=600,
           layer_map=args.layer_map, layer_map_is_local=False)
    gds_ok = local_gds.is_file()
    step("gds-export", gds_ok, {"path": str(local_gds),
                                "bytes": local_gds.stat().st_size if gds_ok else 0,
                                "sha256": sha256_file(local_gds) if gds_ok else None})
    evidence["gds"] = {"path": str(local_gds),
                       "sha256": sha256_file(local_gds) if gds_ok else None,
                       "bytes": local_gds.stat().st_size if gds_ok else 0}
    if not gds_ok:
        Path(args.out).write_text(json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8")
        return 1

    # 4) 上传 CDL / GDS 到远端工作目录
    remote_dir = f"{args.remote_root}/{args.job_id}"
    op("basic.command.run", token, cmd=f"rm -rf {remote_dir} && mkdir -p {remote_dir}",
       timeout=120)
    remote_cdl = f"{remote_dir}/{args.cell}.cdl"
    remote_gds = f"{remote_dir}/{args.cell}.gds"
    op("basic.file.upload", token, local_path=str(cdl_path), remote_path=remote_cdl, timeout=300)
    op("basic.file.upload", token, local_path=str(local_gds), remote_path=remote_gds, timeout=300)
    step("upload-inputs", True, {"cdl": remote_cdl, "gds": remote_gds})

    if args.skip_lvs:
        step("lvs-skipped", True, "--skip-lvs")
        Path(args.out).write_text(json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8")
        return 0

    # 5) 产品跑 Calibre LVS（阻塞），再读结果
    lvs = op("calibre.lvs", token, gds=remote_gds, top=args.cell, deck=args.deck,
             cdl=remote_cdl, calibre_bin=args.calibre_bin, job_id=args.job_id,
             run_dir=f"{remote_dir}/run", turbo=args.turbo, hier=True,
             blocking=True, timeout=900)
    step("calibre-lvs", bool(lvs), {"job_id": lvs.get("job_id"), "run_dir": lvs.get("run_dir"),
                                   "status": lvs.get("status")})
    evidence["lvs_run"] = lvs

    results = op("calibre.read_results", token, kind="lvs", job_id=args.job_id,
                 run_dir=f"{remote_dir}/run", timeout=300)
    evidence["lvs_read_results"] = results
    parsed = results.get("value") if isinstance(results, dict) else None
    step("calibre-read-results", bool(parsed),
         (parsed or {}).get("summary") if isinstance(parsed, dict) else parsed)

    report = op("basic.command.run", token, timeout=180,
                cmd=(f"cd {remote_dir}/run 2>/dev/null && "
                     "grep -m1 -E 'CORRECT|INCORRECT' lvs.rep; "
                     "grep -m2 -E '^(Nets|Instances|Cells):' lvs.rep; "
                     "ls -la lvs.rep lvs.rep.ext 2>/dev/null; "
                     "grep -m4 -E 'TRACE PROPERTY (mn|mp)\\(' lvs.rep | head -4"))
    stdout = cmd_stdout(report)
    verdict_lines = [line for line in str(stdout or "").splitlines()
                     if "CORRECT" in line or line.startswith(("Nets:", "Instances:", "Cells:"))]
    # 报告里既有装饰行也有汇总行；优先取以 CORRECT/INCORRECT 开头的汇总行
    verdict = next((line.strip() for line in verdict_lines
                    if line.strip().startswith(("CORRECT", "INCORRECT"))), "")
    if not verdict:
        verdict = next((line.strip() for line in verdict_lines if "CORRECT" in line), "")
    summary = (parsed or {}).get("summary") if isinstance(parsed, dict) else None
    status = str((summary or {}).get("status") or "").lower()
    passed = bool(verdict) and "INCORRECT" not in verdict and status != "incorrect"
    step("lvs-verdict", passed, {"verdict": verdict[:160], "read_results_status": status,
                                "report_tail": verdict_lines[:6]})
    evidence["verdict"] = {"passed": passed, "line": verdict.strip(),
                           "evidence_lines": verdict_lines[:8]}

    # 6) 把远端报告拉回仓库（有就拉，拉不到不掩盖）
    try:
        op("basic.file.download", token, remote_path=f"{remote_dir}/run/lvs.rep",
           local_path=str(work / f"lvs-{args.job_id}.rep"), timeout=300)
        rep = work / f"lvs-{args.job_id}.rep"
        evidence["lvs_report"] = {"path": str(rep), "bytes": rep.stat().st_size,
                                  "sha256": sha256_file(rep)}
        step("lvs-report-download", True, evidence["lvs_report"])
    except Exception as error:  # noqa: BLE001 - 证据缺失要记录而不是崩
        step("lvs-report-download", False, repr(error))

    evidence["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    Path(args.out).write_text(json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"evidence: {args.out}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
