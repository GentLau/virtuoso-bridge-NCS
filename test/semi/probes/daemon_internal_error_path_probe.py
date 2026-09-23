"""Which handler does a ValueError from ``_read_frame`` actually reach?

``test_daemon_runtime_contracts.py::test_internal_value_error_is_reported_to_the_traceback_only``
expects the daemon to stay silent for ``ValueError`` (the
``except (UnicodeDecodeError, ValueError)`` branch) but the daemon sends a NACK
frame with ``internal daemon error`` (the generic ``except Exception`` branch).

Exactly one of the two is wrong, and the two have very different consequences:

* test wrong  -> the test asserts behaviour the spec never had;
* source wrong -> a ValueError is being re-wrapped somewhere, so the
  "malformed input is dropped silently" contract does not hold, and the
  defensive branch at ``ramic_bridge_daemon_3.py:462`` is dead code.

This probe prints the exception type each handler actually saw, plus the bytes
that reached the socket.

    python test/semi/probes/daemon_internal_error_path_probe.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import traceback as real_traceback
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    tests = _load("daemon_runtime_tests", ROOT / "test/offline/unit/test_daemon_runtime_contracts.py")
    verdicts = []
    for variant in tests.VARIANTS:
        mod = tests.MODULES[variant]
        conn = tests.FakeConn(json.dumps(tests.request(log_level="off")).encode())
        seen: list[str] = []
        # Capture the real printer *before* patching: patching
        # ``mod.traceback.print_exc`` also patches the module-level
        # ``real_traceback`` reference (same module object), which recurses.
        original_print_exc = mod.traceback.print_exc

        def spy(_seen=seen):
            _seen.append(sys.exc_info()[0].__name__)
            original_print_exc()

        with mock.patch.object(mod, "_read_frame", side_effect=ValueError("bad frame")), \
                mock.patch.object(mod.traceback, "print_exc", spy):
            mod.handle_connection(conn)
        sent = bytes(conn.sent)
        verdicts.append({
            "variant": variant,
            "exception_types_seen": seen,
            "bytes_sent": sent.decode("utf-8", errors="replace"),
        })
        print(f"[{variant}] handler saw {seen} -> sent {sent!r}")

    # Expected when the silent-ValueError contract holds: no bytes at all.
    silent = all(not item["bytes_sent"] for item in verdicts)
    print("VERDICT:", "contract holds (test is wrong)" if silent
          else "NACK sent for ValueError (source branch is bypassed)")
    return 0 if silent else 1


if __name__ == "__main__":
    raise SystemExit(main())
