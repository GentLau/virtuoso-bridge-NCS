"""In-process probe for pyapi.packages.maestro (before HTTP registration)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from common.paths import init_work_dir  # noqa: E402
from pyapi.packages import maestro  # noqa: E402
from transport.middle import BusinessServer  # noqa: E402


def main() -> int:
    init_work_dir(str(ROOT / "test" / "artifacts" / "log-vblog"))
    middle = BusinessServer()
    pkg = maestro.Package(middle)
    token = "vb-vblog"
    mode = sys.argv[1] if len(sys.argv) > 1 else "history"

    if mode == "config":
        result = pkg.read_config(maestro.ReadConfigRequest(
            token=token, library="maestro_tb", cell="rc_probe",
        ))
    elif mode == "config-cell":
        result = pkg.read_config(maestro.ReadConfigRequest(
            token=token, library=sys.argv[2], cell=sys.argv[3],
        ))
    elif mode == "history":
        result = pkg.read_history(maestro.ReadHistoryRequest(
            token=token, library="maestro_tb", cell="rc_probe",
        ))
    elif mode == "history-detail":
        result = pkg.read_history(maestro.ReadHistoryRequest(
            token=token, library="maestro_tb", cell="rc_probe",
            history=sys.argv[2] if len(sys.argv) > 2 else "Interactive.4",
        ))
    elif mode == "history-cell":
        result = pkg.read_history(maestro.ReadHistoryRequest(
            token=token, library=sys.argv[2], cell=sys.argv[3],
            history=sys.argv[4] if len(sys.argv) > 4 else None,
        ))
    elif mode == "results":
        result = pkg.read_results(maestro.ReadResultsRequest(
            token=token, library="maestro_tb", cell="rc_probe",
            history=sys.argv[2] if len(sys.argv) > 2 else "Interactive.4",
        ))
    elif mode == "results-cell":
        result = pkg.read_results(maestro.ReadResultsRequest(
            token=token, library=sys.argv[2], cell=sys.argv[3],
            history=sys.argv[4] if len(sys.argv) > 4 else None,
            test=sys.argv[5] if len(sys.argv) > 5 else None,
        ))
    elif mode == "write-smoke":
        result = pkg.write(maestro.WriteRequest(
            token=token,
            library="maestro_tb",
            cell="rc_probe",
            commands=[
                {"op": "set_var", "name": "vprobe", "value": "1.25"},
                {
                    "op": "add_output",
                    "test": "ac",
                    "name": "out_probe",
                    "output_type": "point",
                    "expr": "out",
                },
                {
                    "op": "set_spec",
                    "test": "ac",
                    "name": "out_probe",
                    "gt": "0",
                },
            ],
        ))
    elif mode == "write-cleanup":
        result = pkg.write(maestro.WriteRequest(
            token=token,
            library="maestro_tb",
            cell="rc_probe",
            commands=[
                {"op": "delete_output", "test": "ac", "name": "out_probe",
                 "delete_spec": True},
                {"op": "delete_var", "name": "vprobe"},
            ],
        ))
    elif mode == "run":
        result = pkg.run(maestro.RunRequest(
            token=token,
            library="maestro_tb",
            cell="rc_probe",
            blocking=(len(sys.argv) > 2 and sys.argv[2] == "blocking"),
            timeout=180,
            poll_interval=1.0,
        ))
    elif mode == "run-cell":
        result = pkg.run(maestro.RunRequest(
            token=token,
            library=sys.argv[2],
            cell=sys.argv[3],
            blocking=(len(sys.argv) > 4 and sys.argv[4] == "blocking"),
            timeout=300,
            poll_interval=1.0,
        ))
    elif mode == "open-gui":
        result = pkg.open_gui(maestro.OpenGuiRequest(
            token=token, library=sys.argv[2], cell=sys.argv[3],
        ))
    elif mode == "close-gui":
        result = pkg.close_gui(maestro.CloseGuiRequest(
            token=token, library=sys.argv[2], cell=sys.argv[3],
        ))
    elif mode == "wave-gui":
        result = pkg.open_waveform_gui(maestro.OpenWaveformRequest(
            token=token,
            library=sys.argv[2],
            cell=sys.argv[3],
            history=sys.argv[4],
            test=sys.argv[5] if sys.argv[5] != "-" else None,
            analysis=sys.argv[6] if sys.argv[6] != "-" else None,
            signals=sys.argv[7:],
        ))
    elif mode == "close-wave-gui":
        result = pkg.close_waveform_gui(maestro.CloseWaveformRequest(
            token=token,
            session=sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else None,
            window=sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != "-" else None,
        ))
    elif mode == "wave":
        result = pkg.read_results(maestro.ReadResultsRequest(
            token=token,
            library="maestro_tb",
            cell="rc_probe",
            history=sys.argv[2] if len(sys.argv) > 2 else "Interactive.6",
            test="ac",
            analysis="ac",
            waveform=sys.argv[3] if len(sys.argv) > 3 else "out",
            result=sys.argv[4] if len(sys.argv) > 4 else None,
            output_path=str(
                ROOT / "test" / "artifacts" / "maestro-tb" / "probe-wave.txt"
            ),
        ))
    elif mode == "wave-cell":
        result = pkg.read_results(maestro.ReadResultsRequest(
            token=token,
            library=sys.argv[2],
            cell=sys.argv[3],
            history=sys.argv[4],
            test=sys.argv[5],
            analysis=sys.argv[6],
            waveform=sys.argv[7],
            result=sys.argv[8] if len(sys.argv) > 8 else None,
            output_path=str(
                ROOT / "test" / "artifacts" / "maestro-tb"
                / f"wave-{sys.argv[3]}-{sys.argv[7].replace('/', '_')}.txt"
            ),
        ))
    elif mode == "export-csv":
        result = pkg.export(maestro.ExportRequest(
            token=token, library="maestro_tb", cell="rc_probe",
            kind="outputs_csv",
            history=sys.argv[2] if len(sys.argv) > 2 else "Interactive.6",
            test="ac",
        ))
    elif mode == "export-script":
        result = pkg.export(maestro.ExportRequest(
            token=token, library="maestro_tb", cell="rc_probe",
            kind="script",
        ))
    elif mode == "export-netlist":
        result = pkg.export(maestro.ExportRequest(
            token=token, library="maestro_tb", cell="rc_probe",
            kind="netlist", test="ac", corner="Nominal",
        ))
    elif mode == "export-snapshot":
        result = pkg.export(maestro.ExportRequest(
            token=token, library="maestro_tb", cell="rc_probe",
            kind="snapshot",
            history=sys.argv[2] if len(sys.argv) > 2 else "Interactive.6",
        ))
    elif mode == "export-screenshot":
        result = pkg.export(maestro.ExportRequest(
            token=token, library="maestro_tb", cell=sys.argv[2],
            kind="screenshot",
        ))
    elif mode == "history-rename":
        result = pkg.write_history(maestro.WriteHistoryRequest(
            token=token, library="maestro_tb", cell="rc_probe",
            commands=[{
                "op": "rename",
                "history": sys.argv[2],
                "new_name": sys.argv[3],
            }],
        ))
    elif mode == "history-delete":
        result = pkg.write_history(maestro.WriteHistoryRequest(
            token=token, library="maestro_tb", cell="rc_probe",
            commands=[{"op": "delete", "history": sys.argv[2]}],
        ))
    elif mode == "history-lock":
        result = pkg.write_history(maestro.WriteHistoryRequest(
            token=token, library="maestro_tb", cell="rc_probe",
            commands=[{"op": sys.argv[3] if len(sys.argv) > 3 else "lock",
                       "history": sys.argv[2]}],
        ))
    elif mode == "history-delete-results":
        result = pkg.write_history(maestro.WriteHistoryRequest(
            token=token, library="maestro_tb", cell="rc_probe",
            commands=[{
                "op": "delete_results",
                "history": sys.argv[2],
                "keep_netlist": True,
                "keep_quick_plot": True,
            }],
        ))
    else:
        raise SystemExit(f"unknown mode: {mode}")

    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2, default=str))
    middle.close()
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
