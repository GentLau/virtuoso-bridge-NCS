from pathlib import Path
p=Path('src/transport/ssh.py')
t=p.read_text(encoding='utf-8')
anchor='\n__all__ = ["SSHRunner"]\n'
assert anchor in t
addition='''

    # -- staged / verified transfer (spec: atomic install + digest) ----------

    def upload_atomic(self, local_path: Path, remote_path: str, timeout: float | None = None) -> CommandResult:
        import hashlib as _hashlib
        t = timeout if timeout is not None else self.timeout
        stage = f"{remote_path}.vb_staging.{os.getpid()}"
        up = self.upload(local_path, stage, timeout=t)
        if up.returncode != 0:
            return up
        mv = self.run_command(f"mv -f {shlex.quote(stage)} {shlex.quote(remote_path)}", timeout=t)
        if mv.returncode != 0:
            return mv
        local_sha = _hashlib.sha256(Path(local_path).read_bytes()).hexdigest()
        check = self.run_command(f"sha256sum {shlex.quote(remote_path)}", timeout=t)
        if check.returncode != 0:
            return check
        remote_sha = check.stdout.strip().split()[0]
        if remote_sha != local_sha:
            return CommandResult(1, "", f"sha256 mismatch: local={local_sha} remote={remote_sha}")
        return CommandResult(0, remote_path, "")

    def download_verified(self, remote_path: str, local_path: Path, timeout: float | None = None) -> CommandResult:
        import hashlib as _hashlib
        t = timeout if timeout is not None else self.timeout
        dl = self.download(remote_path, local_path, recursive=False, timeout=t)
        if dl.returncode != 0:
            return dl
        check = self.run_command(f"sha256sum {shlex.quote(remote_path)}", timeout=t)
        if check.returncode != 0:
            return check
        remote_sha = check.stdout.strip().split()[0]
        local_sha = _hashlib.sha256(Path(local_path).read_bytes()).hexdigest()
        if remote_sha != local_sha:
            return CommandResult(1, "", f"sha256 mismatch: local={local_sha} remote={remote_sha}")
        return CommandResult(0, str(local_path), "")
'''
t=t.replace(anchor, addition+anchor)
p.write_text(t, encoding='utf-8')
print('atomic methods appended')
