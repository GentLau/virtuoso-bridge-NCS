# Combined coverage + acceptance gate for the current tree.
#
# Every step is fail-fast: a red TB aborts the run instead of producing a
# green-looking coverage report.
#
#   powershell -NoProfile -File test/tb/run_coverage.ps1                     # local+WSL real daemons
#   powershell -NoProfile -File test/tb/run_coverage.ps1 -IncludeExtended    # + WSL client + saturation
#
# Prerequisites
#   * ssh alias ``wsl-gent`` (real Virtuoso with the vb11 + vblog daemons)
#   * registries under test/tb/artifacts/
#   * for -IncludeExtended: WSL venv ~/.vb-test/venv with paramiko installed
param(
    [switch]$IncludeExtended = $false,
    [string]$WslHost = 'wsl-gent',
    [int]$FailUnder = 80,
    # Escape hatch for a shared workspace only: temporary WIP files that do not
    # collect yet.  A submission run MUST NOT pass this parameter.
    [string[]]$SkipTests = @()
)

$ErrorActionPreference = 'Stop'
# Native (python/pytest) non-zero exits must abort, otherwise a red TB would
# still produce a green-looking coverage report.
$PSNativeCommandUseErrorActionPreference = $true
$env:PYTHONPATH = 'src'

function Invoke-Step {
    param([string]$Label, [scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "acceptance step failed: $Label (exit $LASTEXITCODE)"
    }
}

# ---- offline suites and TBs ------------------------------------------------------
Invoke-Step 'coverage erase' { python -m coverage erase }
$ignoreArgs = @()
foreach ($path in $SkipTests) { $ignoreArgs += "--ignore=$path" }
Invoke-Step 'offline suites' { python -m coverage run --source=src -m pytest test/unit test/integration test/scenario -q @ignoreArgs | Out-Null }
Invoke-Step 'fault injection TB' { python -m coverage run --source=src --append test/tb/fault_injection_tb.py --out test/tb/artifacts/fault-injection-green.json | Out-Null }
Invoke-Step 'semantics TB' { python -m coverage run --source=src --append test/tb/semantics_tb.py --out test/tb/artifacts/semantics-green.json | Out-Null }
Invoke-Step 'daemon log protocol TB' { python -m coverage run --source=src --append test/tb/daemon_log_protocol_tb.py --out test/tb/artifacts/log-protocol.json | Out-Null }

# ---- registration over the real HTTP API ----------------------------------------
Invoke-Step 'registration 1-6 (local)' { python -m coverage run --source=src --append test/tb/registration_http_six_step_tb.py --work-dir test/tb/artifacts/reg-six-local --user vbsixlocal --local-mode --token vb-six-local --out test/tb/artifacts/reg-six-local/evidence.json | Out-Null }
Invoke-Step 'registration 1-4 (remote)' { python -m coverage run --source=src --append test/tb/registration_http_six_step_tb.py --work-dir test/tb/artifacts/reg-six-remote-14 --user vbsixremote --daemon-port 65133 --root /home/Gent/.virtuoso-bridge/vbsixremote --stop-after-deploy --out test/tb/artifacts/reg-six-remote-14/evidence.json | Out-Null }

# ---- HTTP mixed workload (Windows client) ---------------------------------------
Invoke-Step 'http mixed stress (windows)' { python -m coverage run --source=src --append test/tb/http_mixed_stress_tb.py --work-dir test/tb/artifacts/http-stress2 --remote-token vb-vblog --remote-daemon-port 65121 --remote-root /home/Gent/.virtuoso-bridge/vblog --workers 6 --rounds 6 --out test/tb/artifacts/http-stress2/evidence.json | Out-Null }

# ---- real machine TBs -------------------------------------------------------------
Invoke-Step 'real five interfaces' { python -m coverage run --source=src --append test/tb/cov_remote_real.py --work-dir test/tb/artifacts/reg-vb11 --token vb-vb11 | Out-Null }
Invoke-Step 'real registration 1-4' { python -m coverage run --source=src --append test/tb/cov_registration_real.py --work-dir test/tb/artifacts/cov-registration --user covreg --token cov-token --port 65112 | Out-Null }
Invoke-Step 'real CDS.log matrix' { python -m coverage run --source=src --append test/tb/log_matrix_real_tb.py --work-dir test/tb/artifacts/log-vblog --token vb-vblog --out test/tb/artifacts/log-matrix-real-green.json | Out-Null }
Invoke-Step 'one-shot channel burst' { python -m coverage run --source=src --append test/tb/one_shot_burst_tb.py --work-dir test/tb/artifacts/one-shot-burst --token vb-vblog --out test/tb/artifacts/one-shot-burst-green.json | Out-Null }

# ---- extended: WSL client equivalence + saturation -------------------------------
if ($IncludeExtended) {
    Invoke-Step 'sync tree to WSL' {
        tar -czf wsl_sync.tgz src test/tb
        scp -q wsl_sync.tgz "${WslHost}:/home/Gent/.vb-test/"
        ssh $WslHost 'rm -rf /home/Gent/.vb-test/repo2 && mkdir -p /home/Gent/.vb-test/repo2 && tar -xzf /home/Gent/.vb-test/wsl_sync.tgz -C /home/Gent/.vb-test/repo2'
        Remove-Item wsl_sync.tgz -Force
    }
    Invoke-Step 'http mixed stress (wsl client)' {
        ssh $WslHost 'cd /home/Gent/.vb-test/repo2 && rm -rf /tmp/vb-wsl-stress && mkdir -p /tmp/vb-wsl-stress && PYTHONPATH=src /home/Gent/.vb-test/venv/bin/python test/tb/http_mixed_stress_tb.py --work-dir /tmp/vb-wsl-stress --remote-host localhost --remote-token vb-vblog --remote-daemon-port 65121 --remote-root /home/Gent/.virtuoso-bridge/vblog --workers 6 --rounds 6 --out /tmp/vb-wsl-stress/evidence.json'
        scp -q "${WslHost}:/tmp/vb-wsl-stress/evidence.json" test/tb/artifacts/http-stress-wsl-client.json
    }
    Invoke-Step 'saturation profile' { python -m coverage run --source=src --append test/tb/http_mixed_stress_tb.py --work-dir test/tb/artifacts/http-stress-sat --remote-token vb-vblog --remote-daemon-port 65121 --remote-root /home/Gent/.virtuoso-bridge/vblog --workers 24 --rounds 3 --local-pool 4 --max-attempts 60 --out test/tb/artifacts/http-stress-sat/evidence.json | Out-Null }
}

# ---- coverage report --------------------------------------------------------------
Invoke-Step 'coverage text report' { python -m coverage report -m --skip-covered | Out-File -Encoding utf8 test/tb/artifacts/coverage-combined.txt }
Invoke-Step 'coverage json report' { python -m coverage json -o test/tb/artifacts/coverage-combined.json }
Invoke-Step 'coverage threshold' { python -m coverage report --fail-under=$FailUnder | Select-Object -Last 2 }
