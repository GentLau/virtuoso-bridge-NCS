"""L0 contracts for ``pyapi.packages.spectre`` (validation, command build, triage).

这些层在真机 TB 里只以"跑通/跑不通"的形式出现；这里把它们钉成可断言的契约：
命令行怎么拼、哪些日志算致命、哪些输入必须被拒。
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pyapi.models import CommandResult, ExecutionStatus, VirtuosoResult
from pyapi.packages import spectre as S


class FakeMiddle:
    def __init__(self, *results: VirtuosoResult) -> None:
        self.calls: list[tuple[str, str]] = []
        self.queue = list(results)

    def execute_skill(self, skill_code, timeout=None, *, token):
        self.calls.append((token, skill_code))
        return self.queue.pop(0) if self.queue else VirtuosoResult(
            status=ExecutionStatus.SUCCESS, output='("ok")')

    def query(self, *, token, role=None, name=None):
        raise RuntimeError("query not stubbed")


class TestValidators(unittest.TestCase):
    def test_require_text_and_timeout(self):
        self.assertEqual(S._require_text(" spectre ", "n"), " spectre ")
        for bad in ("", "   ", None, 5):
            with self.assertRaises(ValueError) as ctx:
                S._require_text(bad, "spectre_bin")
            self.assertIn("spectre_bin", str(ctx.exception))
        S._require_timeout(None)
        S._require_timeout(2.5)
        for bad in (0, -1, "2", float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                S._require_timeout(bad)

    def test_require_bool_and_job(self):
        self.assertTrue(S._require_bool(True, "download"))
        for bad in (1, "true", None):
            with self.assertRaises(ValueError) as ctx:
                S._require_bool(bad, "download")
            self.assertIn("download", str(ctx.exception))
        self.assertEqual(S._require_job("job-1"), "job-1")
        for bad in ("", "a/b", "a\\b", "..", "-lead", "with space", None):
            with self.assertRaises(ValueError):
                S._require_job(bad)

    def test_require_mode_and_analysis_and_parse(self):
        for mode in S._MODES:
            self.assertEqual(S._require_mode(mode), mode)
        with self.assertRaises(ValueError) as ctx:
            S._require_mode("turbo")
        self.assertIn("mode", str(ctx.exception))
        for analysis in S._ANALYSES:
            self.assertEqual(S._require_analysis(analysis), analysis)
        with self.assertRaises(ValueError):
            S._require_analysis("fft")
        self.assertEqual(S._require_parse("auto"), "auto")
        with self.assertRaises(ValueError):
            S._require_parse("partial")

    def test_safe_name_and_split_bin(self):
        self.assertEqual(S._safe_name("inv/1 out"), "inv_1_out")
        self.assertEqual(S._safe_name(""), "result")
        self.assertEqual(S._split_bin("spectre -64"), ["spectre", "-64"])
        self.assertEqual(S._split_bin("/opt/x/spectre ++aps"), ["/opt/x/spectre", "++aps"])


class TestCommandBuilders(unittest.TestCase):
    def test_build_spectre_command_defaults(self):
        cmd = S._build_spectre_command(
            "spectre", "/run/dir", "inv.scs", "inv", [], "spectre")
        self.assertTrue(cmd.startswith("cd /run/dir && "))
        for needle in ("spectre", "-64", "inv.scs", "+escchars", "+log",
                       "/run/dir/spectre.out", "-format", "psfascii", "-raw",
                       "/run/dir/inv.raw", "+lqtimeout", "900", "-maxw", "5",
                       "-maxn", "5", "+logstatus"):
            self.assertIn(needle, cmd)

    def test_build_spectre_command_respects_user_overrides(self):
        cmd = S._build_spectre_command(
            "spectre", "/r", "n.scs", "n", ["-32", "+lqtimeout", "60", "-maxw", "1"],
            "spectre")
        self.assertIn("-32", cmd)
        self.assertNotIn("-64", cmd)           # 用户已给 -32，不再补 -64
        self.assertIn("60", cmd)               # 用户 +lqtimeout 生效
        self.assertNotIn("900", cmd)
        self.assertIn("-maxw 1", cmd)

    def test_build_spectre_command_mode_args_and_quoting(self):
        cmd = S._build_spectre_command(
            "spectre", "/run dir", "my net.scs", "my net", [], "aps")
        self.assertIn("+aps", cmd)
        self.assertIn("'/run dir'", cmd)       # shlex 会为含空格路径加引号
        self.assertIn("'my net.scs'", cmd)

    def test_prepare_command_shape(self):
        cmd = S._prepare_command("/run/dir")
        self.assertIn("mkdir -p", cmd)
        self.assertIn("exit 9", cmd)
        self.assertIn("EXISTS", cmd)
        self.assertIn("READY", cmd)


class TestLogTriage(unittest.TestCase):
    def test_has_fatal_ignores_zero_error_summary(self):
        self.assertFalse(S._has_fatal("spectre completes with 0 errors, 0 warnings"))
        self.assertFalse(S._has_fatal("all good"))

    def test_has_fatal_detects_markers(self):
        for text in (
            "ERROR (SFE-23): undefined model",
            "Error reading netlist",
            "read-in failed",
            "License error: denied",
            "SPCRTRF-15044 something",
            "failed to converge",
            "convergence failure",
            "spectre terminated prematurely due to fatal error",
            "Segmentation fault",
        ):
            self.assertTrue(S._has_fatal(text), text)

    def test_classify_errors_priority(self):
        self.assertEqual(S._classify_errors("ERROR (SFE-23): error reading"),
                         ["netlist read error (missing include or syntax)"])
        self.assertEqual(S._classify_errors("License ERROR: license denied"),
                         ["license error"])
        self.assertEqual(S._classify_errors("failed to converge"), ["convergence failure"])
        self.assertEqual(S._classify_errors("SPCRTRF-15044 boom"), ["convergence failure"])
        self.assertEqual(S._classify_errors("spectre terminated prematurely due to fatal error"),
                         ["spectre reported a fatal error"])
        self.assertEqual(S._classify_errors("0 errors, 0 warnings"), [])


class TestTaskValidation(unittest.TestCase):
    """`run()` 把所有异常收进 `Result(False, error=f"{type}: {msg}")`（不向调用方抛），
    所以校验错误要断言在 result.error 上。"""

    TASK = {"job": "j", "netlist": "/n.scs"}

    def _run(self, **fields):
        fields.setdefault("token", "t")
        return S.Package(FakeMiddle()).run(S.RunRequest(**fields))

    def test_rejects_unknown_mode_and_bad_workers(self):
        bad_mode = self._run(tasks=[self.TASK], mode="turbo")
        self.assertFalse(bad_mode.ok)
        self.assertIn("ValueError", bad_mode.error)
        self.assertIn("mode", bad_mode.error)
        for bad in (0, -1, True, "4"):
            result = self._run(tasks=[self.TASK], max_workers=bad)
            self.assertFalse(result.ok, f"max_workers={bad!r} should be rejected")
            self.assertIn("max_workers", result.error)

    def test_rejects_bad_parse_combinations(self):
        auto = self._run(tasks=[self.TASK], parse="auto", download=False)
        self.assertFalse(auto.ok)
        self.assertIn("download", auto.error)
        none_parse = self._run(tasks=[self.TASK], parse="none", keep_run_dir=False)
        self.assertFalse(none_parse.ok)
        self.assertIn("keep_run_dir", none_parse.error)

    def test_rejects_malformed_task_entries(self):
        for tasks in (
            ["not-a-dict"],
            [{"netlist": "/n.scs"}],
            [{"job": "j"}],
            [{"job": "bad/name", "netlist": "/n.scs"}],
            [{"job": "j", "netlist": "/n.scs", "include_files": "x"}],
            [{"job": "j", "netlist": "/n.scs", "spectre_args": [""]}],
            [{"job": "j", "netlist": "/n.scs", "mode": "turbo"}],
        ):
            result = self._run(tasks=tasks)
            self.assertFalse(result.ok, f"{tasks!r} should be rejected")
            self.assertIn("ValueError", result.error)

    def test_rejects_duplicate_jobs(self):
        result = self._run(tasks=[{"job": "j", "netlist": "/a.scs"},
                                  {"job": "j", "netlist": "/b.scs"}])
        self.assertFalse(result.ok)
        self.assertIn("unique", result.error)

    def test_normalize_tasks_defaults(self):
        request = S.RunRequest(token="t", tasks=[{"job": "j", "netlist": "/n.scs"}])
        normalized = S._normalize_tasks(request)
        self.assertEqual(normalized[0]["include_files"], [])
        self.assertIsNone(normalized[0]["mode"])
        self.assertIsNone(normalized[0]["spectre_args"])
        defaults = S._task_defaults(request)
        self.assertEqual(defaults["parse"], "auto")
        self.assertTrue(defaults["download"])
        self.assertFalse(defaults["keep_run_dir"])


#: 供 run 编排用例使用的 PSF（tran，3 点；与真机产物同格式）
TRAN_PSF = """HEADER
"PSFversion" "1.00"
"simulator" "spectre"
"analysis type" "tran"
"analysis name" "tran1"
TYPE
"sweep" FLOAT DOUBLE PROP(
"key" "sweep"
)
"V" FLOAT DOUBLE PROP(
"units" "V"
"key" "node"
)
SWEEP
"time" "sweep" PROP(
"sweep_direction" 0
"units" "s"
)
TRACE
"vout" "V"
VALUE
"time" 0.000000000000000e+00
"vout" 0.000000000000000e+00
"time" 1.000000000000000e-09
"vout" 1.000000000000000e+00
END
"""


class _Role:
    def __init__(self, root: str, bin_text: str | None) -> None:
        self.root = root
        self.bin = bin_text


class _Status:
    value = "success"


class _Facts:
    def __init__(self) -> None:
        self.status = _Status()
        self.roles = {"spectre": _Role("/role/spectre", "/opt/spectre/bin/spectre")}


class RunMiddle(FakeMiddle):
    """Record-answering middle for ``run()`` orchestration tests.

    ``download_file`` 会**真的把文件造出来**（raw 目录里放一份 PSF、再放 spectre.out），
    否则 parse='auto' 那一步永远走不到——用返回值假装成功是在骗自己。
    """

    def __init__(self, *, execute_rc: int = 0, execute_out: str = "",
                 execute_err: str = "", kind: str = "command",
                 prepare_rc: int = 0, make_raw: bool = True) -> None:
        super().__init__()
        self.commands: list[str] = []
        self.executed: list[str] = []
        self.execute_rc = execute_rc
        self.execute_out = execute_out
        self.execute_err = execute_err
        self.kind = kind
        self.prepare_rc = prepare_rc
        self.make_raw = make_raw
        self.include_uploads: list[str] = []

    def query(self, *, token, role=None, name=None):
        return _Facts()

    def run_spectre_command(self, cmd, timeout=None, *, token):
        self.executed.append(cmd)
        if cmd.startswith("mkdir -p") or "EXISTS" in cmd:
            out = "READY\n" if self.prepare_rc == 0 else "EXISTS\n"
            return CommandResult(self.prepare_rc, out, "", "command")
        if cmd.startswith("rm -rf"):
            return CommandResult(0, "", "", "command")
        return CommandResult(self.execute_rc, self.execute_out, self.execute_err, self.kind)

    def upload_file(self, local_path, remote_path, timeout=None, *, token, recursive=False):
        self.include_uploads.append(str(remote_path))
        return CommandResult(0, str(remote_path), "", "command")

    def download_file(self, remote_path, local_path, timeout=None, *, token, recursive=False):
        local = Path(local_path)
        if str(remote_path).endswith(".raw"):
            if self.make_raw:
                local.mkdir(parents=True, exist_ok=True)
                (local / "tran1.tran.tran").write_text(TRAN_PSF, encoding="utf-8")
            return CommandResult(0, "", "", "command")
        if str(remote_path).endswith("spectre.out"):
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_text("spectre completes with 0 errors, 0 warnings\n",
                             encoding="utf-8")
            return CommandResult(0, str(local), "", "command")
        return CommandResult(1, "", f"download requires a regular file: {remote_path} (missing)",
                             "path")


class TestRunOrchestration(unittest.TestCase):
    def _run(self, middle, netlist: Path, **fields):
        fields.setdefault("tasks", [{"job": "job1", "netlist": str(netlist)}])
        fields.setdefault("token", "t")
        fields.setdefault("output_root", str(netlist.parent))
        return S.Package(middle).run(S.RunRequest(**fields))

    def _netlist(self, tmp: Path) -> Path:
        path = tmp / "inv.scs"
        path.write_text("simulator lang=spectre\n", encoding="utf-8")
        return path

    def test_happy_path_parses_raw_and_cleans_up(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            middle = RunMiddle()
            result = self._run(middle, self._netlist(Path(tmp)))
        self.assertTrue(result.ok, result.error)
        value = result.value["runs"][0]["value"]
        self.assertEqual(value["status"], "success")
        self.assertEqual(value["result_kind"], "raw")
        self.assertEqual(value["analyses"], ["tran"])
        self.assertEqual(value["data"]["vout"], [0.0, 1.0])
        self.assertEqual(value["transport_kind"], "command")
        self.assertTrue(any(str(item).endswith("tran1.tran.tran")
                            for item in value["output_files"]), value["output_files"])
        names = [step["name"] for step in result.value["runs"][0]["steps"]]
        for expected in ("prepare", "upload_netlist", "execute", "download_raw", "cleanup"):
            self.assertIn(expected, names)
        executed_netlist = [c for c in middle.executed if "inv.scs" in c]
        self.assertTrue(executed_netlist, middle.executed)
        self.assertIn("+escchars", executed_netlist[0])

    def test_keep_run_dir_skips_cleanup(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            middle = RunMiddle()
            result = self._run(middle, self._netlist(Path(tmp)), keep_run_dir=True)
        self.assertTrue(result.ok, result.error)
        names = [step["name"] for step in result.value["runs"][0]["steps"]]
        self.assertNotIn("cleanup", names)
        self.assertFalse(any(cmd.startswith("rm -rf") for cmd in middle.executed))

    def test_prepare_failure_reports_run_dir_not_empty(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            middle = RunMiddle(prepare_rc=9)
            result = self._run(middle, self._netlist(Path(tmp)))
        self.assertFalse(result.ok)
        run = result.value["runs"][0]
        self.assertEqual(run["error"], "run directory is not empty")
        self.assertEqual(run["value"]["status"], "error")

    def test_execute_failure_classified_and_status_failure(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            # make_raw=False：读入就失败时不会有 .raw，状态应为 failure（有 raw 才是 partial）
            middle = RunMiddle(execute_rc=1, execute_err="Error reading netlist",
                               make_raw=False)
            result = self._run(middle, self._netlist(Path(tmp)))
        self.assertFalse(result.ok)
        value = result.value["runs"][0]["value"]
        self.assertEqual(value["status"], "failure")
        self.assertIn("netlist read error", " ".join(value["errors"]))

    def test_fatal_output_with_raw_present_is_partial(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            middle = RunMiddle(execute_rc=1,
                               execute_out="spectre terminated prematurely due to fatal error")
            result = self._run(middle, self._netlist(Path(tmp)))
        value = result.value["runs"][0]["value"]
        self.assertEqual(value["status"], "partial")
        self.assertIn("failure to converge" if False else "spectre", " ".join(value["errors"]))

    def test_transport_kind_is_reported_as_error(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            middle = RunMiddle(kind="transport", execute_rc=255, execute_err="connection lost")
            result = self._run(middle, self._netlist(Path(tmp)))
        value = result.value["runs"][0]["value"]
        self.assertEqual(value["status"], "error")
        self.assertIn("spectre transport failure (transport)", " ".join(value["errors"]))
        self.assertIn("connection lost", " ".join(value["errors"]))

    def test_missing_raw_marks_error(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            middle = RunMiddle(make_raw=False)
            result = self._run(middle, self._netlist(Path(tmp)))
        value = result.value["runs"][0]["value"]
        self.assertEqual(value["status"], "error")
        self.assertIn("raw output directory is missing", value["errors"])

    def test_missing_netlist_and_duplicate_basenames(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            tmp_path = Path(tmp)
            missing = self._run(RunMiddle(), tmp_path / "nope.scs")
            self.assertFalse(missing.ok)
            self.assertIn("netlist not found", missing.value["runs"][0]["error"])

            netlist = self._netlist(tmp_path)
            include = tmp_path / "sub" / "inv.scs"
            include.parent.mkdir()
            include.write_text("x", encoding="utf-8")
            clash = self._run(RunMiddle(), netlist, tasks=[{
                "job": "job1", "netlist": str(netlist),
                "include_files": [str(include)]}])
            self.assertFalse(clash.ok)
            self.assertIn("basenames must be unique", clash.value["runs"][0]["error"])

    def test_include_files_are_uploaded(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            tmp_path = Path(tmp)
            netlist = self._netlist(tmp_path)
            include = tmp_path / "models.scs"
            include.write_text("* models\n", encoding="utf-8")
            middle = RunMiddle()
            result = self._run(middle, netlist, tasks=[{
                "job": "job1", "netlist": str(netlist),
                "include_files": [str(include)]}])
        self.assertTrue(result.ok, result.error)
        self.assertTrue(any(item.endswith("models.scs") for item in middle.include_uploads))
        names = [step["name"] for step in result.value["runs"][0]["steps"]]
        self.assertIn("upload_include:models.scs", names)


class ResultsMiddle(FakeMiddle):
    """download_file 会真的造出本地 raw 目录，供 read_results 解析。"""

    def __init__(self, *, dir_ok: bool = True, file_ok: bool = True) -> None:
        super().__init__()
        self.dir_ok = dir_ok
        self.file_ok = file_ok

    def download_file(self, remote_path, local_path, timeout=None, *, token, recursive=False):
        local = Path(local_path)
        if recursive:
            if not self.dir_ok:
                return CommandResult(1, "", "no such remote dir", "path")
            local.mkdir(parents=True, exist_ok=True)
            (local / "tran1.tran.tran").write_text(TRAN_PSF, encoding="utf-8")
            return CommandResult(0, "", "", "command")
        if not self.file_ok:
            return CommandResult(1, "", "no such remote file", "path")
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(TRAN_PSF, encoding="utf-8")
        return CommandResult(0, str(local), "", "command")


class TestReadResults(unittest.TestCase):
    def test_raw_directory_layout(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            result = S.Package(ResultsMiddle()).read_results(
                S.ReadResultsRequest(token="t", source="/remote/job.raw",
                                     output_dir=tmp, timeout=30))
        self.assertTrue(result.ok, result.error)
        value = result.value
        self.assertEqual(value["kind"], "raw")
        self.assertEqual(value["analyses"], ["tran"])
        self.assertEqual(value["signals"], ["time", "vout"])
        self.assertEqual(value["data"]["vout"], [0.0, 1.0])
        self.assertEqual(value["point_count"], 0)
        self.assertTrue(value["files"] and value["files"][0].endswith("tran1.tran.tran"))

    def test_directory_download_falls_back_to_file(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            result = S.Package(ResultsMiddle(dir_ok=False)).read_results(
                S.ReadResultsRequest(token="t", source="/remote/job.raw",
                                     output_dir=tmp, timeout=30))
        self.assertTrue(result.ok, result.error)
        names = [step["name"] for step in result.steps]
        self.assertIn("download_dir", names)

    def test_both_downloads_failing_is_reported(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            result = S.Package(ResultsMiddle(dir_ok=False, file_ok=False)).read_results(
                S.ReadResultsRequest(token="t", source="/remote/job.raw",
                                     output_dir=tmp, timeout=30))
        self.assertFalse(result.ok)
        self.assertIn("no such remote", result.error)

    def test_analysis_argument_is_validated(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            with self.assertRaises(ValueError):
                S.Package(ResultsMiddle()).read_results(
                    S.ReadResultsRequest(token="t", source="/r", analysis="fft",
                                         output_dir=tmp))


class TestExport(unittest.TestCase):
    DATA = {"time": [0.0, 1e-9, 2e-9], "vout": [0.0, 1.0, 2.0]}

    def _export(self, tmp: str, **fields):
        fields.setdefault("token", "t")
        fields.setdefault("format", "csv")
        fields.setdefault("data", self.DATA)
        fields.setdefault("output_path", str(Path(tmp) / "out.csv"))
        return S.Package(FakeMiddle()).export(S.ExportRequest(**fields))

    def test_csv_export_writes_rows(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            result = self._export(tmp)
            path = Path(result.value["output_path"])
            text = path.read_text(encoding="utf-8")
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value["format"], "csv")
        self.assertEqual(result.value["columns"], ["time", "vout"])
        self.assertEqual(result.value["rows"], 3)
        self.assertGreater(result.value["bytes"], 0)
        self.assertTrue(text.startswith("time,vout"))
        self.assertIn("1e-09,1", text)

    def test_json_export_and_column_selection(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            result = self._export(tmp, format="json",
                                  output_path=str(Path(tmp) / "out.json"),
                                  columns=["vout"])
            payload = json.loads(Path(result.value["output_path"]).read_text(encoding="utf-8"))
        self.assertTrue(result.ok, result.error)
        # spec §8：JSON 侧写 `{"format","metadata","data"}` 信封；columns 是 **CSV 专属**
        # 参数，对 JSON 请求不生效（实现按 spec 处理，这里把两件事都钉住）。
        self.assertEqual(result.value["columns"], ["time", "vout"])
        self.assertEqual(payload["format"], "json")
        self.assertEqual(payload["metadata"], {"columns": ["time", "vout"], "rows": 3})
        self.assertEqual(payload["data"]["vout"], [0.0, 1.0, 2.0])

    def test_precision_and_validation_errors(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            precise = self._export(tmp, precision=3)
            self.assertTrue(precise.ok, precise.error)
            # columns=[] 按实现等价于"未指定"（`if requested_columns:` 为假）→ 导出全部列。
            # 这里钉住现状：空列表不报错。
            all_columns = self._export(tmp, columns=[])
            self.assertTrue(all_columns.ok, all_columns.error)
            self.assertEqual(all_columns.value["columns"], ["time", "vout"])
            for fields in ({"format": "xlsx"}, {"columns": [1]},
                           {"precision": 0}, {"precision": 17}, {"precision": True}):
                bad = self._export(tmp, **fields)
                self.assertFalse(bad.ok, f"{fields!r} should be rejected")
                self.assertIn("ValueError", bad.error)

    def test_unknown_column_is_reported(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            bad = self._export(tmp, columns=["nope"])
            self.assertFalse(bad.ok)
            self.assertIn("not present in data", bad.error)

    def test_load_data_requires_exactly_one_source(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            both = self._export(tmp, source_path=str(Path(tmp) / "x.json"))
            self.assertFalse(both.ok)
            self.assertIn("exactly one", both.error)

            neither = S.Package(FakeMiddle()).export(S.ExportRequest(
                token="t", format="csv", output_path=str(Path(tmp) / "x.csv")))
            self.assertFalse(neither.ok)
            self.assertIn("exactly one", neither.error)

    def test_load_data_from_source_path(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            source = Path(tmp) / "data.json"
            source.write_text(json.dumps(self.DATA), encoding="utf-8")
            result = S.Package(FakeMiddle()).export(S.ExportRequest(
                token="t", format="csv", source_path=str(source),
                output_path=str(Path(tmp) / "out.csv")))
            self.assertTrue(result.ok, result.error)
            self.assertEqual(result.value["rows"], 3)

            broken = Path(tmp) / "broken.json"
            broken.write_text("{not json", encoding="utf-8")
            bad = S.Package(FakeMiddle()).export(S.ExportRequest(
                token="t", format="csv", source_path=str(broken),
                output_path=str(Path(tmp) / "out2.csv")))
            self.assertFalse(bad.ok)
            self.assertIn("not valid JSON", bad.error)

            scalar = Path(tmp) / "scalar.json"
            scalar.write_text("[1,2]", encoding="utf-8")
            wrong = S.Package(FakeMiddle()).export(S.ExportRequest(
                token="t", format="csv", source_path=str(scalar),
                output_path=str(Path(tmp) / "out3.csv")))
            self.assertFalse(wrong.ok)
            self.assertIn("must contain an object", wrong.error)


class LicenseMiddle:
    """spectre.check_license 的假 middle（版本 + lmstat 两条接口 + 兜底回退）。"""

    VERSION_LINE = "@(#)$CDS: spectre version 24.1.0 64bit 09/14/2024 $"

    def __init__(self, *, version_stdout: str | None = None, version_rc: int = 0,
                 lmstat_cmd_rc: int = 0, lmstat_cmd_stdout: str = "",
                 lmstat_cmd_stderr: str = "",
                 lmstat_spectre_rc: int = 0, lmstat_spectre_stdout: str = "",
                 lmstat_spectre_stderr: str = "") -> None:
        self.version_stdout = (self.VERSION_LINE if version_stdout is None
                               else version_stdout)
        self.version_rc = version_rc
        self.lmstat_cmd_rc = lmstat_cmd_rc
        self.lmstat_cmd_stdout = lmstat_cmd_stdout
        self.lmstat_cmd_stderr = lmstat_cmd_stderr
        self.lmstat_spectre_rc = lmstat_spectre_rc
        self.lmstat_spectre_stdout = lmstat_spectre_stdout
        self.lmstat_spectre_stderr = lmstat_spectre_stderr
        self.spectre_commands: list[str] = []
        self.commands: list[str] = []

    def query(self, *, token, role=None, name=None):
        from pyapi.models import ExecutionStatus

        class _Status:
            value = "success"

        class _Role:
            root = "/role/spectre"
            bin = "/opt/spectre/bin/spectre"

        class _Facts:
            status = _Status()
            roles = {"spectre": _Role()}

        return _Facts()

    def run_spectre_command(self, cmd, timeout=None, *, token):
        from pyapi.models import CommandResult
        self.spectre_commands.append(cmd)
        if cmd.endswith("-V"):
            return CommandResult(self.version_rc, self.version_stdout, "", "command")
        return CommandResult(self.lmstat_spectre_rc, self.lmstat_spectre_stdout,
                             self.lmstat_spectre_stderr, "command")

    def run_command(self, cmd, timeout=None, *, token, parallel=False):
        from pyapi.models import CommandResult
        self.commands.append(cmd)
        return CommandResult(self.lmstat_cmd_rc, self.lmstat_cmd_stdout,
                             self.lmstat_cmd_stderr, "command")


class TestCheckLicense(unittest.TestCase):
    def test_licenses_from_lmstat_command(self):
        middle = LicenseMiddle(
            lmstat_cmd_stdout="Users of Virtuoso_Spectre:  (Total of 10 licenses issued)\n"
                              "Users of Virtuoso_Spectre:  (Total of 4 licenses in use)\n")
        result = S.Package(middle).check_license(S.CheckLicenseRequest(token="t"))
        self.assertTrue(result.ok, result.error)
        value = result.value
        self.assertEqual(value["lmstat_interface"], "command")
        self.assertEqual(len(value["licenses"]), 2)
        self.assertEqual(value["version"], LicenseMiddle.VERSION_LINE)
        self.assertEqual(value["warnings"], [])
        self.assertEqual([step["name"] for step in result.steps],
                         ["version", "lmstat_command"])
        self.assertFalse(any("lmstat -a" in c for c in middle.spectre_commands))

    def test_falls_back_to_spectre_interface(self):
        middle = LicenseMiddle(lmstat_cmd_rc=127, lmstat_cmd_stderr="sh: lmstat: not found",
                               lmstat_spectre_stdout="Users of Virtuoso_Spectre: (Total of 2)\n")
        result = S.Package(middle).check_license(S.CheckLicenseRequest(token="t"))
        self.assertTrue(result.ok, result.error)
        value = result.value
        self.assertEqual(value["lmstat_interface"], "spectre")
        self.assertEqual(len(value["licenses"]), 1)
        self.assertIn("lmstat -a", middle.spectre_commands)
        self.assertEqual([step["name"] for step in result.steps],
                         ["version", "lmstat_command", "lmstat_spectre"])

    def test_no_licenses_yields_warning_and_error_line(self):
        middle = LicenseMiddle(lmstat_cmd_rc=1, lmstat_cmd_stderr="",
                               lmstat_spectre_rc=1,
                               lmstat_spectre_stderr="Error getting status: down or not responding\n")
        result = S.Package(middle).check_license(S.CheckLicenseRequest(token="t"))
        self.assertTrue(result.ok, result.error)     # 版本拿到就算成功
        value = result.value
        self.assertEqual(value["licenses"], [])
        self.assertIn("down or not responding", value["lmstat_error"])
        self.assertEqual(value["warnings"],
                         ["license detail unavailable or shows no active users"])

    def test_empty_lmstat_stdout_also_falls_back(self):
        middle = LicenseMiddle(lmstat_cmd_rc=0, lmstat_cmd_stdout="   \n",
                               lmstat_spectre_stdout="Users of X: y\n")
        value = S.Package(middle).check_license(S.CheckLicenseRequest(token="t")).value
        self.assertEqual(value["lmstat_interface"], "spectre")

    def test_missing_version_fails_with_classified_errors(self):
        middle = LicenseMiddle(version_stdout="", version_rc=1,
                               lmstat_cmd_stdout="Users of X: y\n")
        result = S.Package(middle).check_license(S.CheckLicenseRequest(token="t"))
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "spectre version check failed")
        self.assertIsNone(result.value["version"])
        self.assertEqual(result.value["errors"], [])

    def test_explicit_bin_overrides_query_and_is_quoted(self):
        middle = LicenseMiddle(lmstat_cmd_stdout="Users of X: y\n")
        result = S.Package(middle).check_license(S.CheckLicenseRequest(
            token="t", spectre_bin="/opt/my spectre/bin/spectre -64"))
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value["bin"], "/opt/my spectre/bin/spectre -64")
        version_call = [c for c in middle.spectre_commands if c.endswith("-V")][0]
        # `spectre_bin` 语义是"命令前缀"：按空白切分 argv（spec §7 `spectre_bin`）。
        # 因此**路径里带空格会被当成参数分隔**（钉住现状；真机路径不含空格，不影响）。
        self.assertEqual(version_call, "/opt/my spectre/bin/spectre -64 -V")

        clean = LicenseMiddle(lmstat_cmd_stdout="Users of X: y\n")
        S.Package(clean).check_license(S.CheckLicenseRequest(
            token="t", spectre_bin="/opt/spectre241/bin/spectre"))
        self.assertEqual([c for c in clean.spectre_commands if c.endswith("-V")][0],
                         "/opt/spectre241/bin/spectre -V")

    def test_query_failure_is_reported(self):
        class BadQuery(LicenseMiddle):
            def query(self, *, token, role=None, name=None):
                raise RuntimeError("no spectre role")

        result = S.Package(BadQuery()).check_license(S.CheckLicenseRequest(token="t"))
        self.assertFalse(result.ok)
        self.assertIn("no spectre role", result.error)


class TestMeasureExport(unittest.TestCase):
    DATA = {"time": [0.0, 1.0], "vout": [0.0, 2.0]}

    def test_measure_requires_non_empty_metrics(self):
        result = S.Package(FakeMiddle()).measure(
            S.MeasureRequest(token="t", metrics=[]))
        self.assertFalse(result.ok)
        self.assertIn("non-empty list", result.error)

    def test_measure_non_object_metric_is_structured(self):
        result = S.Package(FakeMiddle()).measure(S.MeasureRequest(
            token="t", data=self.DATA,
            metrics=[3, {"type": "max", "signal": "vout", "x": "time"}],
        ))
        self.assertFalse(result.ok)
        self.assertIn("metrics[0] must be an object", result.error)
        self.assertEqual(len(result.value["metrics"]), 2)

    def test_measure_unsupported_metric_is_failure(self):
        result = S.Package(FakeMiddle()).measure(S.MeasureRequest(
            token="t", data=self.DATA,
            metrics=[{"type": "banana", "signal": "vout"}],
        ))
        self.assertFalse(result.ok)
        self.assertIn("unsupported metric", result.error)

    def test_export_validation(self):
        pkg = S.Package(FakeMiddle())
        base = {"token": "t", "output_path": "out.csv", "data": self.DATA}
        bad_format = pkg.export(S.ExportRequest(**base, format="xlsx"))
        self.assertFalse(bad_format.ok)
        self.assertIn("format must be", bad_format.error)
        bad_columns = pkg.export(S.ExportRequest(
            **base, format="csv", columns=[1]))
        self.assertFalse(bad_columns.ok)
        self.assertIn("columns must be", bad_columns.error)
        bad_precision = pkg.export(S.ExportRequest(
            **base, format="csv", precision=0))
        self.assertFalse(bad_precision.ok)
        self.assertIn("precision must be", bad_precision.error)

    def test_export_missing_column_is_reported(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            result = S.Package(FakeMiddle()).export(S.ExportRequest(
                token="t", output_path=str(Path(tmp) / "out.csv"),
                data=self.DATA, format="csv", columns=["nope"],
            ))
        self.assertFalse(result.ok)
        self.assertIn("not present in data", result.error)

    def test_export_csv_and_json_roundtrip(self):
        pkg = S.Package(FakeMiddle())
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            for fmt in ("csv", "json"):
                path = Path(tmp) / f"out.{fmt}"
                result = pkg.export(S.ExportRequest(
                    token="t", output_path=str(path),
                    data=self.DATA, format=fmt,
                ))
                self.assertTrue(result.ok, result.error)
                self.assertEqual(result.value["format"], fmt)
                self.assertTrue(path.is_file() and path.stat().st_size > 0)


if __name__ == "__main__":
    unittest.main()
