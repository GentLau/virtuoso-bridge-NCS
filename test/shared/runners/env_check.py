# -*- coding: utf-8 -*-
"""TB 第 1 步专用：**"当前环境是不是我需要的环境"** 一键检测。

写 TB 的人不必自己拼检查代码——在 TB 的六步流程第 1 步里跑一次本脚本即可；退出码非 0
就说明环境不对，TB 应**直接失败**（不是 skip，也不要换环境凑合）。

两种用法：

1) HTTP 业务面（最常用）::

       PYTHONPATH=src python test/shared/runners/env_check.py \
           --base http://127.0.0.1:8127 --token vb-vblog \
           --expect-host wsl-gent --expect-user Gent \
           --require-lib tsmcN65 --require-calibre \
           --json test/artifacts/evidence/env-check.json

2) 进程内（TB 直接走 middle 时；额外把 `query` 的 role root / display / spectre bin 记进报告）::

       PYTHONPATH=src python test/shared/runners/env_check.py \
           --work-dir test/artifacts/env/log-vblog --token vb-vblog --require-lib serdes_rx

**在 Python 里一行调用**（TB 最省事；失败会抛 `RuntimeError`，等于第 1 步不通过）：:

    import sys
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(ROOT / "test" / "shared" / "runners"))
    from env_check import require_environment
    require_environment(base="http://127.0.0.1:8127/api/operation", token="vb-vblog",
                        expect_host="wsl-gent", require_lib=["tsmcN65"])

检查项（每项都会写进报告：`name / ok / detail / expected`）：

* `face`：业务面 `/health`（HTTP 模式）或 `BusinessServer` 构造（进程内模式）；
* `token`：`basic.command.run` 回声 —— token 有效且 command role 可达；
* `host` / `user`：`hostname` / `whoami`，与 `--expect-host` / `--expect-user` 比对；
* `skill-<n>`：SKILL 通道可用（`1+2` 必须回 `3`）；
* `lib-<NAME>`：CIW 里 `ddGetObj("<NAME>")` 非空（**库/工艺/共享库是否挂上**）；
* `calibre` / `spectre`：命令 role 上能找到可执行文件（`--require-calibre` / `--require-spectre`）；
* `python`：`--expect-python 3.9` → 跑 `python3 -V`（前缀 2.x 时用 `python2.7 -V`）并比对版本前缀。
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _call_http(base: str, token: str, operation: str, timeout: float = 120.0, **fields):
    body = json.dumps({"operation": operation, "token": token, **fields}).encode("utf-8")
    request = urllib.request.Request(base, data=body,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return json.loads(error.read().decode("utf-8"))


class HttpEnv:
    """走 HTTP 业务面（`--base`）。"""

    mode = "http"

    def __init__(self, base: str, token: str) -> None:
        self.base, self.token = base, token
        self.middle = None

    def command(self, cmd: str, timeout: float = 120.0):
        response = _call_http(self.base, self.token, "basic.command.run",
                              timeout=timeout, cmd=cmd)
        result = (response.get("data") or {}).get("result") or []
        ok = bool(response.get("ok")) and isinstance(result, list) and result and result[0] == 0
        stdout = str(result[1]) if isinstance(result, list) and len(result) > 1 else ""
        return ok, stdout.strip(), response.get("error")

    def skill(self, code: str, timeout: float = 120.0):
        response = _call_http(self.base, self.token, "basic.skill.execute",
                              timeout=timeout, skill_code=code)
        result = (response.get("data") or {}).get("result") or {}
        ok = bool(response.get("ok")) and result.get("status") == "success"
        return ok, str(result.get("output") or "").strip(), response.get("error")

    def health(self):
        root = self.base.rstrip("/").removesuffix("/api/operation")
        try:
            with urllib.request.urlopen(f"{root}/health", timeout=15) as response:
                return response.status == 200, {"http": response.status}
        except (urllib.error.HTTPError, OSError) as error:
            return False, {"error": f"{type(error).__name__}: {error}"}

    def query(self):
        return None


class InProcessEnv:
    """走进程内 middle（`--work-dir`）：额外可用只读 `query`。"""

    mode = "in-process"

    def __init__(self, work_dir: str, token: str) -> None:
        from common.paths import init_work_dir
        from transport.middle import BusinessServer

        init_work_dir(str(Path(work_dir).resolve()))
        self.middle = BusinessServer()
        self.token = token

    def command(self, cmd: str, timeout: float = 120.0):
        result = self.middle.run_command(cmd, token=self.token, timeout=timeout)
        # 进程内返回的是 CommandResult(returncode/stdout/stderr/kind)，不是 HTTP 的 [rc, out, err, kind]
        stdout = getattr(result, "stdout", "") or ""
        stderr = getattr(result, "stderr", "") or ""
        returncode = getattr(result, "returncode", 1)
        return (returncode == 0, stdout.strip(), stderr.strip() or None)

    def skill(self, code: str, timeout: float = 120.0):
        result = self.middle.execute_skill(code, token=self.token, timeout=timeout)
        # VirtuosoResult(status/output/errors)，同样不是 HTTP 形状
        return bool(result.ok), (result.output or "").strip(), \
            "; ".join(result.errors or []) or None

    def health(self):
        return True, {"mode": "in-process"}

    def query(self):
        try:
            return _jsonable(self.middle.query(token=self.token))
        except Exception as error:  # noqa: BLE001 - query 只是附加信息
            return {"error": f"{type(error).__name__}: {error}"}


def _jsonable(value):
    """把 dataclass / 嵌套结构转成可 JSON 化的普通对象（进程内模式报告用）。"""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: _jsonable(getattr(value, field.name))
                for field in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def run_checks(env, *, expect_host: str = "", expect_user: str = "",
               require_lib=(), require_calibre: bool = False,
               require_spectre: bool = False, expect_python: str = "") -> dict:
    """执行全部检查，返回 `{ok, failed, checks}`（不打印、不退出，供 TB 直接调用）。"""
    checks: list[dict] = []

    def record(name: str, ok: bool, detail=None, expected=None) -> bool:
        checks.append({"name": name, "ok": bool(ok), "detail": detail, "expected": expected})
        return bool(ok)

    ok_face, face_detail = env.health()
    record("face", ok_face, face_detail)

    ok_cmd, host_out, cmd_err = env.command("hostname; whoami")
    if not record("token+command-role", ok_cmd, host_out.splitlines()[:2] or cmd_err):
        return {"ok": False, "failed": ["token+command-role"], "checks": checks}
    lines = host_out.splitlines()
    host = lines[0].strip() if lines else ""
    user = lines[1].strip() if len(lines) > 1 else ""
    if expect_host:
        record("host", host == expect_host, host, expect_host)
    if expect_user:
        record("user", user == expect_user, user, expect_user)

    ok_skill, skill_out, skill_err = env.skill("1+2")
    record("skill-1+2", ok_skill and skill_out.strip().strip('"') == "3",
           skill_out or skill_err, "3")

    for lib in require_lib:
        ok, out, err = env.skill(f'ddGetObj("{lib}")~>name')
        visible = ok and out.strip().strip('"') not in ("", "nil")
        record(f"lib-{lib}", visible, out or err, "非 nil")

    if require_calibre:
        ok, out, err = env.command("command -v calibre || true")
        record("calibre", ok and bool(out.strip()), out.strip() or err, "PATH 里有 calibre")
    if require_spectre:
        ok, out, err = env.command("command -v spectre || true")
        record("spectre", ok and bool(out.strip()), out.strip() or err, "PATH 里有 spectre")
    if expect_python:
        exe = "python2.7" if expect_python.startswith("2") else "python3"
        ok, out, err = env.command(f"{exe} -V 2>&1 || true")
        record("python", ok and expect_python in out, out.strip() or err,
               f"{exe} 版本包含 {expect_python}")

    if env.mode == "in-process":
        record("query(read-only)", True, env.query())

    failed = [c["name"] for c in checks if not c["ok"]]
    return {"ok": not failed, "failed": failed, "checks": checks}


def require_environment(*, base: str = "", work_dir: str = "", token: str,
                        **options) -> dict:
    """TB 第 1 步的一行调用：环境不对直接抛 `RuntimeError`（视同 TB 失败，不是 skip）。"""
    if not (base or work_dir):
        raise ValueError("require_environment 需要 base 或 work_dir 之一")
    env = HttpEnv(base, token) if base else InProcessEnv(work_dir, token)
    try:
        report = run_checks(env, **options)
    finally:
        middle = getattr(env, "middle", None)
        if middle is not None:
            try:
                middle.close()
            except Exception:  # noqa: BLE001 - best effort cleanup
                pass
    if not report["ok"]:
        raise RuntimeError(
            "环境不满足本 TB 的需求：" + ", ".join(report["failed"])
            + "（明细见 report['checks']）")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--base", default="", help="HTTP 业务面，如 http://127.0.0.1:8127/api/operation")
    target.add_argument("--work-dir", default="", help="进程内模式：注册表所在 work-dir")
    parser.add_argument("--token", required=True)
    parser.add_argument("--expect-host", default="")
    parser.add_argument("--expect-user", default="")
    parser.add_argument("--require-lib", action="append", default=[],
                        help="要求 CIW 里可见的库/工艺名（可重复）")
    parser.add_argument("--require-calibre", action="store_true")
    parser.add_argument("--require-spectre", action="store_true")
    parser.add_argument("--expect-python", default="", help="如 3.9 / 2.7（跑 python3 -V 或 python2.7 -V）")
    parser.add_argument("--exit-on-skill-fail", action="store_true", default=True)
    parser.add_argument("--json", default="", help="把完整报告写到该路径（TB 可当环境证据留档）")
    args = parser.parse_args(argv)

    env = (HttpEnv(args.base, args.token) if args.base
           else InProcessEnv(args.work_dir, args.token))
    report = run_checks(env, expect_host=args.expect_host, expect_user=args.expect_user,
                        require_lib=args.require_lib,
                        require_calibre=args.require_calibre,
                        require_spectre=args.require_spectre,
                        expect_python=args.expect_python)
    checks = report["checks"]
    for check in checks:
        flag = "OK " if check["ok"] else "FAIL"
        expected = check.get("expected")
        extra = f"  (期望 {expected})" if expected and not check["ok"] else ""
        detail = check.get("detail")
        print(f"[{flag}] {check['name']}{extra}" + (f" -> {detail}" if detail else ""))
    failed = report["failed"]
    print(f"\n环境判定：{'通过' if not failed else '不通过 -> ' + ', '.join(failed)}"
          f"（共 {len(checks)} 项，模式 {env.mode}）")
    if args.json:
        out_path = Path(args.json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(
            {"mode": env.mode, "token": args.token, "base": args.base,
             "work_dir": args.work_dir, "ok": not failed, "failed": failed,
             "checks": _jsonable(checks)}, ensure_ascii=False, indent=1,
            default=str), encoding="utf-8")
        print(f"报告：{out_path}")
    return 0 if not failed else 1


def report_fail(checks: list[dict], args, env) -> None:
    """前置检查就失败时也要写报告（TB 里需要留下'为什么判环境不对'）。"""
    if args.json:
        out_path = Path(args.json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(
            {"mode": env.mode, "token": args.token, "base": args.base,
             "work_dir": args.work_dir, "ok": False,
             "failed": [c["name"] for c in checks if not c["ok"]],
             "checks": _jsonable(checks)},
            ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"报告：{out_path}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
