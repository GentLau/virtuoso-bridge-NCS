"""Top-level ``server`` package.

Currently hosts the registration HTTP server (setup phase).  The long-running
business/API top layer will live here later.

Use ``python -m server.registration_server`` or
``from server.registration_server import main``.
"""

from __future__ import annotations

from typing import Any

__all__ = ["main"]


def __getattr__(name: str) -> Any:
    if name == "main":
        from server.registration_server import main
        return main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
