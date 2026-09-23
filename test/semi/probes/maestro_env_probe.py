"""Probe the WSL-Gent environment for maestro TB material.

Reports: libraries and their paths, cells that already carry a maestro view,
simulator availability, and the remote home layout.

    python test/semi/probes/maestro_env_probe.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _maestro_tb import data, shell, skill, unquote  # noqa: E402


def libs_and_paths():
    code = (
        'let((out) out = "" '
        'foreach(l ddGetLibList() '
        '  out = strcat(out sprintf(nil "%s|%s\\n" l~>name l~>readPath))) '
        "out)"
    )
    ok, out, err = skill(code)
    print("== libraries ==", ok, err)
    print(unquote(out))


def maestro_views():
    """Any cell that already has a view named 'maestro'."""
    code = (
        'let((out) out = "" '
        'foreach(l ddGetLibList() '
        "  foreach(c l~>cells "
        "    foreach(v c~>views "
        '      when(v~>name == "maestro" '
        '        out = strcat(out sprintf(nil "%s/%s/%s\\n" l~>name c~>name v~>name)))))) '
        "out)"
    )
    ok, out, err = skill(code)
    print("== existing maestro views ==", ok, err)
    print(unquote(out) or "(none)")


def schematic_inventory():
    """Cells that have a schematic view (candidate DUTs for a TB)."""
    code = (
        'let((out) out = "" '
        'foreach(l ddGetLibList() '
        "  foreach(c l~>cells "
        "    foreach(v c~>views "
        '      when(v~>name == "schematic" '
        '        out = strcat(out sprintf(nil "%s/%s\\n" l~>name c~>name)))))) '
        "out)"
    )
    ok, out, err = skill(code)
    print("== cells with schematic view ==", ok, err)
    text = unquote(out)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    print("\n".join(lines[:60]))
    print(f"(total {len(lines)})")


def remote_layout():
    rc, out, err = shell(
        "echo HOME=$HOME; ls -d ~/* 2>/dev/null | head -20; "
        "echo ---project---; ls /home/Gent/project 2>/dev/null | head -20; "
        "echo ---models---; ls /home/Gent/models /opt/eda/models 2>/dev/null | head -20"
    )
    print("== remote layout ==", rc, err.strip())
    print(out)


def library_cells(lib_name: str, limit: int = 200):
    code = (
        f'let((out l) l = ddGetObj("{lib_name}") out = "" '
        'when(l foreach(c l~>cells out = strcat(out c~>name " "))) '
        "out)"
    )
    ok, out, err = skill(code)
    names = unquote(out).split()
    print(f"== {lib_name} cells ({len(names)}) ==", ok, err)
    print(" ".join(names[:limit]))
    print()


def cell_views(lib_name: str, cell_name: str):
    code = (
        f'let((out c) c = ddGetObj("{lib_name}" "{cell_name}") out = "" '
        'when(c foreach(v c~>views out = strcat(out v~>name " "))) '
        "out)"
    )
    ok, out, err = skill(code)
    print(f"== views of {lib_name}/{cell_name} ==", ok, unquote(out), err)


def main():
    libs_and_paths()
    maestro_views()
    schematic_inventory()
    remote_layout()
    print("== paths.facts ==")
    print(str(data("demo.paths.facts"))[:800])
    for lib in ("ahdlLib", "analogLib", "functional", "rfExamples"):
        library_cells(lib)


if __name__ == "__main__":
    main()
