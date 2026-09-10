from pathlib import Path
p=Path('src/transport/ssh.py')
t=p.read_text(encoding='utf-8')
# upload single file: fallback on CM failure
old='''    def upload(self, local_path: Path, remote_path: str, timeout: float | None = None) -> CommandResult:
        t = timeout if timeout is not None else self.timeout
        cmd = [self._scp_cmd] + self._options(control_master=True)
        cmd += [str(local_path), f"{self._target()}:{remote_path}"]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=t, **_windows_no_window_kwargs())
        except subprocess.TimeoutExpired:
            return CommandResult(124, "", f"scp upload timed out after {t}s")
        return CommandResult(proc.returncode, proc.stdout.decode("utf-8", errors="replace"), proc.stderr.decode("utf-8", errors="replace"))'''
new='''    def _scp_with_fallback(self, args, t):
        for attempt in (1, 2):
            cmd = [self._scp_cmd] + self._options() + args
            try:
                proc = subprocess.run(cmd, capture_output=True, timeout=t, **_windows_no_window_kwargs())
            except subprocess.TimeoutExpired:
                return CommandResult(124, "", f"scp timed out after {t}s")
            stdout = proc.stdout.decode("utf-8", errors="replace")
            stderr = proc.stderr.decode("utf-8", errors="replace")
            if proc.returncode == 0:
                return CommandResult(0, stdout, stderr)
            low = stderr.lower()
            if self._control_master and any(frag in low for frag in self._CM_FAILURE_FRAGMENTS):
                self._control_master = False
                continue
            return CommandResult(proc.returncode, stdout, stderr)
        return CommandResult(1, "", "scp failed")

    def upload(self, local_path: Path, remote_path: str, timeout: float | None = None) -> CommandResult:
        t = timeout if timeout is not None else self.timeout
        return self._scp_with_fallback([str(local_path), f"{self._target()}:{remote_path}"], t)'''
assert old in t
t=t.replace(old,new)
# download single-file fallback
old2='''        cmd = [self._scp_cmd] + self._options(control_master=True)
        cmd += [f"{self._target()}:{remote_path}", str(local_path)]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=t, **_windows_no_window_kwargs())
        except subprocess.TimeoutExpired:
            return CommandResult(124, "", f"scp download timed out after {t}s")
        return CommandResult(proc.returncode, proc.stdout.decode("utf-8", errors="replace"), proc.stderr.decode("utf-8", errors="replace"))'''
new2='''        return self._scp_with_fallback([f"{self._target()}:{remote_path}", str(local_path)], t)'''
assert old2 in t
t=t.replace(old2,new2)
p.write_text(t, encoding='utf-8')
print('scp fallback added')
