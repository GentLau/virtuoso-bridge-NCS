"""Run maestro write cases one by one and report open sessions after each."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

spec = importlib.util.spec_from_file_location(
    "maestro_e2e", ROOT / "test" / "live" / "packages" / "maestro_e2e_tests.py")
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

transport = module.HttpTransport()


def sessions() -> str:
    return module._skill(transport, "maeGetSessions()")


print("before:", sessions())
cases = [
    ("WRITE-01 smoke", module._case_write_smoke),
    ("WRITE-02 atomics", module._case_write_atomics),
    ("WRITE-03 var scopes", module._case_write_var_scopes),
    ("WRITE-04 param scopes", module._case_write_parameter_scopes),
    ("WRITE-05 job policy", module._case_write_job_policy_sim_mode),
]
for name, func in cases:
    try:
        func(transport)
        print(name, "PASS ->", sessions())
    except Exception as exc:  # noqa: BLE001
        print(name, "FAIL ->", type(exc).__name__, exc, "sessions:", sessions())
