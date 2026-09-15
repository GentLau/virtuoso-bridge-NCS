#!/usr/bin/env python3
"""Spec governance checker (the "Spec CI" referenced by spec/README.md).

Runs with the standard library only so CI needs no extra dependencies:

    python tools/check_spec.py

Checks
------
1. Normative hash   — recompute the 7-file aggregate from the *committed*
                      content (LF, i.e. ``git show :<path>``) and compare it
                      with the value documented in ``spec/README.md``.
2. Manifest versions— each doc header ``版本：`` matches the Manifest table.
3. Links            — every relative Markdown link resolves.
4. JSON blocks      — every ```json fenced block parses.
5. Banned copies    — non-owner documents must not re-define a mechanism that
                      has a unique owner (word list in ``spec/README.md``).
6. Headings         — no duplicate numbered headings inside one document.

Exit code is non-zero when any check fails; ``--quiet`` prints only failures.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SPEC = REPO / "spec"
README = SPEC / "README.md"

NORMATIVE = [
    "design-concepts/总览/1-四层整体架构与接口.md",
    "design-concepts/总览/本版范围与明确不支持.md",
    "design-concepts/总览/配置一览.md",
    "design-concepts/底层与中层/多节点设计.md",
    "design-concepts/底层与中层/多用户设计.md",
    "design-concepts/底层与中层/2-并发设计.md",
    "design-concepts/底层与中层/日志返回设计标准.md",
]

# mechanism -> (owner file, patterns that may only appear in the owner)
OWNED_PATTERNS = [
    ("endpoint canonical key", "design-concepts/总览/配置一览.md",
     [r"endpoint_key\s*=", r"canonical_json\s*="]),
    ("channel 记账矩阵", "design-concepts/底层与中层/2-并发设计.md",
     [r"\|\s*动作\s*\|\s*线程预算\s*\|\s*channel 预算"]),
    ("CommandResult.kind 枚举", "design-concepts/总览/1-四层整体架构与接口.md",
     [r"(?:.*`kind=[a-z-]+`.*){3,}"]),
    ("六步注册状态机", "design-concepts/底层与中层/多用户设计.md",
     [r"\|\s*步\s*\|\s*预测目标"]),
    ("reservation 记录格式", "design-concepts/总览/配置一览.md",
     [r"registry\.reservation", r"\"local_port\":\s*6"]),
]

BANNED_LITERALS = ["三接口", "三端口", "三条数据流"]
BANNED_EXCEPTION = "子集示例"


def read_committed(rel: str) -> bytes | None:
    """Content as committed (index first, then HEAD) — LF, platform-independent."""
    for rev in (f":spec/{rel}", f"HEAD:spec/{rel}"):
        proc = subprocess.run(
            ["git", "-C", str(REPO), "show", rev],
            capture_output=True,
        )
        if proc.returncode == 0:
            return proc.stdout
    return None


def norm_hash() -> tuple[str, list[str]]:
    lines = []
    for rel in sorted(NORMATIVE):
        data = read_committed(rel)
        if data is None:
            data = (SPEC / rel).read_bytes().replace(b"\r\n", b"\n")
        lines.append(f"{rel} {hashlib.sha256(data).hexdigest()}")
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest(), lines


def check_hash(failures: list[str]) -> None:
    documented = re.search(r"Normative 内容哈希\*\*：`([0-9a-f]{64})`", README.read_text(encoding="utf-8"))
    if not documented:
        failures.append("README: Normative 内容哈希 not found")
        return
    actual, per_file = norm_hash()
    if documented.group(1) != actual:
        failures.append(f"hash mismatch: README={documented.group(1)} actual={actual}")
    else:
        print(f"[ok] normative hash {actual[:16]}…")
    del per_file


def check_manifest(failures: list[str]) -> None:
    readme = README.read_text(encoding="utf-8")
    rows = {}
    for line in readme.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 4 and cells[1].startswith(("Draft v", "v")):
            rows[cells[0]] = cells[1]
    checked = 0
    for rel in NORMATIVE:
        text = (SPEC / rel).read_text(encoding="utf-8")
        m = re.search(r"^> 版本：(.+)$", text, re.M)
        if not m:
            failures.append(f"{rel}: missing '> 版本：' header")
            continue
        header = m.group(1).strip()
        name = re.sub(r"^\d+-", "", Path(rel).stem)
        if name not in rows:
            failures.append(f"{rel}: no manifest row named {name!r}")
            continue
        if rows[name] != header:
            failures.append(f"{rel}: header={header!r} manifest={rows[name]!r}")
        checked += 1
    if checked == len(NORMATIVE):
        print(f"[ok] manifest versions match {checked} doc headers")


def check_links(failures: list[str]) -> None:
    total = 0
    for md in sorted(SPEC.rglob("*.md")):
        text = md.read_text(encoding="utf-8")
        for m in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", text):
            target = m.group(1).strip()
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            target = target.split("#")[0]
            if not target:
                continue
            total += 1
            if not (md.parent / target).resolve().exists():
                failures.append(f"{md.relative_to(SPEC)}: broken link -> {target}")
    print(f"[ok] {total} relative links checked")


def check_json_blocks(failures: list[str]) -> None:
    blocks = 0
    for md in sorted(SPEC.rglob("*.md")):
        text = md.read_text(encoding="utf-8")
        for m in re.finditer(r"```json\n(.*?)```", text, re.S):
            blocks += 1
            try:
                json.loads(m.group(1))
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{md.relative_to(SPEC)}: invalid json block: {exc}")
    print(f"[ok] {blocks} json blocks parsed")


def check_banned(failures: list[str]) -> None:
    hits = 0
    for rel in NORMATIVE:
        text = (SPEC / rel).read_text(encoding="utf-8")
        owner_of = {}
        for _, owner, patterns in OWNED_PATTERNS:
            for pat in patterns:
                owner_of.setdefault(pat, owner)
        for i, line in enumerate(text.splitlines(), 1):
            if rel != "design-concepts/总览/1-四层整体架构与接口.md" and line.count("`kind=") >= 3:
                hits += 1
                failures.append(
                    f"{rel}:{i}: CommandResult.kind 枚举只允许出现在 "
                    f"design-concepts/总览/1-四层整体架构与接口.md"
                )
            for word in BANNED_LITERALS:
                if word in line and BANNED_EXCEPTION not in line:
                    hits += 1
                    failures.append(f"{rel}:{i}: 禁用词 {word!r}（子集示例需显式标注）")
            for label, owner, patterns in OWNED_PATTERNS:
                for pat in patterns:
                    if re.search(pat, line) and rel != owner:
                        hits += 1
                        failures.append(f"{rel}:{i}: {label} 只允许出现在 {owner}")
    print(f"[ok] banned-copy scan done ({hits} hits)" if hits == 0 else f"[!!] banned-copy hits: {hits}")


def check_headings(failures: list[str]) -> None:
    for md in sorted(SPEC.rglob("*.md")):
        text = md.read_text(encoding="utf-8")
        heads = re.findall(r"^#{2,4}\s+(\d+(?:\.\d+)*)[.、\s]", text, re.M)
        dupes = sorted({h for h in heads if heads.count(h) > 1})
        if dupes:
            failures.append(f"{md.relative_to(SPEC)}: duplicate numbered headings {dupes}")
    print("[ok] numbered headings unique per document")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    failures: list[str] = []
    check_hash(failures)
    check_manifest(failures)
    check_links(failures)
    check_json_blocks(failures)
    check_banned(failures)
    check_headings(failures)

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  -", f)
        return 1
    if not args.quiet:
        print("\nSpec checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
