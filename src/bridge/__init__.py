"""Bottom layer: Virtuoso daemon resources and deployment helpers."""
from pathlib import Path


def resources_dir() -> Path:
    return Path(__file__).with_name("resources")


__all__ = ["resources_dir"]
