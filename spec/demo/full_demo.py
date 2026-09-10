# -*- coding: utf-8 -*-
"""完整业务 demo：注册 + token 路由 + 单用户并行（收拢版）。

把此前分散的三个最小验证收拢到一个自包含模块里，模拟一条完整业务链路：

    register(user) → 探测端口 / 分配 token / 写 registry.json
    deploy(user)   → token 注入伪 virtuoso_setup.il
    load(user)     → 启动该用户自己的 Skill 端口（单线程 daemon）
    connect(user)  → 命令通道 + Skill 通道双冒烟

之后上层每次只带 token 调中层两个接口：

    middle.run_command(cmd, token=..., parallel=...)   # 用系统 pwsh 模拟命令执行
    middle.execute_skill(skill, token=...)             # 投送到对应端口，到达即成功

语义对照设计文档：

* 多个用户各自拥有独立 runtime / daemon / 端口，跨用户真并行；
* 同一用户的 execute_skill 由单线程 daemon 串行（Virtuoso CIW 语义）；
* run_command 默认走 persistent pwsh（保顺序、保会话状态、串行），
  ``parallel=True`` 每次起一个独立 pwsh 进程并行；
* 中层只认 token 路由，上层不接触 host / port / socket / subprocess；
* worker 池超限直接返回结构化错误，不无限排队。

只依赖 Python 标准库 + 系统 PATH 中的 ``pwsh``（PowerShell Core）。
"""
from __future__ import annotations

import getpass
import json
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class DemoError(Exception):
    """demo 内部错误基类。"""


class RegistrationError(DemoError):
    """注册 / 部署 / load / 连接流程错误。"""


@dataclass
class CommandResult:
    """RunCommand 的最小结构化返回值（前三个字段对应协议口径）。"""

    returncode: int
    stdout: str = ""
    stderr: str = ""
    error_kind: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "error_kind": self.error_kind,
        }


@dataclass
class SkillResult:
    """execute_skill 的最小结构化返回值；成功判据是“到达对应端口”。"""

    status: str
    output: str = ""
    errors: List[str] = field(default_factory=list)
    endpoint: Optional[str] = None
    log: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "success"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "output": self.output,
            "errors": self.errors,
            "endpoint": self.endpoint,
            "log": self.log,
        }


@dataclass(frozen=True)
class CommandRecord:
    """一条 run_command 的执行区间，用于观察串行 / 并行。"""

    token: str
    mode: str
    cmd: str
    started_at: float
    finished_at: float

    def overlaps(self, other: "CommandRecord") -> bool:
        return self.started_at < other.finished_at and other.started_at < self.finished_at


@dataclass(frozen=True)
class Arrival:
    """一条到达 Skill 端口的请求记录。"""

    endpoint: str
    token: Optional[str]
    skill: Optional[str]
    started_at: float
    finished_at: float

    def overlaps(self, other: "Arrival") -> bool:
        return self.started_at < other.finished_at and other.started_at < self.finished_at


class Registry:
    """极小的本地 JSON 注册表，user 是查询键。"""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._users: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._users = {}
            return
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        users = payload.get("users", {})
        if not isinstance(users, dict):
            raise RegistrationError("registry.users must be an object")
        self._users = dict(users)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(
            json.dumps({"users": self._users}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def get(self, user: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            entry = self._users.get(user)
            return None if entry is None else json.loads(json.dumps(entry))

    def put(self, user: str, entry: Dict[str, Any]) -> None:
        with self._lock:
            if user in self._users:
                raise RegistrationError("user already registered: {}".format(user))
            self._users[user] = json.loads(json.dumps(entry))
            self._save()

    def remove(self, user: str) -> None:
        with self._lock:
            self._users.pop(user, None)
            self._save()

    def users(self) -> List[str]:
        with self._lock:
            return sorted(self._users)


def run_pwsh_command(cmd: str, timeout: Optional[float]) -> CommandResult:
    """一次独立的 pwsh 进程执行，用于 parallel=True。"""

    executable = shutil.which("pwsh")
    if executable is None:
        return CommandResult(
            -1,
            stderr="pwsh not found on PATH",
            error_kind="pwsh_missing",
        )
    try:
        completed = subprocess.run(
            [
                executable,
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                cmd,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)
    except subprocess.TimeoutExpired:
        return CommandResult(-1, stderr="command timeout", error_kind="timeout")
    except OSError as exc:
        return CommandResult(-1, stderr=str(exc), error_kind="spawn_error")


class PersistentPwsh:
    """一个常驻 pwsh，命令通过 stdin 投送、用 marker 定界读取。

    保持会话状态是“串行命令 persistent shell”语义的关键：前一条命令设置的
    变量，下一条命令仍然可见。调用方必须串行使用（见 TokenRuntime 的锁）。
    """

    def __init__(self) -> None:
        executable = shutil.which("pwsh")
        if executable is None:
            raise DemoError("pwsh not found on PATH")
        self._proc = subprocess.Popen(
            [
                executable,
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "-",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self._condition = threading.Condition()
        self._current: Optional[Dict[str, Any]] = None
        self._eof = False
        self._marker_seq = 0
        self._reader = threading.Thread(
            target=self._read_loop,
            name="persistent-pwsh-reader",
            daemon=True,
        )
        self._reader.start()

    def _read_loop(self) -> None:
        try:
            for line in self._proc.stdout:  # type: ignore[union-attr]
                with self._condition:
                    if self._current is None:
                        continue
                    if line.strip() == self._current["marker"]:
                        self._current["done"] = True
                    else:
                        self._current["lines"].append(line)
                    self._condition.notify_all()
        except (OSError, ValueError):
            pass
        finally:
            with self._condition:
                self._eof = True
                if self._current is not None:
                    self._current["eof"] = True
                self._condition.notify_all()

    def execute(self, cmd: str, timeout: Optional[float] = None) -> CommandResult:
        with self._condition:
            if self._eof or self._current is not None:
                return CommandResult(
                    -1,
                    stderr="persistent shell unavailable",
                    error_kind="shell_error",
                )
            self._marker_seq += 1
            marker = "__VB_EOM_{}__".format(self._marker_seq)
            context = {
                "marker": marker,
                "lines": [],
                "done": False,
                "eof": False,
            }
            self._current = context

        try:
            self._proc.stdin.write(  # type: ignore[union-attr]
                "{}\nWrite-Output '{}'\n".format(cmd, marker)
            )
            self._proc.stdin.flush()  # type: ignore[union-attr]
        except (OSError, ValueError):
            with self._condition:
                if self._current is context:
                    self._current = None
            return CommandResult(
                -1,
                stderr="persistent shell write failed",
                error_kind="shell_error",
            )

        deadline = None if timeout is None else time.monotonic() + timeout
        with self._condition:
            while not context["done"] and not context["eof"]:
                remaining = None
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                self._condition.wait(remaining)
            timed_out = not context["done"] and not context["eof"]
            output = "".join(context["lines"])
            eof = context["eof"]
            if self._current is context:
                self._current = None

        if timed_out:
            return CommandResult(-1, output, "command timeout", error_kind="timeout")
        if eof:
            return_code = self._proc.poll()
            return CommandResult(
                -1 if return_code is None else return_code,
                output,
                "persistent shell exited",
                error_kind="shell_error",
            )
        return CommandResult(0, output.rstrip("\n"), "")

    def close(self) -> None:
        try:
            self._proc.stdin.close()  # type: ignore[union-attr]
        except OSError:
            pass
        try:
            self._proc.terminate()
        except OSError:
            pass
        try:
            self._proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            self._proc.kill()
        try:
            self._proc.stdout.close()  # type: ignore[union-attr]
        except OSError:
            pass


class SkillDaemon:
    """单线程 accept 循环的伪 Skill 端口：到达即记录、即 ACK。

    单线程顺序处理是 Virtuoso CIW 的语义投影；``delay`` 用于观察串行化，
    默认 0（只验证到达）。
    """

    def __init__(
        self,
        endpoint: str,
        host: str,
        port: int,
        token: str,
        delay: float = 0.0,
    ) -> None:
        self.endpoint = endpoint
        self.host = host
        self.port = port
        self.token = token
        self.delay = delay
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((host, port))
        self._server.listen(16)
        self._server.settimeout(0.2)
        self._stop = threading.Event()
        self._arrivals: List[Arrival] = []
        self._arrivals_lock = threading.Lock()
        self._thread = threading.Thread(
            target=self._serve,
            name="skill-daemon-" + endpoint,
            daemon=True,
        )
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                connection, _address = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                self._handle(connection)
            finally:
                try:
                    connection.close()
                except OSError:
                    pass

    def _handle(self, connection: socket.socket) -> None:
        started_at = time.monotonic()
        token = None
        skill = None
        try:
            reader = connection.makefile("rb")
            try:
                line = reader.readline()
            finally:
                reader.close()
            if line:
                request = json.loads(line.decode("utf-8", errors="replace"))
                token = request.get("token") if isinstance(request, dict) else None
                skill = request.get("skill") if isinstance(request, dict) else None
            if self.delay:
                time.sleep(self.delay)
            response = {
                "ok": True,
                "status": "arrived",
                "endpoint": self.endpoint,
                "echo": skill,
            }
        except Exception as exc:  # 到达即成功；只有协议破损才回 error
            response = {"ok": False, "status": "arrived", "error": str(exc)}
        finished_at = time.monotonic()
        with self._arrivals_lock:
            self._arrivals.append(
                Arrival(
                    endpoint=self.endpoint,
                    token=token,
                    skill=skill,
                    started_at=started_at,
                    finished_at=finished_at,
                )
            )
        connection.sendall((json.dumps(response) + "\n").encode("utf-8"))

    def arrivals(self) -> List[Arrival]:
        with self._arrivals_lock:
            return list(self._arrivals)

    def close(self) -> None:
        self._stop.set()
        try:
            self._server.close()
        except OSError:
            pass
        self._thread.join(timeout=2.0)


class TokenRuntime:
    """一个 token 的私有 worker 池、persistent pwsh 与 Skill 端口。"""

    def __init__(
        self,
        token: str,
        user: str,
        daemon: SkillDaemon,
        max_workers: int = 32,
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        self.token = token
        self.user = user
        self.daemon = daemon
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="vb-{}".format(user),
        )
        self._slots = threading.BoundedSemaphore(max_workers)
        self._serial_lock = threading.Lock()
        self._pwsh: Optional[PersistentPwsh] = None
        self._records: List[CommandRecord] = []
        self._records_lock = threading.Lock()
        self._active_parallel = 0
        self._max_parallel = 0
        self._parallel_lock = threading.Lock()

    # ------------------------------------------------------------------ skill

    def execute_skill(self, skill_code: str, timeout: Optional[float] = None) -> SkillResult:
        host = self.daemon.host
        port = self.daemon.port
        effective_timeout = 5.0 if timeout is None else timeout
        request = json.dumps({"token": self.token, "skill": skill_code}) + "\n"
        try:
            with socket.create_connection((host, port), timeout=effective_timeout) as sock:
                sock.settimeout(effective_timeout)
                sock.sendall(request.encode("utf-8"))
                reader = sock.makefile("rb")
                try:
                    line = reader.readline()
                finally:
                    reader.close()
            if not line:
                raise DemoError("daemon closed without response")
            ack = json.loads(line.decode("utf-8", errors="replace"))
            if not ack.get("ok"):
                return SkillResult(
                    "error",
                    errors=[str(ack.get("error", "daemon rejected request"))],
                    endpoint=ack.get("endpoint"),
                )
            return SkillResult(
                "success",
                output=ack.get("echo") if ack.get("echo") is not None else skill_code,
                endpoint=ack.get("endpoint"),
                log="arrived",
            )
        except (OSError, ValueError, DemoError) as exc:
            return SkillResult("error", errors=[str(exc)])

    # ---------------------------------------------------------------- command

    def run_command(
        self,
        cmd: str,
        timeout: Optional[float] = None,
        parallel: bool = False,
    ) -> CommandResult:
        if not self._slots.acquire(blocking=False):
            return CommandResult(
                -1,
                stderr="worker capacity exceeded",
                error_kind="worker_capacity",
            )
        future: Future[CommandResult] = self._executor.submit(
            self._execute_command,
            cmd,
            timeout,
            parallel,
        )
        future.add_done_callback(lambda _future: self._slots.release())
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError:
            return CommandResult(-1, stderr="command timeout", error_kind="timeout")

    def _execute_command(
        self,
        cmd: str,
        timeout: Optional[float],
        parallel: bool,
    ) -> CommandResult:
        mode = "parallel" if parallel else "serial"
        # parallel 区间从真正 spawn pwsh 开始；serial 区间从拿到锁之后开始，
        # 这样记录反映“执行是否重叠”，而不是“排队等待是否重叠”。
        started_at = time.monotonic()
        try:
            if parallel:
                with self._parallel_lock:
                    self._active_parallel += 1
                    self._max_parallel = max(self._max_parallel, self._active_parallel)
                try:
                    return run_pwsh_command(cmd, timeout)
                finally:
                    with self._parallel_lock:
                        self._active_parallel -= 1
            # 默认串行：persistent pwsh 保持会话状态，锁保证顺序与不重叠。
            with self._serial_lock:
                started_at = time.monotonic()
                if self._pwsh is None:
                    try:
                        self._pwsh = PersistentPwsh()
                    except DemoError as exc:
                        return CommandResult(-1, stderr=str(exc), error_kind="pwsh_missing")
                return self._pwsh.execute(cmd, timeout)
        finally:
            with self._records_lock:
                self._records.append(
                    CommandRecord(
                        token=self.token,
                        mode=mode,
                        cmd=cmd,
                        started_at=started_at,
                        finished_at=time.monotonic(),
                    )
                )

    def records(self) -> List[CommandRecord]:
        with self._records_lock:
            return list(self._records)

    def stats(self) -> Dict[str, Any]:
        records = self.records()
        with self._parallel_lock:
            max_parallel = self._max_parallel
        return {
            "user": self.user,
            "skill_port": self.daemon.port,
            "arrivals": len(self.daemon.arrivals()),
            "serial_commands": sum(1 for record in records if record.mode == "serial"),
            "parallel_commands": sum(1 for record in records if record.mode == "parallel"),
            "max_parallel_in_use": max_parallel,
            "max_workers": self.max_workers,
        }

    def close(self) -> None:
        self._executor.shutdown(wait=True)
        if self._pwsh is not None:
            self._pwsh.close()


class MiddleLayer:
    """完整业务中层：注册流程 + token 路由 + 两个业务接口。"""

    _USER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
    _TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

    def __init__(
        self,
        state_root: Optional[Path] = None,
        max_workers: int = 32,
    ) -> None:
        self.state_root = Path(
            state_root if state_root is not None else tempfile.mkdtemp(prefix="vb-full-demo-")
        )
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.deploy_root = self.state_root / "deploy"
        self.registry = Registry(self.state_root / "registry.json")
        self.max_workers = max_workers
        self._lock = threading.RLock()
        self._runtimes: Dict[str, TokenRuntime] = {}
        self._users: Dict[str, TokenRuntime] = {}
        self._daemons: Dict[str, SkillDaemon] = {}

    # ------------------------------------------------------- 注册四步流程

    def register(self, user: str, token: Optional[str] = None) -> Dict[str, Any]:
        if not self._USER_RE.fullmatch(user):
            raise RegistrationError("invalid user name: {}".format(user))
        final_token = token or uuid.uuid4().hex
        if not self._TOKEN_RE.fullmatch(final_token):
            raise RegistrationError("invalid token: {}".format(final_token))
        with self._lock:
            if self.registry.get(user) is not None:
                raise RegistrationError("user already registered: {}".format(user))
            for existing_user in self.registry.users():
                existing = self.registry.get(existing_user) or {}
                if existing.get("token") == final_token:
                    raise RegistrationError("token already registered")
            port = self._pick_free_port()
            entry = {
                "token": final_token,
                "mode": "local",
                "route": {
                    "skill": {"host": "127.0.0.1", "port": port},
                    "command": {"shell": "pwsh"},
                },
                "expected": {
                    "daemon_endpoint_hostname": socket.gethostname(),
                    "daemon_user": getpass.getuser(),
                    "python_executable": sys.executable,
                },
                "setup_path": str(self.deploy_root / user / "virtuoso_setup.il"),
                "identity_path": str(self.deploy_root / user / "daemon_identity.txt"),
                "registered_at": time.time(),
            }
            self.registry.put(user, entry)
            return json.loads(json.dumps(entry))

    def _pick_free_port(self) -> int:
        while True:
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                probe.bind(("127.0.0.1", 0))
                port = int(probe.getsockname()[1])
            finally:
                probe.close()
            used = any(
                ((self.registry.get(user) or {}).get("route") or {})
                .get("skill", {})
                .get("port")
                == port
                for user in self.registry.users()
            )
            if not used:
                return port

    def deploy(self, user: str) -> Dict[str, str]:
        raw = self.registry.get(user)
        if raw is None:
            raise RegistrationError("unknown user: {}".format(user))
        setup = Path(raw["setup_path"])
        identity = Path(raw["identity_path"])
        root = setup.parent
        root.mkdir(parents=True, exist_ok=True)
        setup.write_text(
            "; demo setup (token injected as il constant)\n"
            '(setq vb_demo_token "{}")\n'
            '(printf "[DEMO] token=%s\\n" vb_demo_token)\n'.format(raw["token"]),
            encoding="utf-8",
        )
        identity.write_text(raw["token"] + "\n", encoding="utf-8")
        daemon = root / "daemon.py"
        daemon.write_text(
            "# placeholder: real deployment would copy daemon.py here\n",
            encoding="utf-8",
        )
        return {
            "setup_path": str(setup),
            "identity_path": str(identity),
            "daemon_path": str(daemon),
        }

    def load(self, user: str, daemon_delay: float = 0.0) -> Dict[str, Any]:
        raw = self.registry.get(user)
        if raw is None:
            raise RegistrationError("unknown user: {}".format(user))
        setup = Path(raw["setup_path"])
        if not setup.exists():
            raise RegistrationError("deploy must complete before load")
        if raw["token"] not in setup.read_text(encoding="utf-8"):
            raise RegistrationError("setup does not contain the injected token")
        host = str(raw["route"]["skill"]["host"])
        port = int(raw["route"]["skill"]["port"])
        token = str(raw["token"])
        with self._lock:
            if user in self._users:
                raise RegistrationError("user already loaded: {}".format(user))
            daemon = SkillDaemon(
                endpoint=user,
                host=host,
                port=port,
                token=token,
                delay=daemon_delay,
            )
            runtime = TokenRuntime(
                token=token,
                user=user,
                daemon=daemon,
                max_workers=self.max_workers,
            )
            self._daemons[user] = daemon
            self._users[user] = runtime
            self._runtimes[token] = runtime
        print("[DEMO load] user={} token={} port={}".format(user, token, port))
        return {"user": user, "token": token, "skill_port": port}

    def connect(self, user: str) -> Dict[str, Any]:
        raw = self.registry.get(user)
        if raw is None:
            raise RegistrationError("unknown user: {}".format(user))
        if user not in self._users:
            raise RegistrationError("not loaded: {}".format(user))
        token = str(raw["token"])
        command_smoke = self.run_command("Write-Output vb-ok", token=token)
        skill_smoke = self.execute_skill("1+1", token=token)
        success = bool(command_smoke.ok and "vb-ok" in command_smoke.stdout and skill_smoke.ok)
        return {
            "success": success,
            "command_smoke": command_smoke.to_dict(),
            "skill_smoke": skill_smoke.to_dict(),
            "token": token,
        }

    def register_and_start(
        self,
        user: str,
        token: Optional[str] = None,
        daemon_delay: float = 0.0,
    ) -> Dict[str, Any]:
        entry = self.register(user, token=token)
        self.deploy(user)
        loaded = self.load(user, daemon_delay=daemon_delay)
        connected = self.connect(user)
        return {"user": user, "entry": entry, "loaded": loaded, "connected": connected}

    # ------------------------------------------------------- 两个业务接口

    def execute_skill(
        self,
        skill_code: str,
        timeout: Optional[float] = None,
        token: Optional[str] = None,
    ) -> SkillResult:
        if not token:
            return SkillResult("error", errors=["token is required"])
        with self._lock:
            runtime = self._runtimes.get(token)
        if runtime is None:
            return SkillResult("error", errors=["unknown token"])
        return runtime.execute_skill(skill_code, timeout=timeout)

    def run_command(
        self,
        cmd: str,
        timeout: Optional[float] = None,
        token: Optional[str] = None,
        parallel: bool = False,
    ) -> CommandResult:
        if not token:
            return CommandResult(-1, stderr="token is required", error_kind="invalid_token")
        with self._lock:
            runtime = self._runtimes.get(token)
        if runtime is None:
            return CommandResult(-1, stderr="unknown token", error_kind="invalid_token")
        return runtime.run_command(cmd, timeout=timeout, parallel=parallel)

    # ------------------------------------------------------------- 观测接口

    def arrivals(self, token: str) -> List[Arrival]:
        with self._lock:
            runtime = self._runtimes.get(token)
        if runtime is None:
            raise DemoError("unknown token")
        return runtime.daemon.arrivals()

    def command_records(self, token: str) -> List[CommandRecord]:
        with self._lock:
            runtime = self._runtimes.get(token)
        if runtime is None:
            raise DemoError("unknown token")
        return runtime.records()

    def stats(self, token: str) -> Dict[str, Any]:
        with self._lock:
            runtime = self._runtimes.get(token)
        if runtime is None:
            raise DemoError("unknown token")
        return runtime.stats()

    def close(self) -> None:
        with self._lock:
            runtimes = list(self._runtimes.values())
            daemons = list(self._daemons.values())
            self._runtimes.clear()
            self._users.clear()
            self._daemons.clear()
        for runtime in runtimes:
            runtime.close()
        for daemon in daemons:
            daemon.close()


def run_demo() -> Dict[str, Any]:
    """注册两个用户，演示 token 路由、串行状态、单用户并行和跨用户并行。"""

    with tempfile.TemporaryDirectory(prefix="vb-full-demo-") as temporary:
        middle = MiddleLayer(Path(temporary))
        try:
            alice = middle.register_and_start("alice", token="alice-prod", daemon_delay=0.05)
            bob = middle.register_and_start("bob", token="bob-prod", daemon_delay=0.05)

            # 1) 默认串行 + persistent shell 状态保持：$vb_counter 跨命令可见。
            middle.run_command("$vb_counter=41", token="alice-prod")
            state = middle.run_command("Write-Output ($vb_counter+1)", token="alice-prod")

            # 2) 单用户内 parallel=True：两条独立命令并行跑。
            parallel_start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=2) as callers:
                futures = [
                    callers.submit(
                        lambda label: middle.run_command(
                            "Start-Sleep -Milliseconds 300; Write-Output {}".format(label),
                            token="alice-prod",
                            parallel=True,
                        ),
                        "p{}".format(index),
                    )
                    for index in range(2)
                ]
                parallel_results = [future.result() for future in futures]
            parallel_elapsed_ms = (time.perf_counter() - parallel_start) * 1000.0

            # 3) 跨用户 execute_skill 并行：到达各自端口即成功。
            skill_start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=2) as callers:
                skill_futures = [
                    callers.submit(
                        middle.execute_skill,
                        "skill-{}".format(label),
                        None,
                        token,
                    )
                    for label, token in (("alice", "alice-prod"), ("bob", "bob-prod"))
                ]
                skill_results = [future.result() for future in skill_futures]
            skill_elapsed_ms = (time.perf_counter() - skill_start) * 1000.0

            summary = {
                "registry_users": middle.registry.users(),
                "alice_connect": alice["connected"],
                "bob_connect": bob["connected"],
                "serial_state_after_41_plus_1": state.stdout,
                "parallel_commands": {
                    "results": [result.to_dict() for result in parallel_results],
                    "elapsed_ms": round(parallel_elapsed_ms, 2),
                },
                "skill_arrivals": {
                    "alice": [
                        {
                            "skill": arrival.skill,
                            "token": arrival.token,
                            "endpoint": arrival.endpoint,
                        }
                        for arrival in middle.arrivals("alice-prod")
                    ],
                    "bob": [
                        {
                            "skill": arrival.skill,
                            "token": arrival.token,
                            "endpoint": arrival.endpoint,
                        }
                        for arrival in middle.arrivals("bob-prod")
                    ],
                    "elapsed_ms": round(skill_elapsed_ms, 2),
                },
                "alice_stats": middle.stats("alice-prod"),
                "bob_stats": middle.stats("bob-prod"),
            }
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return summary
        finally:
            middle.close()


if __name__ == "__main__":
    run_demo()
