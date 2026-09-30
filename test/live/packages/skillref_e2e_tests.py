# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-30 11:20
# 依赖: 无
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查（靶机指纹 / 业务面）；②③ 造并校验基线；④ 只做被测动作；
# ⑤ 读回比对（期望/实际入证据）；⑥ 跑完不清理现场。某步不适用时正文有注释说明。
"""End-to-end acceptance tests for ``virtuoso.skillref.*``.

Run with ``--transport direct`` (in-process dispatch) or ``--transport http``
(the 8127 business face).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"
WORK_DIR = ROOT / "test" / "artifacts" / "env" / "log-vblog"
LOCAL_DOC_ROOT = r"C:\Users\user\Desktop\doc"
REMOTE_DOC_ROOT = "/opt/eda/cadence/IC618/doc"


class HttpTransport:
    middle = None

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            API, data=body, headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=900) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return json.loads(error.read().decode("utf-8"))


class DirectTransport:
    def __init__(self) -> None:
        from common import config as config_base
        from common.paths import config_path, init_work_dir
        from server import dispatch
        from server.api_server import register_packages
        from transport.middle import BusinessServer

        init_work_dir(str(WORK_DIR))
        config_base.init_config(config_path())
        register_packages()
        self.dispatch = dispatch
        self.middle = BusinessServer()

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        status, body = self.dispatch.dispatch(self.middle, payload)
        if status not in (200, 400):
            raise AssertionError(f"dispatch status {status}: {body}")
        return body


def _op(transport, operation: str, **fields: Any) -> Any:
    response = transport.call({"operation": operation, "token": TOKEN, **fields})
    if not response.get("ok"):
        raise AssertionError(f"{operation} failed: {response.get('error')}")
    return response


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _search(transport, **fields: Any) -> dict[str, Any]:
    return _op(transport, "virtuoso.skillref.search", **fields)


def _info(transport, **fields: Any) -> dict[str, Any]:
    return _op(transport, "virtuoso.skillref.info", **fields)


def _case_search_local(transport) -> None:
    """SEARCH-01：四档检索的**内容**判据（round9 W-2 补强，原用例只验"命中非空"）。

    期望（实测基准：`C:\\Users\\user\\Desktop\\doc`）：

    * `search_in=name` → 只跑 name 层，命中 `dbOpenCellViewByType`（`skdfref.fnd`），字段齐全；
    * `search_in=entry` / `topic` → 层集合**累积**（name+entry / name+entry+topic），
      且各自出现过对应层的命中；
    * `search_in=body` + `under=["cpf_ref"]` → 命中层为 body、`why` 标出原因、未被截断。
    """
    def _hits(**fields: Any) -> dict[str, Any]:
        value = _search(transport, source="local", doc_root=LOCAL_DOC_ROOT, **fields)
        hits = value.get("results") or []
        _check(hits, f"{fields.get('search_in')} search empty: {value}")
        for hit in hits:
            _check(isinstance(hit.get("name"), str) or hit.get("layer") == "body",
                   f"命中缺少 name 且不是 body 层: {hit}")
            _check(isinstance(hit.get("why"), list) and hit["why"],
                   f"命中缺少 why（判据来源）: {hit}")
            _check(float(hit.get("score") or 0) > 0, f"命中 score 非正: {hit}")
        return value

    by_name = _hits(query="dbOpenCellView", search_in="name")
    top = (by_name.get("results") or [{}])[0]
    _check(by_name.get("layers_run") == ["name"],
           f"name 档层集合应为 ['name']: {by_name.get('layers_run')}")
    _check(top.get("name") == "dbOpenCellViewByType",
           f"name 档首条命中应为 dbOpenCellViewByType: {top.get('name')!r}")
    _check(top.get("source_file") == "skdfref.fnd",
           f"命中来源文件应可点开: {top.get('source_file')!r}")
    _check(top.get("syntax") and top.get("description"),
           f"命中缺 syntax/description: {top}")

    by_entry = _hits(query="dbOpenCellView", search_in="entry")
    _check(set(by_entry.get("layers_run") or []) == {"name", "entry"},
           f"entry 档层集合应为 name+entry: {by_entry.get('layers_run')}")
    _check(any(h.get("layer") == "entry" for h in by_entry["results"]),
           f"entry 档未出现 entry 层命中: {[h.get('layer') for h in by_entry['results']]}")

    by_topic = _hits(query="dbOpenCellView", search_in="topic")
    _check(set(by_topic.get("layers_run") or []) == {"name", "entry", "topic"},
           f"topic 档层集合应为三层: {by_topic.get('layers_run')}")
    _check(any(h.get("layer") == "topic" for h in by_topic["results"]),
           f"topic 档未出现 topic 层命中: {[h.get('layer') for h in by_topic['results']]}")

    by_body = _hits(query="ground bounce", search_in="body", under=["cpf_ref"])
    _check(set(by_body.get("layers_run") or []) == {"name", "entry", "topic", "body"},
           f"body 档层集合应为四层: {by_body.get('layers_run')}")
    _check(any(h.get("layer") == "body" for h in by_body["results"]),
           f"body 档未出现 body 层命中: {[h.get('layer') for h in by_body['results']]}")
    _check(by_body.get("truncated") is False, f"body 档意外截断: {by_body.get('truncated')}")


def _case_search_modes(transport) -> None:
    exact = _search(
        transport, source="local", doc_root=LOCAL_DOC_ROOT,
        query="dbOpenCellViewByType", search_in="name", mode="exact",
    )
    hits = exact.get("results") or []
    _check(any(
        "dbOpenCellViewByType" in str(item) for item in hits
    ), f"exact search misses exact name: {exact}")
    unknown = _search(
        transport, source="local", doc_root=LOCAL_DOC_ROOT,
        query="zzNoSuchSkillFunctionQq", search_in="name",
    )
    _check(not (unknown.get("results") or []),
           f"unknown query must be empty: {unknown}")


def _case_info_local(transport) -> None:
    found = _info(
        transport, source="local", doc_root=LOCAL_DOC_ROOT,
        name="dbOpenCellViewByType",
    )
    _check(found.get("found") is True, f"info found: {found}")
    markdown = found.get("plain_text") or ""
    _check("dbOpenCellViewByType" in markdown, "info content missing")
    missing = _info(
        transport, source="local", doc_root=LOCAL_DOC_ROOT,
        name="zzNoSuchSkillFunctionQq",
    )
    _check(missing.get("found") is False, f"missing info found flag: {missing}")


def _case_remote(transport) -> None:
    value = _search(
        transport, source="remote", doc_root=REMOTE_DOC_ROOT,
        query="dbOpenCellView", search_in="name",
    )
    hits = value.get("results") or []
    _check(hits, f"remote search empty: {value}")
    found = _info(
        transport, source="remote", doc_root=REMOTE_DOC_ROOT,
        name="dbOpenCellViewByType",
    )
    _check(found.get("found") is True, f"remote info: {found}")


def _case_errors(transport) -> None:
    response = transport.call({
        "operation": "virtuoso.skillref.search", "token": TOKEN,
        "source": "local", "doc_root": r"Z:\no\such\docroot",
        "query": "whatever",
    })
    _check(not response.get("ok"), "missing doc root must fail")
    # 2026-09-30 加强：原来只判 not ok —— 现在断言失败**原因**（文档根下找不到 finder/SKILL），
    # 并点名那个不存在的 doc_root，避免"任何失败都算过"。
    doc_error = str(response.get("error") or "")
    _check("no\\such\\docroot" in doc_error or "no/such/docroot" in doc_error
           or "docroot" in doc_error,
           f"错误文案必须点名 doc_root（实测 {doc_error!r}）")
    _check("finder" in doc_error or "SKILL" in doc_error,
           f"错误文案必须说明缺什么（finder/SKILL，实测 {doc_error!r}）")
    bad_source = transport.call({
        "operation": "virtuoso.skillref.search", "token": TOKEN,
        "source": "mars", "query": "whatever",
    })
    _check(not bad_source.get("ok"), "invalid source must fail")
    source_error = str(bad_source.get("error") or "")
    _check("source must be one of" in source_error,
           f"非法 source 必须给出取值域（实测 {source_error!r}）")


def _case_params(transport) -> None:
    """SEARCH-03 / INFO-02：limit / max_files / snippet / max_candidates / include_raw。"""
    name_base = dict(source="local", doc_root=LOCAL_DOC_ROOT, query="dbOpenCellView",
                     search_in="name")
    one = _search(transport, limit=1, timeout=60, **name_base)
    hits1 = one.get("results") or []
    _check(len(hits1) == 1, f"limit=1 must cap results: {one}")
    five = _search(transport, limit=5, timeout=60, **name_base)
    hits5 = five.get("results") or []
    _check(1 <= len(hits5) <= 5, f"limit=5 cap: {len(hits5)}")

    # snippet：body 层命中带 snippet；False 时必须剥掉该字段
    body = dict(source="local", doc_root=LOCAL_DOC_ROOT, query="ground bounce",
                search_in="body", under=["cpf_ref"])
    with_snip = _search(transport, snippet=True, limit=5, timeout=120, **body)
    body_hits = with_snip.get("results") or []
    _check(any(h.get("snippet") for h in body_hits),
           f"default snippet=True must produce snippets: {body_hits[:1]}")
    nosnip = _search(transport, snippet=False, limit=5, timeout=120, **body)
    _check((nosnip.get("results") or [])
           and all("snippet" not in h for h in nosnip["results"]),
           "snippet=False must drop snippet fields")

    # max_files：本地扫描上限（max_files=1 → scanned_files ≤ 1）
    capped = _search(transport, max_files=1, limit=50, timeout=120, **body)
    _check(int(capped.get("scanned_files") or 0) <= 1,
           f"max_files=1 must cap scanned files: {capped.get('scanned_files')}")

    # max_candidates：远端 grep 候选上限（看 body-grep step 的 candidates）
    remote_base = dict(source="remote", doc_root=REMOTE_DOC_ROOT,
                       query="dbOpenCellView", search_in="body")
    cap1 = _search(transport, max_candidates=1, limit=50, timeout=240, **remote_base)
    step1 = next((s for s in cap1.get("steps") or [] if s.get("name") == "body-grep"), {})
    cand1 = int((step1.get("detail") or {}).get("candidates") or 0)
    _check(cand1 <= 1, f"max_candidates=1 must cap grep: {step1}")
    full = _search(transport, max_candidates=50, limit=50, timeout=240, **remote_base)
    step2 = next((s for s in full.get("steps") or [] if s.get("name") == "body-grep"), {})
    cand50 = int((step2.get("detail") or {}).get("candidates") or 0)
    _check(cand50 >= cand1, f"max_candidates=50 must not cap below 1: {step2}")

    # include_raw：原始 HTML 只在显式要求时返回
    with_raw = _info(transport, source="local", doc_root=LOCAL_DOC_ROOT,
                     name="dbOpenCellViewByType", include_raw=True, timeout=60)
    _check(bool(with_raw.get("raw_html")),
           "include_raw=True must return raw_html")
    without_raw = _info(transport, source="local", doc_root=LOCAL_DOC_ROOT,
                        name="dbOpenCellViewByType", include_raw=False, timeout=60)
    _check(not without_raw.get("raw_html"),
           "include_raw=False must omit raw_html")


def run_suite(transport) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []

    def run(name: str, func: Callable[[], Any]) -> None:
        try:
            func()
            results.append((name, "PASS"))
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            raise

    run("SEARCH-01 local four levels", lambda: _case_search_local(transport))
    run("SEARCH-02 modes + unknown", lambda: _case_search_modes(transport))
    run("INFO-01 local found/missing", lambda: _case_info_local(transport))
    run("SEARCH/INFO-02 remote", lambda: _case_remote(transport))
    run("SEARCH/INFO-03 params", lambda: _case_params(transport))
    run("ERR-01 bad source/root", lambda: _case_errors(transport))
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("direct", "http"), default="http",
                        help="direct=故障定位/覆盖率；真机判据必须 http")
    args = parser.parse_args()
    transport = HttpTransport() if args.transport == "http" else DirectTransport()
    try:
        results = run_suite(transport)
    finally:
        middle = getattr(transport, "middle", None)
        if middle is not None:
            middle.close()
    for name, status in results:
        print(f"{status:6}  {name}")
    return 0 if results and all(status == "PASS" for _, status in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
