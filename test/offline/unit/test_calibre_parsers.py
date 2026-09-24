"""calibre 结果解析契约（第五轮新增，先红后绿）。

第五轮首次把 calibre 包接上真实环境（专用 work-dir + 8128 业务面）后实测发现：
`calibre.drc` 跑完（1737 rulechecks / 36 results）后，`calibre.read_results`
解析**真实 Calibre DRC.rep** 输出的是垃圾——

* ``by_rule`` 空：真实报告写的是 ``RULECHECK <name> .... TOTAL Result Count = N``，
  而解析器只认 ``^(RESULT|CHECK) <name> <n>``；
* ``first_offenders`` 把头部 "RUNTIME WARNINGS" 段的
  ``Cell name parameter   for INSIDE CELL operation not located.``
  当成违规条目（rule="Cell" / cell="operation"）。

本 TB 用**真实报告裁剪样本**（``test/shared/fixtures/calibre_drc_rep_sample.txt``，
取自 s11_inv/inv 的 DRC.rep）把"违规按规则聚合"和"不许有垃圾条目"钉住。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from pyapi.packages._calibre_util import (  # noqa: E402
    parse_drc_report,
    parse_drc_results_db,
    parse_lvs_report,
)

REPORT = (ROOT / "test" / "shared" / "fixtures" / "calibre_drc_rep_sample.txt").read_text(
    encoding="utf-8")
LVS_REPORT = (ROOT / "test" / "shared" / "fixtures" / "calibre_lvs_rep_sample.txt").read_text(
    encoding="utf-8")
DRC_DB = (ROOT / "test" / "shared" / "fixtures" / "calibre_drc_db_sample.txt").read_text(
    encoding="utf-8")

EXPECTED_BY_RULE = {
    "NW.A.1": 1, "NW.A.3": 1, "OD.DN.1L": 1, "DOD.R.1": 1, "PO.A.1": 2,
    "PO.DN.1L": 1, "DPO.R.1": 1, "M9.DN.1L": 1, "CSR.R.1.NWi": 1,
    "CSR.R.1.PPi": 1, "CSR.R.1.NPi": 1, "CSR.R.1.COi": 4, "CSR.R.1.M1i": 1,
    "CSR.R.1.M1_real": 1, "CSR.R.1.ODi": 2, "CSR.R.1.POi": 2, "DM1.R.1": 1,
    "DM2.R.1": 1, "DM3.R.1": 1, "DM4.R.1": 1, "DM5.R.1": 1, "DM6.R.1": 1,
    "DM7.R.1": 1, "DM8.R.1": 1, "DM9.R.1": 1, "LUP.6": 4, "ESD.WARN.1": 1,
}


def test_real_report_totals_are_read():
    """报告自带的总数必须能读出来（当前只有旧格式 ``TOTAL RULECHECKS EXECUTED =``
    能读；2025 报告写的是 ``TOTAL DRC RuleChecks Executed:`` → 解析为 None，
    线上只能靠 log counters 兜底 —— 报告解析器与真报告口径不一致）。"""
    summary = parse_drc_report(REPORT)
    assert summary["rules_checked"] == 1737
    assert summary["total_results"] == 36


def test_real_report_rule_counts_are_aggregated():
    summary = parse_drc_report(REPORT)
    assert summary["by_rule"] == EXPECTED_BY_RULE


def test_real_report_has_no_garbage_offenders():
    summary = parse_drc_report(REPORT)
    offenders = summary["first_offenders"]
    assert offenders == [] or all(
        item.get("rule") not in {"Cell", "---"} and item.get("cell") != "operation"
        for item in offenders
    ), offenders[:5]


def test_synthetic_report_is_parsed_exactly():
    """两种格式都要支持，且不得多算：新格式（RULECHECK 行）+ 旧格式（EXECUTED=）。"""
    tiny_new = (
        "RULECHECK FOO.A .................. TOTAL Result Count = 3 (3)\n"
        "RULECHECK BAR.B .................. TOTAL Result Count = 0 (0)\n"
        "TOTAL DRC RuleChecks Executed:   2\n"
        "TOTAL DRC Results Generated:     3 (3)\n"
    )
    summary = parse_drc_report(tiny_new)
    assert summary["by_rule"] == {"FOO.A": 3}
    assert summary["first_offenders"] == []
    assert summary["rules_checked"] == 2
    assert summary["total_results"] == 3

    tiny_old = "TOTAL RULECHECKS EXECUTED = 5\nTOTAL RESULTS GENERATED = 7\n"
    legacy = parse_drc_report(tiny_old)
    assert legacy["rules_checked"] == 5
    assert legacy["total_results"] == 7


def test_real_lvs_report_verdict_is_a_known_value():
    """真实报告写 ``NOT COMPARED``（两词）；解析只截到 ``not`` —— 必须归一为
    ``not_compared``（或 correct/incorrect/unknown），不能把半个词当结论。"""
    summary = parse_lvs_report(LVS_REPORT)
    assert summary["status"] in {"correct", "incorrect", "not_compared", "unknown"} or \
        summary["status"] == "not_comparable"
    assert summary["status"] == "not_compared", summary["status"]


def test_real_lvs_report_counts_table_is_parsed():
    """真实报告的计数是**表格**（`` Ports: 1 4 *``），不是 ``name = n``；
    layout/source 两个数都要能读出来。"""
    summary = parse_lvs_report(LVS_REPORT)
    counts = summary["counts"]
    assert counts.get("ports") == 1 and counts.get("ports_source") == 4, counts
    assert counts.get("nets") == 5 and counts.get("nets_source") == 4, counts


def test_drc_results_db_yields_first_offenders():
    """DRC_RES.db（ASCII）里的坐标多边形要能转成 first_offenders。"""
    offenders = parse_drc_results_db(DRC_DB)
    assert offenders, "db 样本应解析出违规"
    first = offenders[0]
    assert first["rule"] == "NW.A.1"
    assert first["cell"] == "inv"
    assert first["bbox"] == [-395.0, 5780.0, 455.0, 6420.0]
    assert first["count"] == 1
    by_rule = {item["rule"]: item for item in offenders}
    assert by_rule["PO.A.1"]["count"] == 2
    assert by_rule["PO.A.1"]["bbox"] == [0.0, -140.0, 60.0, 340.0]
    assert all(item["cell"] == "inv" for item in offenders)
    assert all(item["rule"] != "Cell" for item in offenders)


def test_drc_results_db_skips_rules_without_polygons_and_caps_limit():
    text = (
        "inv 1000\n"
        "EMPTY.RULE\n"
        "1 1 3 Sep 24 11:13:11 2026\n"
        "EMPTY.RULE { no geometry }\n"
        "A.R.1\n"
        "1 1 3 Sep 24 11:13:11 2026\n"
        "A.R.1 { @ area }\n"
        "p 1 4\n"
        "0 0\n"
        "1 0\n"
        "1 1\n"
        "0 1\n"
        "B.R.2\n"
        "2 2 3 Sep 24 11:13:11 2026\n"
        "B.R.2 { @ area }\n"
        "p 1 4\n"
        "2 2\n"
        "3 2\n"
        "3 3\n"
        "2 3\n"
        "p 2 4\n"
        "5 5\n"
        "6 5\n"
        "6 6\n"
        "5 6\n"
    )
    offenders = parse_drc_results_db(text, limit=1)
    assert [item["rule"] for item in offenders] == ["A.R.1"]
