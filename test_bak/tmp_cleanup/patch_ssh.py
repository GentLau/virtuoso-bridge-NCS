from pathlib import Path
p=Path('src/transport/ssh.py')
t=p.read_text(encoding='utf-8')
start=t.index('    def run_command(self, command: str, timeout: float | None = None) -> CommandResult:')
end=t.index('    # -- file transfer', start)
new='''    _CM_FAILURE_FRAGMENTS = (
        "getsockname failed", "not a socket", "mux_client", "could not create named pipe",
        "controlpath too long", "mux server has been disabled",
    )

    def run_command(self, command: str, timeout: float | None = None) -> CommandResult:
        t = timeout if timeout is not None else self.timeout
        for attempt in (1, 2, 3):
            cmd = [self._ssh_cmd] + self._options() + [self._target(), "sh", "-l"]
            try:
                proc = subprocess.run(
                    cmd, input=command.encode("utf-8"), capture_output=True, text=False,
                    timeout=t, **_windows_no_window_kwargs(),
                )
            except subprocess.TimeoutExpired:
                return CommandResult(returncode=124, stdout="", stderr=f"command timed out after {t}s")
            stdout = proc.stdout.decode("utf-8", errors="replace")
            stderr = proc.stderr.decode("utf-8", errors="replace")
            if proc.returncode == 0:
                return CommandResult(proc.returncode, stdout, stderr)
            low = stderr.lower()
            if self._control_master and any(frag in low for frag in self._CM_FAILURE_FRAGMENTS):
                self._control_master = False
                continue
            transient = any(x in low for x in ("banner exchange", "kex_exchange_identification", "connection reset", "connection closed"))
            if attempt < 3 and transient:
                continue
            return CommandResult(proc.returncode, stdout, stderr)
        return CommandResult(returncode=1, stdout="", stderr="ssh failed")

'''
t=t[:start]+new+t[end:]
p.write_text(t, encoding='utf-8')
print('run_command rewritten')
