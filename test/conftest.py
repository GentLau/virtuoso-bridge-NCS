"""Shared pytest fixtures for the offline suites.

The offline tests create per-test work dirs with ``tempfile.mkdtemp()`` (the
bridge's working-directory contract).  Nothing in the *production* code owns
those dirs, so this fixture removes the ``vb-*`` dirs a test created once that
test finishes — keeping ``%TEMP%`` clean without touching other tools' files.
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


@pytest.fixture(autouse=True)
def _cleanup_vb_temp_dirs():
    before = _vb_dirs()
    yield
    for path in _vb_dirs() - before:
        shutil.rmtree(path, ignore_errors=True)
