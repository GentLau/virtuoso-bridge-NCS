"""Upper-layer business packages.

The production registry in :mod:`server.api_server` explicitly imports the
packages it wants.  This module must not eagerly import every package: that
would defeat per-package failure isolation and load non-production examples.
"""

__all__: list[str] = []
