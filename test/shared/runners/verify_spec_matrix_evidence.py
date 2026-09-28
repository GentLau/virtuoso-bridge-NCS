"""核对 spec 覆盖矩阵里每一行的"证据文件"是否真的在本轮 JUnit 里跑过。

为什么需要：矩阵里大量 `🟡 历史已验` 其实是**本轮离线套件里跑过的**（整层一起跑了），
只是因为写矩阵时按"这轮专门为它取证"来标，保守标成了历史。本脚本用 JUnit XML 把它们区分开：

* 行里引用的 `test/.../*.py` 在本轮 XML 中有用例且**全绿** → 可以升级为"本轮已验（随离线套件复跑）"；
* 有红用例 → 说明该行证据依赖已立案缺陷，保持原状并点名；
* XML 里根本没有 → 保持"历史/未复跑"。

用法::

    python test/shared/runners/verify_spec_matrix_evidence.py \
        --matrix test/reports/round5-spec覆盖矩阵.md \
        --junit test/artifacts/evidence/round5-main/offline-final.xml
"""
from __future__ import annotations

import argparse
import collections
import re
import xml.etree.ElementTree as ET
from pathlib import Path

MARK_ROWS = ("🟡", "⬜", "✅")
FILE_RE = re.compile(r"test/[A-Za-z0-9_./-]+\.py")


def load_junit(path: Path) -> dict[str, list[int]]:
    root = ET.parse(path).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        raise SystemExit(f"unexpected JUnit shape: {path}")
    stat: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    for case in suite.iter("testcase"):
        classname = case.attrib.get("classname", "")
        # classname 形如 `test.offline.unit.test_transfer.TestX` → 取前四段就是模块路径
        module = ".".join(classname.split(".")[:4]) if classname.startswith("test.") else classname
        stat[module][0] += 1
        if any(child.tag in ("failure", "error") for child in case):
            stat[module][1] += 1
    return stat


def module_of(test_path: str) -> str:
    return ".".join(Path(test_path).with_suffix("").parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", default="test/reports/round5-spec覆盖矩阵.md")
    parser.add_argument("--junit", default="test/artifacts/evidence/round5-main/offline-final.xml")
    parser.add_argument("--md", action="store_true",
                        help="输出可直接贴进矩阵的 Markdown 表（只列离线证据本轮全绿的行）")
    parser.add_argument("--append-to-matrix", action="store_true",
                        help="把 §14 核对表写回矩阵（幂等：替换既有 markers 之间的内容）")
    args = parser.parse_args(argv)

    stat = load_junit(Path(args.junit))
    lines = Path(args.matrix).read_text(encoding="utf-8").splitlines()

    upgradeable: list[tuple[str, str, int]] = []
    blocked: list[tuple[str, str, int]] = []
    untouched: list[tuple[str, str]] = []
    for line in lines:
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2 or cells[0] not in ("", "-") and not re.fullmatch(r"[A-Z]\d+", cells[0]):
            continue
        mark = cells[-1]
        if mark not in MARK_ROWS:
            continue
        files = FILE_RE.findall(line)
        offline = [f for f in files if f.startswith("test/offline/")]
        others = [f for f in files if not f.startswith("test/offline/")]
        if not offline:
            untouched.append((cells[0], "行内没有 test/offline/*.py 证据"))
            continue
        ran = 0
        red = 0
        missing = 0
        for path in offline:
            total, failed = stat.get(module_of(path), [0, 0])
            ran += total
            red += failed
            if total == 0:
                missing += 1
        if missing == len(offline) and ran == 0:
            untouched.append((cells[0], f"{len(offline)} 个离线证据文件本轮 XML 里没有用例"))
        elif red:
            blocked.append((cells[0], offline[0], red))
        elif missing:
            untouched.append((cells[0], f"{missing}/{len(offline)} 个离线证据文件本轮没跑"))
        else:
            upgradeable.append((cells[0], ", ".join(Path(f).name for f in offline), ran, len(others)))

    if args.md:
        print("| 行 | 本轮离线证据（全部为 green） | 用例数 | 行内另有非离线证据 |")
        print("|---|---|---|---|")
        for item, names, ran, n_other in upgradeable:
            print(f"| {item} | `{names}` | {ran} | {n_other if n_other else '—'} |")
        return 0

    if args.append_to_matrix:
        begin, end = "<!-- offline-rerun:begin -->", "<!-- offline-rerun:end -->"
        table = [
            "| 行 | 本轮离线证据（全部为 green） | 用例数 | 行内另有非离线证据 |",
            "|---|---|---|---|",
        ]
        table += [f"| {item} | `{names}` | {ran} | {n_other if n_other else '—'} |"
                  for item, names, ran, n_other in upgradeable]
        section = "\n".join([
            "## 14. 本轮离线复跑核对（机器生成，可复现）",
            "",
            "> 口径：矩阵里标 `🟡 历史已验` 的行，只要它引用的 `test/offline/**` 证据在本轮离线套件里"
            "跑过且全绿，就不属于「只靠历史证据」。下表把这类行挑出来；数据源 "
            "`round5-main/offline-final.xml`（**1686 项 / failures=11 / skipped=6**；junit 头的 `tests=2335` "
            "是 pytest 9.1.1 计入 subTest 的膨胀属性，别当用例数引用——见独立复核 D5）。",
            "> 最后一列是该行**还引用了几份真机/半真机文件**——那些部分仍按原状态，"
            "**不要**因为离线绿就当成全链已验。",
            "> 复现：`python test/shared/runners/verify_spec_matrix_evidence.py --md`",
            "",
            *table,
            "",
        ])
        text = Path(args.matrix).read_text(encoding="utf-8")
        if begin in text and end in text:
            head, rest = text.split(begin, 1)
            _old, tail = rest.split(end, 1)
            text = f"{head}{begin}\n{section}{end}{tail}"
        else:
            text = f"{text.rstrip()}\n\n{begin}\n{section}{end}\n"
        Path(args.matrix).write_text(text, encoding="utf-8")
        print(f"updated: {args.matrix}（{len(upgradeable)} 行）")
        return 0

    print(f"矩阵：{args.matrix}")
    print(f"JUnit：{args.junit}\n")
    print(f"[可升级] 本轮离线套件里跑过且全绿（{len(upgradeable)} 行）")
    for item, sample, ran, _n_other in upgradeable:
        print(f"   {item:5s} {ran:4d} 条用例全绿（例：{sample}）")
    print(f"\n[保持] 证据文件本轮有红（{len(blocked)} 行）——依赖已立案缺陷")
    for item, sample, red in blocked:
        print(f"   {item:5s} 红 {red} 条（例：{sample}）")
    print(f"\n[保持] 不是离线文件 / 本轮未跑（{len(untouched)} 行）")
    for item, why in untouched:
        print(f"   {item:5s} {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
