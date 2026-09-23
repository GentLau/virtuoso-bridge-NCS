"""P1 live CDS.log delta contract against a real Virtuoso daemon."""
import subprocess, sys, tempfile, time, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from _win import no_window  # noqa: E402  (hide Windows consoles for ssh/scp)

from transport.middle import BusinessServer
from common.registry import UserEntry, load_registry
from register.probe import allocate_local_port
from common.paths import override_work_dir_for_tests, registry_path

def build_entry(level):
    wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))
    reg = load_registry(registry_path())
    e = UserEntry(token="vb-vb01", mode="remote")
    e.roles.daemon.host = "wsl-gent"; e.roles.daemon.daemon_port = 65101
    e.roles.daemon.local_port = allocate_local_port()
    e.roles.command.host = "wsl-gent"; e.roles.command.user = "Gent"
    e.roles.daemon.root = "/home/Gent/.virtuoso-bridge/vb01"
    e.roles.daemon.expected_user = "Gent"
    e.cdslog.log_level = level
    reg.register("vb01", e)
    return BusinessServer(wd)

marker = "VB-E2E-" + uuid.uuid4().hex[:12]
allm = build_entry("all")
r = allm.execute_skill(f'progn(hiPrintToLogFile("{marker}") 1+1)', token="vb-vb01", timeout=60)
print("all-write:", r.status, r.output, "marker_in_log=", marker in r.log, "log_len=", len(r.log))
r2 = allm.execute_skill("1+1", token="vb-vb01", timeout=60)
print("all-noop-log-empty:", r2.log == "", repr(r2.log))

offm = build_entry("off")
r3 = offm.execute_skill(f'progn(hiPrintToLogFile("{marker}") 1+1)', token="vb-vb01", timeout=60)
print("off:", r3.status, r3.output, "log_empty=", r3.log == "")

out = subprocess.run(["ssh","wsl-gent", f'grep -c "VB-BEGIN\\|VB-END" /home/Gent/project/vb01/CDS.log || true'], capture_output=True, text=True, **no_window()).stdout.strip()
print("CDS.log bridge-marker count:", out)
for m in [allm, offm]:
    for c in list(m._clients.values()):
        try: c.close()
        except Exception: pass
