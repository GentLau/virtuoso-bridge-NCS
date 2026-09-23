"""Shared pytest fixtures for the offline suites.

The offline tests create work dirs with ``tempfile.mkdtemp(prefix="vb-")``
(the bridge's working-directory contract).  Nothing in the *production* code
owns those dirs, so this fixture removes the ``vb-*`` dirs created during the
run once the whole session finishes.

Scope is **session**, not per-test: several test classes create their work dir
in ``setUpClass`` and keep using it across methods — a per-test sweep would
delete it under them.  Only ``vb-*`` entries that appeared *after* the session
started are removed, so other tools' temp files are never touched.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest


def _vb_dirs() -> set[Path]:
    root = Path(tempfile.gettempdir())
    try:
        return {p for p in root.glob("vb-*") if p.is_dir()}
    except OSError:  # pragma: no cover - unreadable temp dir
        return set()


@pytest.fixture(autouse=True, scope="session")
def _cleanup_vb_temp_dirs():
    before = _vb_dirs()
    yield
    for path in _vb_dirs() - before:
        shutil.rmtree(path, ignore_errors=True)
