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
WORK_DIR = ROOT / "test" / "artifacts" / "log-vblog"
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
    return response["data"]


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _search(transport, **fields: Any) -> dict[str, Any]:
    return _op(transport, "virtuoso.skillref.search", **fields)


def _info(transport, **fields: Any) -> dict[str, Any]:
    return _op(transport, "virtuoso.skillref.info", **fields)


def _case_search_local(transport) -> None:
    for search_in, query in (
        ("name", "dbOpenCellView"),
        ("entry", "dbOpenCellView"),
        ("topic", "dbOpenCellView"),
    ):
        value = _search(
            transport, source="local", doc_root=LOCAL_DOC_ROOT,
            query=query, search_in=search_in,
        )
        hits = value.get("results") or []
        _check(hits, f"{search_in} search empty: {value}")
    body = _search(
        transport, source="local", doc_root=LOCAL_DOC_ROOT,
        query="ground bounce", search_in="body", under=["cpf_ref"],
    )
    hits = body.get("results") or []
    _check(hits, f"body search empty: {body}")


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
    bad_source = transport.call({
        "operation": "virtuoso.skillref.search", "token": TOKEN,
        "source": "mars", "query": "whatever",
    })
    _check(not bad_source.get("ok"), "invalid source must fail")


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
    run("ERR-01 bad source/root", lambda: _case_errors(transport))
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("direct", "http"), default="direct")
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
