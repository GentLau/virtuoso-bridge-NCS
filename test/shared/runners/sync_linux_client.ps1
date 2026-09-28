# Sync the working tree (src + test + pyproject.toml) to the Linux client repo copy
# on wsl-gent, then optionally run the offline suite there with python3.9.
#
# Usage:
#   powershell -File test/shared/runners/sync_linux_client.ps1          # sync only
#   powershell -File test/shared/runners/sync_linux_client.ps1 -Run     # sync + run offline suite
param(
    [switch]$Run,
    [string]$JunitName = "offline-linux-py39.xml"
)
$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\user\Desktop\repos_Github\virtuoso-bridge-NCS'
Set-Location $repo

$remoteBase = '/home/Gent/project/vblog/tb-sandbox/linux-client'
$tarball = Join-Path $env:TEMP ("vb-linux-sync-{0}.tgz" -f (Get-Date -Format 'HHmmss'))

# 1) pack (skip artifacts / caches)
tar.exe -czf $tarball --exclude=test/artifacts --exclude=__pycache__ --exclude=.pytest_cache src test pyproject.toml
if ($LASTEXITCODE -ne 0) { throw "tar failed" }
$size = (Get-Item $tarball).Length
Write-Output ("tarball {0} ({1:N1} MB)" -f $tarball, ($size / 1MB))

# 2) upload then extract into a fresh dir and atomically swap
scp -q $tarball "wsl-gent:/tmp/vb-linux-sync.tgz"
if ($LASTEXITCODE -ne 0) { throw "scp failed" }

$remoteCmd = @"
set -eu
base='$remoteBase'
test -d "`$base/repo" || { echo 'sandbox repo missing'; exit 2; }
rm -rf "`$base/repo.new"
mkdir -p "`$base/repo.new"
tar -xzf /tmp/vb-linux-sync.tgz -C "`$base/repo.new"
rm -rf "`$base/repo.old"
mv "`$base/repo" "`$base/repo.old"
mv "`$base/repo.new" "`$base/repo"
rm -rf "`$base/repo.old"
echo "synced: `$(find `$base/repo -name '*.py' | wc -l) py files"
"@
$remoteCmd = $remoteCmd -replace "`r", ""
$remoteCmd | ssh wsl-gent "bash -s"
if ($LASTEXITCODE -ne 0) { throw "remote sync failed" }

if (-not $Run) {
    Remove-Item $tarball -Force
    Write-Output 'sync only (pass -Run to execute the offline suite)'
    exit 0
}

# 3) run the offline suite on the Linux copy
$evid = "/home/Gent/project/vblog/tb-sandbox/linux-client/$JunitName"
$remoteRun = @"
set -eu
cd $remoteBase/repo
export PYTHONPATH=src
/usr/bin/python3.9 -m pytest test/offline/unit test/offline/integration test/offline/scenario \
    -q --junitxml=$evid -p no:cacheprovider 2>&1 | tail -25
echo "JUNIT=$evid"
"@
$remoteRun = $remoteRun -replace "`r", ""
$remoteRun | ssh wsl-gent "bash -s"
if ($LASTEXITCODE -ne 0) { Write-Output 'REMOTE PYTEST FAILED (rc != 0)' }

# 4) pull the JUnit XML back
$dest = Join-Path $repo ("test\artifacts\evidence\round8\" + $JunitName)
scp -q "wsl-gent:$evid" $dest
Write-Output ("junit -> {0}" -f $dest)
Remove-Item $tarball -Force
