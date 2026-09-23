#!/bin/bash
# Start one real Virtuoso instance for a test scenario.
#
# Run on the remote host (wsl-gent) as the Virtuoso user:
#
#   nohup ~/start_real_virtuoso.sh <run-dir> <cds.lib> <display> [ref-pid] \
#       > <run-dir>/start.log 2>&1 &
#
# Why it looks like this:
#   * cwd is the run dir, so CDS.log / CDS.log.cdslck / .artist_states stay
#     inside the scenario's own directory instead of polluting $HOME or a
#     project directory (see test/docs/推荐测试环境.md section 0);
#   * a .cdsinit in the run dir auto-loads the bridge setup, so the daemon
#     comes up without typing into the CIW;
#   * non-interactive ssh shells do not source the Cadence login environment,
#     so LD_LIBRARY_PATH & friends are copied from an already-running
#     Virtuoso process (pass its pid as <ref-pid>); without this the loader
#     fails with "libap_sh.so: cannot open shared object file".
set -euo pipefail

RUN_DIR=${1:?usage: start_real_virtuoso.sh <run-dir> <cds.lib> <display> [ref-pid]}
CDSLIB=${2:?usage: start_real_virtuoso.sh <run-dir> <cds.lib> <display> [ref-pid]}
DISPLAY_NAME=${3:-:99}
REF_PID=${4:-}

runtime_env() {
    tr '\0' '\n' < "/proc/$REF_PID/environ" | sed -n "s/^$1=//p" | head -1
}

cd "$RUN_DIR"

if [ -n "$REF_PID" ] && [ -r "/proc/$REF_PID/environ" ]; then
    for name in PATH LD_LIBRARY_PATH CDS_LIC_FILE CDSHOME CDS_INST_DIR CDS_SITE \
                LM_LICENSE_FILE LM_PROJECT MGC_HOME CALIBRE_HOME SPECTRE_HOME; do
        value=$(runtime_env "$name")
        if [ -n "$value" ]; then
            export "$name=$value"
        fi
    done
fi

export DISPLAY="$DISPLAY_NAME"
exec /opt/eda/cadence/IC618/tools/dfII/bin/64bit/virtuoso \
    -cdslib "$CDSLIB" -log "$RUN_DIR/CDS.log"
