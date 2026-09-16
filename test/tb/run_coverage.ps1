# Combined coverage for the current tree (see doc/测试覆盖报告.md).
#
# Merges, in one coverage data file:
#   1. offline suites            test/unit + test/integration + test/scenario
#   2. offline TBs               fault_injection / semantics / daemon_log_protocol
#   3. HTTP registration TB      six-step, local mode (full 1-6) and remote 1-4
#   4. HTTP mixed stress TB      Windows client, local + real WSL daemon
#   5. real-machine TBs          Windows -> WSL real Virtuoso five interfaces,
#                                registration steps 1-4, CDS.log matrix,
#                                one-shot channel burst
#
# Prerequisites: ssh alias wsl-gent (real Virtuoso with vb11 + vblog daemons),
# registries under test/tb/artifacts/.  Run from the repository root.
$ErrorActionPreference = 'Stop'
$env:PYTHONPATH = 'src'
python -m coverage erase
python -m coverage run --source=src -m pytest test/unit test/integration test/scenario -q | Out-Null
python -m coverage run --source=src --append test/tb/fault_injection_tb.py | Out-Null
python -m coverage run --source=src --append test/tb/semantics_tb.py | Out-Null
python -m coverage run --source=src --append test/tb/daemon_log_protocol_tb.py | Out-Null
python -m coverage run --source=src --append test/tb/registration_http_six_step_tb.py --work-dir test/tb/artifacts/reg-six-local --user vbsixlocal --local-mode --token vb-six-local | Out-Null
python -m coverage run --source=src --append test/tb/registration_http_six_step_tb.py --work-dir test/tb/artifacts/reg-six-remote --user vbsixremote --daemon-port 65133 --root /home/Gent/.virtuoso-bridge/vbsixremote --stop-after-deploy | Out-Null
python -m coverage run --source=src --append test/tb/http_mixed_stress_tb.py --work-dir test/tb/artifacts/http-stress2 --remote-token vb-vblog --remote-daemon-port 65121 --remote-root /home/Gent/.virtuoso-bridge/vblog --workers 6 --rounds 3 | Out-Null
python -m coverage run --source=src --append test/tb/cov_remote_real.py --work-dir test/tb/artifacts/reg-vb11 --token vb-vb11 | Out-Null
python -m coverage run --source=src --append test/tb/cov_registration_real.py --work-dir test/tb/artifacts/cov-registration --user covreg --token cov-token --port 65112 | Out-Null
python -m coverage run --source=src --append test/tb/log_matrix_real_tb.py --work-dir test/tb/artifacts/log-vblog --token vb-vblog --out test/tb/artifacts/log-matrix-real-green.json | Out-Null
python -m coverage run --source=src --append test/tb/one_shot_burst_tb.py --work-dir test/tb/artifacts/one-shot-burst --token vb-vblog --out test/tb/artifacts/one-shot-burst-green.json | Out-Null
python -m coverage report -m --skip-covered | Out-File -Encoding utf8 test/tb/artifacts/coverage-combined.txt
python -m coverage json -o test/tb/artifacts/coverage-combined.json
python -m coverage report | Select-Object -Last 2
