"""SSH backend semi-real TB: OpenSSH *and* Paramiko over a real sshd.

Every transport primitive the middle layer relies on is exercised against a
real host (default ``wsl-gent``) with **no Virtuoso** involved:

* ``run_command`` / ``run_one_shot`` (rc, stdout, stderr, timeout);
* ``upload`` / ``upload_batch`` / ``upload_text`` and ``download``
  (file + ``recursive`` directory, plus a missing-path failure);
* the persistent shell protocol (env/cwd persistence, failing command, close);
* concurrent commands through one runner (session gate / channel budget).

Both backends run the same matrix so a green OpenSSH result cannot hide a
Paramiko-only regression (and vice versa).  The remote scratch tree is created
under ``~/.virtuoso-bridge/tb-scratch`` and removed in ``finally``.

Run with::

    PYTHONPATH=src python test/semi/transport/ssh_backend_semi_tb.py \
        --out test/artifacts/evidence/ssh-backend-semi.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.ssh import SSHRunner  # noqa: E402


class CaseFailure(AssertionError):
    """A semi-real check failed; the message must name the contract."""


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise CaseFailure(message)


def _runner(host: str, user: str, *, backend: str, persistent: bool,
            work_dir: str) -> SSHRunner:
    return SSHRunner(
        host,
        user=user,
        backend=backend,
        persistent_shell=persistent,
        control_master="disable" if backend == "openssh" else "auto",
        connect_timeout=15,
        timeout=60,
        work_dir=work_dir,
    )


def run_matrix(runner: SSHRunner, remote_root: str, local_root: Path,
               *, persistent: bool) -> list[dict]:
    results: list[dict] = []

    def case(name: str, fn) -> None:
        started = time.perf_counter()
        try:
            detail = fn()
            results.append({
                "case": name, "ok": True, "detail": detail,
                "seconds": round(time.perf_counter() - started, 3),
            })
        except Exception as exc:  # noqa: BLE001 - evidence, not control flow
            results.append({
                "case": name, "ok": False,
                "detail": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(limit=3),
                "seconds": round(time.perf_counter() - started, 3),
            })

    def conn():
        _check(runner.test_connection(), "test_connection must report reachable")
        return True

    def rc_and_streams():
        res = runner.run_command("echo out; echo err >&2; exit 3")
        _check(res.returncode == 3, f"rc={res.returncode}, expected 3")
        _check("out" in res.stdout, f"stdout={res.stdout!r}")
        _check("err" in res.stderr, f"stderr={res.stderr!r}")
        return {"rc": res.returncode}

    def upload_text_case():
        remote = f"{remote_root}/text/greeting.txt"
        res = runner.upload_text("hello-semi\n", remote)
        _check(res.returncode == 0, f"upload_text rc={res.returncode}: {res.stderr}")
        cat = runner.run_command(f"cat {remote}")
        _check(cat.stdout.strip() == "hello-semi", f"cat={cat.stdout!r}")
        return {"rc": res.returncode}

    def upload_file_case():
        local = local_root / "single.bin"
        local.write_bytes(b"single-file-payload\n")
        remote = f"{remote_root}/single/uploaded.bin"
        res = runner.upload(local, remote)
        _check(res.returncode == 0, f"upload rc={res.returncode}: {res.stderr}")
        cat = runner.run_command(f"cat {remote}")
        _check(cat.stdout.strip() == "single-file-payload", cat.stdout)
        return {"rc": res.returncode}

    def upload_batch_case():
        one = local_root / "batch-a.txt"
        two = local_root / "batch-b.txt"
        one.write_text("batch-a\n", encoding="utf-8")
        two.write_text("batch-b\n", encoding="utf-8")
        res = runner.upload_batch([
            (one, f"{remote_root}/batch/a.txt"),
            (two, f"{remote_root}/batch/b.txt"),
        ])
        _check(res.returncode == 0, f"upload_batch rc={res.returncode}: {res.stderr}")
        listing = runner.run_command(f"cat {remote_root}/batch/a.txt {remote_root}/batch/b.txt")
        _check("batch-a" in listing.stdout and "batch-b" in listing.stdout,
               listing.stdout)
        return {"rc": res.returncode}

    def upload_dir_case():
        src = local_root / "tree"
        (src / "nested").mkdir(parents=True, exist_ok=True)
        (src / "top.txt").write_text("top\n", encoding="utf-8")
        (src / "nested" / "deep.txt").write_text("deep\n", encoding="utf-8")
        res = runner.upload(src, f"{remote_root}/tree", recursive=True)
        _check(res.returncode == 0, f"upload dir rc={res.returncode}: {res.stderr}")
        cat = runner.run_command(
            f"cat {remote_root}/tree/top.txt {remote_root}/tree/nested/deep.txt"
        )
        _check("top" in cat.stdout and "deep" in cat.stdout, cat.stdout)
        return {"rc": res.returncode}

    def download_file_case():
        remote = f"{remote_root}/download/remote.txt"
        runner.run_command(f"mkdir -p {remote_root}/download && printf 'from-remote\\n' > {remote}")
        local = local_root / "downloaded" / "remote.txt"
        res = runner.download(remote, local)
        _check(res.returncode == 0, f"download rc={res.returncode}: {res.stderr}")
        _check(local.read_text(encoding="utf-8").strip() == "from-remote",
               local.read_text(encoding="utf-8"))
        return {"rc": res.returncode}

    def download_dir_case():
        res = runner.download(f"{remote_root}/tree", local_root / "tree-back",
                              recursive=True)
        _check(res.returncode == 0, f"download dir rc={res.returncode}: {res.stderr}")
        top = (local_root / "tree-back" / "top.txt").read_text(encoding="utf-8")
        deep = (local_root / "tree-back" / "nested" / "deep.txt").read_text(
            encoding="utf-8"
        )
        _check(top.strip() == "top" and deep.strip() == "deep", f"{top!r}/{deep!r}")
        return {"rc": res.returncode}

    def download_missing_case():
        res = runner.download(f"{remote_root}/nope/missing.txt",
                              local_root / "missing.txt")
        _check(res.returncode != 0, "missing remote path must not report success")
        _check(not (local_root / "missing.txt").exists(),
               "failed download must not install a partial file")
        return {"rc": res.returncode}

    def timeout_case():
        if persistent:
            # a timed-out persistent command retires the shell; the next call
            # must transparently rebuild it
            try:
                runner.run_command("sleep 5", timeout=1)
            except subprocess.TimeoutExpired:
                pass
            else:
                raise CaseFailure("sleep 5 with timeout=1 must raise TimeoutExpired")
            after = runner.run_command("echo alive")
            _check(after.returncode == 0 and "alive" in after.stdout,
                   f"post-timeout rebuild failed: {after}")
            return {"recovered": True}
        try:
            runner.run_command("sleep 5", timeout=1)
        except subprocess.TimeoutExpired:
            return {"raised": "TimeoutExpired"}
        raise CaseFailure("sleep 5 with timeout=1 must raise TimeoutExpired")

    def persistent_case():
        if not persistent:
            return {"skipped": "one-shot runner"}
        first = runner.run_command("cd /tmp && export VB_SEMI_MARK=abc123")
        _check(first.returncode == 0, f"first shell command rc={first.returncode}")
        second = runner.run_command("printf '%s:%s' \"$VB_SEMI_MARK\" \"$(pwd)\"")
        _check(second.returncode == 0, f"second rc={second.returncode}: {second.stderr}")
        _check(second.stdout.strip() == "abc123:/tmp",
               f"shell state lost: {second.stdout!r}")
        # ``sh -c 'exit 7'`` fails the command without killing the shared shell
        failing = runner.run_command("sh -c 'exit 7'")
        _check(failing.returncode == 7, f"rc={failing.returncode}, expected 7")
        return {"stdout": second.stdout.strip()}

    def concurrency_case():
        def one(index: int) -> tuple[int, str]:
            res = runner.run_command(f"echo worker-{index}")
            return res.returncode, res.stdout.strip()

        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(one, range(8)))
        for index, (rc, out) in enumerate(outcomes):
            _check(rc == 0 and out == f"worker-{index}", f"{index}: rc={rc} out={out!r}")
        return {"workers": len(outcomes)}

    case("test_connection", conn)
    case("run_command_rc_and_streams", rc_and_streams)
    case("upload_text", upload_text_case)
    case("upload_file", upload_file_case)
    case("upload_batch", upload_batch_case)
    case("upload_dir_recursive", upload_dir_case)
    case("download_file", download_file_case)
    case("download_dir_recursive", download_dir_case)
    case("download_missing_path", download_missing_case)
    case("run_command_timeout", timeout_case)
    case("persistent_shell_state", persistent_case)
    case("concurrent_run_command", concurrency_case)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="wsl-gent")
    parser.add_argument("--ssh-user", default="Gent")
    parser.add_argument("--remote-root",
                        default="/home/Gent/.virtuoso-bridge/tb-scratch")
    parser.add_argument("--backends", default="paramiko,openssh")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    run_id = uuid.uuid4().hex[:10]
    remote_root = f"{args.remote_root.rstrip('/')}/{run_id}"
    local_root = Path(tempfile.mkdtemp(prefix="vb-ssh-semi-"))
    report = {
        "tb": "ssh_backend_semi_tb",
        "host": args.host,
        "ssh_user": args.ssh_user,
        "remote_root": remote_root,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "backends": {},
    }
    failed = False
    try:
        for backend in [b.strip() for b in args.backends.split(",") if b.strip()]:
            for persistent in (False, True):
                key = f"{backend}{'+persistent' if persistent else ''}"
                runner = _runner(args.host, args.ssh_user, backend=backend,
                                 persistent=persistent, work_dir=remote_root)
                try:
                    cases = run_matrix(runner, remote_root, local_root,
                                       persistent=persistent)
                finally:
                    try:
                        runner.close()
                    except Exception:  # noqa: BLE001 - best effort cleanup
                        pass
                report["backends"][key] = {
                    "persistent_shell_enabled": bool(
                        getattr(runner, "_persistent_shell_enabled", False)
                    ),
                    "cases": cases,
                }
                if not all(c["ok"] for c in cases):
                    failed = True
    finally:
        cleanup = _runner(args.host, args.ssh_user, backend="paramiko",
                          persistent=False, work_dir=remote_root)
        try:
            cleanup.run_command(f"rm -rf {remote_root}")
            cleanup.close()
        except Exception:  # noqa: BLE001 - cleanup is best effort
            pass
        shutil.rmtree(local_root, ignore_errors=True)

    report["ok"] = not failed
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
