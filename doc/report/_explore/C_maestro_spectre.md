# Legacy Maestro/ADE and Standalone Spectre Upper-Layer Inventory

**Scope analysed:** `src_bak/virtuoso_bridge/virtuoso/maestro/`, `src_bak/virtuoso_bridge/spectre/`, the requested legacy tests, the Maestro/Spectre examples, and the named reference documents. This was a read-only exploration; the only file written is this report.

**Classification baseline:** the new upper layer may call only the five middle interfaces:

```python
middle.execute_skill(skill_code, timeout=None, *, token) -> VirtuosoResult
middle.run_command(cmd, timeout=None, *, token, parallel=False) -> CommandResult
middle.upload_file(local_path, remote_path, timeout=None, *, token, recursive=False) -> CommandResult
middle.download_file(remote_path, local_path, timeout=None, *, token, recursive=False) -> CommandResult
middle.run_gui_command(cmd, timeout=None, *, token) -> CommandResult
middle.run_spectre_command(cmd, timeout=None, *, token) -> CommandResult
```

The normative definitions are in `spec/design-concepts/总览/1-四层整体架构与接口.md:178-212`, with role routing in `spec/design-concepts/中层/3-路由设计.md:59-75`. Spectre high-level orchestration is explicitly left to the upper layer in `spec/design-concepts/总览/add-本版范围与明确不支持.md:19`. The new models and protocol are in `src/pyapi/models.py:24-82` and `src/pyapi/models.py:98-128`; the minimal upper-layer examples are `src/pyapi/packages/file_skill_command_file.py:29-74` and `src/pyapi/packages/parallel_probe.py:19-60`.

## 1. Module inventory

Line counts below are physical lines. “Legacy source” means files in the requested scope; test/example files are listed separately to make the evidence trail complete.

### 1.1 Maestro/ADE production modules

| Legacy file | Lines | One-line purpose |
|---|---:|---|
| `src_bak/virtuoso_bridge/virtuoso/maestro/__init__.py` | 129 | Public package facade; re-exports lifecycle, reader, writer, waveform-viewer, and `MaestroOps` entry points. |
| `src_bak/virtuoso_bridge/virtuoso/maestro/lifecycle.py` | 468 | Background/GUI Maestro session lifecycle, focused/ADE window-state probes, lock cleanup, dialog dismissal, and cellview purge. |
| `src_bak/virtuoso_bridge/virtuoso/maestro/ops.py` | 140 | `MaestroOps` facade that binds every client-bound Maestro function to `client.maestro.*`. |
| `src_bak/virtuoso_bridge/virtuoso/maestro/writer.py` | 673 | SKILL wrappers for test/analysis/output/variable/parameter/corner/run-mode/save/export/migration operations; also `run_simulation`, `run_and_wait`, and marker polling. |
| `src_bak/virtuoso_bridge/virtuoso/maestro/waveform_viewer.py` | 228 | Builds and executes SKILL for ViVA/AWV waveform-window open/close, including retained Maestro-session cleanup. |
| `src_bak/virtuoso_bridge/virtuoso/maestro/snapshot_filter.yaml` | 231 | Config/documentation whitelist for `maestro.sdb`, `active.state`, and per-point netlist/PSF artifact selection. |
| `src_bak/virtuoso_bridge/virtuoso/maestro/reader/__init__.py` | 31 | Reader package facade: filters, `snapshot`, `read_results`, and `export_waveform`. |
| `src_bak/virtuoso_bridge/virtuoso/maestro/reader/_parse_sdb.py` | 174 | Pure XML filters for `maestro.sdb`/`active.state` plus YAML keep-list loading and active-test extraction. |
| `src_bak/virtuoso_bridge/virtuoso/maestro/reader/_parse_skill.py` | 17 | Compatibility re-exports of shared SKILL-output tokenizers/parsers. |
| `src_bak/virtuoso_bridge/virtuoso/maestro/reader/_skill.py` | 45 | Low-level SKILL breadcrumb, first-test discovery, and collision-free remote waveform-temp-path helpers. |
| `src_bak/virtuoso_bridge/virtuoso/maestro/reader/bundle.py` | 296 | Brief/full SKILL probe bundles for `snapshot`; derives library path, scratch root, histories, and mtimes. |
| `src_bak/virtuoso_bridge/virtuoso/maestro/reader/runs.py` | 425 | Exports/parses Maestro Detail CSV results and OCEAN waveform text; validates format options. |
| `src_bak/virtuoso_bridge/virtuoso/maestro/reader/session.py` | 175 | Focused-window title/session parsing, history-name extraction, natural sorting, and mtime sorting. |
| `src_bak/virtuoso_bridge/virtuoso/maestro/reader/snapshot.py` | 517 | Aggregates focused-session state and writes the four-track disk snapshot: SKILL text, raw XML, filtered XML, and selected run artifacts. |

### 1.2 Spectre production modules

| Legacy file | Lines | One-line purpose |
|---|---:|---|
| `src_bak/virtuoso_bridge/spectre/__init__.py` | 5 | Public facade exporting `SpectrePool` and `SpectreSimulator` only. |
| `src_bak/virtuoso_bridge/spectre/runner.py` | 1093 | Local/remote Spectre invocation, mode arguments, include staging, result download, parallel pools, license checks, and result assembly. |
| `src_bak/virtuoso_bridge/spectre/parsers.py` | 583 | PSF ASCII parser for single files, directory aggregation, and classic/flat parametric-sweep layouts. |
| `src_bak/virtuoso_bridge/spectre/psf.py` | 83 | Small typed/validating accessors over parsed PSF data: result-file lookup, scalar, vector, frequency. |

### 1.3 Requested legacy tests

| Test file | Lines | What it pins |
|---|---:|---|
| `test_bak/test_maestro_ops.py` | 77 | `client.maestro` facade exposure, exact delegate set, owner forwarding, keyword-only forwarding. |
| `test_bak/test_maestro_read_results.py` | 303 | Detail CSV parsing, single-point CSV shape, download-materialization success contract, empty-result diagnostics, OCEAN format options. |
| `test_bak/test_maestro_snapshot_filter.py` | 11 | `exprOutputs.json` remains in the netlist whitelist. |
| `test_bak/test_maestro_waveform_viewer.py` | 222 | Waveform SKILL content, escaping, fallback, failure cleanup, window/session validation, raw result contract. |
| `test_bak/test_maestro_writer.py` | 174 | Exact SKILL strings, escaping for selected APIs, timeout forwarding, one-budget wait, marker polling budget. |
| `test_bak/test_spectre_parsers.py` | 336 | Delta-compressed PSF, NaN for late signals, complex AC, sweep layouts, STRUCT flattening, fatal/error classification. |
| `test_bak/test_spectre_psf.py` | 101 | Typed scalar/vector/frequency validation and result-path security. |
| `test_bak/test_spectre_runtime_paths.py` | 261 | Local/remote work directories, include staging, csh sourcing, parallel directory isolation, executor lifecycle. |

### 1.4 Scoped examples and real-use assets

| Example file | Lines | Purpose |
|---|---:|---|
| `examples/01_virtuoso/maestro/01_read_focused_maestro.py` | 38 | Snapshot the focused Maestro window into one in-memory dict. |
| `examples/01_virtuoso/maestro/02_snapshot_with_metrics.py` | 58 | Snapshot the focused Maestro window plus disk artifacts. |
| `examples/01_virtuoso/maestro/03_bg_open_read_close_maestro.py` | 99 | Background open, read setup, and deterministic close. |
| `examples/01_virtuoso/maestro/04_gui_open_snapshot_close.py` | 67 | GUI open, snapshot, then save/close lifecycle. |
| `examples/01_virtuoso/maestro/05_gui_session_lifecycle.py` | 277 | Integration matrix for session reuse, reading/editing transitions, unsaved changes, background/zombie cleanup. |
| `examples/01_virtuoso/maestro/06a_rc_create.py` | 128 | End-to-end schematic + Maestro setup creation: test, analysis, outputs, spec, sweep variable. |
| `examples/01_virtuoso/maestro/06b_rc_simulate_and_read.py` | 148 | Background run-and-wait, structured result read, OCEAN waveform export, parsing/measurement. |
| `examples/01_virtuoso/maestro/07_ensure_maestro_view.py` | 99 | Bootstrap a missing `maestro` view with `maeOpenSetup` + `maeSaveSetup`, then open GUI. |
| `examples/01_virtuoso/maestro/08_set_simulator_mode.py` | 190 | Set/read Maestro `uniMode` and `spectreXPreset` via ASI high-performance options. |
| `examples/01_virtuoso/maestro/09_export_sweep_subpoints.py` | 135 | Per-sweep-point OCEAN `openResults`/`selectResult`/`ocnPrint` export and download. |
| `examples/02_spectre/01_inverter_tran.py` | 167 | Remote transient simulation, waveform CSV/plot, timing and summary JSON. |
| `examples/02_spectre/01_veriloga_adc_dac.py` | 257 | Spectre run with Verilog-A include staging and waveform analysis. |
| `examples/02_spectre/02_cap_dc_ac.py` | 149 | DC + AC simulation, complex phasor magnitude, bandwidth calculation, plot. |
| `examples/02_spectre/03_check_license.py` | 90 | Spectre binary/version/`lmstat` license check and JSON report. |
| `examples/02_spectre/04_strongarm_pss_pnoise.py` | 147 | PSS + Pnoise run and downstream waveform/metric extraction. |
| `examples/02_spectre/05_parallel_sweep.py` | 235 | Batch parallel sweep, per-point measurement, summary JSON. |
| `examples/02_spectre/_result_io.py` | 100 | CSV waveform bundle and compact JSON summary/result-count writers. |
| `examples/02_spectre/assets/adc_dac_ideal_4b/analyze_adc_dac_ideal_4b.py` | 156 | External `evas_simulate` ADC/DAC run and `tran.csv` analysis. |
| `examples/02_spectre/assets/adc_dac_ideal_4b/validate_adc_dac_ideal_4b.py` | 263 | Validation of ADC/DAC `tran.csv` semantics and plots. |
| `examples/02_spectre/assets/strongarm_cmp/analyze_strongarm_pss_pnoise.py` | 142 | PSF parsing, crossing/power/noise/FOM measurement logic for PSS/Pnoise results. |

### 1.5 Contract/reference documents used

| Document | Lines | Contract relevance |
|---|---:|---|
| `skills/virtuoso/references/maestro-python-api.md` | 388 | Intended Python API, session mode rules, snapshot/result shapes, writer API. |
| `skills/virtuoso/references/maestro-skill-api.md` | 621 | Maestro SKILL behavior, `mae*`/`asi*`/`axl*` details, blockers, OCEAN, pnoise-jitter limitation. |
| `skills/virtuoso/references/simulation-flow.md` | 172 | Intended GUI simulation flow, title-state parsing, close pitfalls, optimization loop. |
| `skills/spectre/SKILL.md` | 288 | Intended Spectre runner contract, mode semantics, result object, PSF/output pitfalls. |
| `skills/spectre/references/parallel.md` | 97 | Batch/incremental parallel behavior and multi-server profile model. |
| `skills/spectre/references/netlist_syntax.md` | 100 | `.scs` syntax, analyses, save controls, parameterization. |

## 2. Public API surface

This section lists every non-underscore entry point in the scoped production code and the methods exposed through `client.maestro`. “Exact signature” is the source-level call signature; legacy functions take `VirtuosoClient` as the first positional argument, while the facade methods remove that argument and inject the owner.

### 2.1 Result models and package exports

Legacy result model (`src_bak/virtuoso_bridge/models.py:12-95`; same conceptual model is retained in `src/pyapi/models.py:17-95`):

```text
ExecutionStatus: success | failure | partial | error

VirtuosoResult:
  status: ExecutionStatus
  output: str = ""
  errors: list[str] = []
  warnings: list[str] = []
  execution_time: float | None = None
  metadata: dict[str, Any] = {}
  .ok -> bool
  .is_nil -> bool

SimulationResult:
  status: ExecutionStatus
  tool_version: str | None = None
  data: dict[str, Any] = {}
  errors: list[str] = []
  warnings: list[str] = []
  metadata: dict[str, Any] = {}
  .ok -> bool
```

The new protocol additionally defines `CommandResult(returncode, stdout, stderr, kind)` (`src/pyapi/models.py:53-64`) and the five interface methods (`.models.py:98-128`). Legacy `VirtuosoResult` has no `log` field; the new one does (`.models.py:24-37`).

`src_bak/virtuoso_bridge/virtuoso/maestro/__init__.py:3-129` exports:

```text
Lifecycle:
  open_session, close_session, find_open_session, open_gui_session,
  close_gui_session, purge_maestro_cellviews

Reader:
  snapshot, filter_sdb_xml, filter_active_state_xml, read_results, export_waveform

Writer:
  create_test, set_design, set_analysis, add_output, set_spec, set_var, get_var,
  delete_var, get_parameter, set_parameter, set_env_option, set_sim_option,
  set_corner, setup_corner, load_corners, set_current_run_mode,
  set_job_control_mode, set_job_policy, run_simulation, run_and_wait,
  create_netlist_for_corner, export_output_view, write_script,
  migrate_adel_to_maestro, migrate_adexl_to_maestro, save_setup,
  open_maestro_gui_with_history

Waveform/API facade:
  close_waveform_viewer, maestro_close_waveform_viewer_skill,
  maestro_open_waveform_viewer_skill, open_waveform_viewer, MaestroOps
```

`src_bak/virtuoso_bridge/spectre/__init__.py:3-5` exports only `SpectrePool` and `SpectreSimulator`. `spectre_mode_args`, parser functions, and `psf.py` helpers are public-by-name but require importing their submodules.

### 2.2 `MaestroOps` client-bound facade

`src_bak/virtuoso_bridge/virtuoso/maestro/ops.py:80-140` defines `MaestroOps(owner)`. `_client_method` stores the original function in `_DELEGATES` and creates a wrapper that calls it as `_DELEGATES[name](self._owner, *args, **kwargs)` (`ops.py:66-77`). Therefore every method below has the same signature as the module-level function after removing the leading `client` parameter.

| Facade method | Underlying signature; all forwarded exactly | Observable return |
|---|---|---|
| `open_session(lib, cell)` | `open_session(client, lib, cell)` (`lifecycle.py:217`) | session string |
| `close_session(session)` | `close_session(client, session)` (`lifecycle.py:229`) | `None`; raises only for transport/SKILL wrapper errors |
| `find_open_session()` | `find_open_session(client)` (`lifecycle.py:245`) | session string or `None` |
| `open_gui_session(lib, cell, *, timeout=60)` | same (`lifecycle.py:294`) | session string |
| `close_gui_session(session, save=True, *, timeout=60)` | same (`lifecycle.py:360`) | `None` |
| `purge_maestro_cellviews(*, timeout=60)` | alias of `_purge_maestro_cellviews(client, *, timeout=60)` (`lifecycle.py:126`; export at `__init__.py:9,76`) | `None` |
| `snapshot(*, output_root=None, history=None)` | `snapshot(client, ...)` (`snapshot.py:429`) | dict described in §2.6 |
| `read_results(session, lib='', cell='', history='', *, include_raw=False)` | `runs.py:37` | dict described in §2.6 or `{}` on recoverable failure |
| `export_waveform(session, expression, local_path, *, analysis='ac', history='', precision=None, width=None, number_notation=None)` | `runs.py:328` | local path string |
| `open_waveform_viewer(lib, cell, history, *, signals, view='maestro', application='Assembler', test=None, result='tran', results_dir=None, timeout=60)` | `waveform_viewer.py:184` | raw `VirtuosoResult` |
| `close_waveform_viewer(*, window=None, session=None, timeout=30)` | `waveform_viewer.py:219` | raw `VirtuosoResult` |
| `create_test(test, *, lib, cell, view='schematic', simulator='spectre', session='')` | `writer.py:32` | raw SKILL output string |
| `set_design(test, *, lib, cell, view='schematic', session='')` | `writer.py:42` | raw SKILL output string |
| `set_analysis(test, analysis, *, enable=True, options='', session='')` | `writer.py:55` | raw SKILL output string |
| `add_output(name, test, *, output_type='', signal_name='', expr='', session='')` | `writer.py:72` | raw SKILL output string |
| `set_spec(name, test, *, lt='', gt='', session='')` | `writer.py:91` | raw SKILL output string |
| `set_var(name, value, *, type_name='', type_value='', session='')` | `writer.py:108` | raw SKILL output string |
| `get_var(name, *, session='')` | `writer.py:133` | raw SKILL output string |
| `delete_var(name, *, test='', session='')` | `writer.py:139` | raw SKILL output string |
| `get_parameter(name, *, type_name='', type_value='', session='')` | `writer.py:163` | raw SKILL output string |
| `set_parameter(name, value, *, type_name='', type_value='', session='')` | `writer.py:177` | raw SKILL output string |
| `set_env_option(test, options, *, session='')` | `writer.py:200` | raw SKILL output string |
| `set_sim_option(test, options, *, session='')` | `writer.py:212` | raw SKILL output string |
| `set_corner(name, *, disable_tests='', session='')` | `writer.py:228` | raw SKILL output string |
| `setup_corner(name, *, model_file='', model_section='', variables=None, session='')` | `writer.py:239` | corner name string |
| `load_corners(filepath, *, sections='corners', operation='overwrite')` | `writer.py:293` | raw SKILL output string |
| `set_current_run_mode(run_mode, *, session='')` | `writer.py:306` | raw SKILL output string |
| `set_job_control_mode(mode, *, session='')` | `writer.py:317` | raw SKILL output string |
| `set_job_policy(policy, *, test_name='', job_type='', session='')` | `writer.py:324` | raw SKILL output string |
| `run_simulation(*, session='', callback='', timeout=None)` | `writer.py:338` | history-name string (normally quoted) |
| `run_and_wait(*, session='', timeout=600)` | `writer.py:491` | `(history, status)` tuple |
| `create_netlist_for_corner(test, corner, output_dir, *, session='')` | `writer.py:582` | raw SKILL output string |
| `export_output_view(filepath, *, view='Detail')` | `writer.py:594` | raw SKILL output string |
| `write_script(filepath)` | `writer.py:601` | raw SKILL output string |
| `migrate_adel_to_maestro(lib, cell, state)` | `writer.py:610` | raw SKILL output string |
| `migrate_adexl_to_maestro(lib, cell, view='adexl', *, maestro_view='maestro')` | `writer.py:617` | raw SKILL output string |
| `save_setup(lib, cell, *, session='')` | `writer.py:630` | raw SKILL output string |
| `open_maestro_gui_with_history(lib, cell, *, history='')` | `writer.py:642` | history-name string |

The writer’s common `_q` helper executes SKILL and raises `RuntimeError("SKILL error: ...")` if `VirtuosoResult.errors` is non-empty; otherwise it returns `r.output or ""` (`writer.py:20-25`). This exception behavior is a direct legacy contract that the new upper layer must translate into a structured business result.

### 2.3 Maestro lifecycle API

| Entry point | Exact signature | Observed contract / return shape |
|---|---|---|
| `open_session` | `(client, lib: str, cell: str) -> str` (`lifecycle.py:217`) | Calls `maeOpenSetup(lib, cell, "maestro")`, strips quotes, raises if result is empty/nil/t. |
| `close_session` | `(client, session: str) -> None` (`lifecycle.py:229`) | Calls `maeCloseSession(?session ..., ?forceClose t)` inside `progn`. |
| `find_open_session` | `(client) -> str | None` (`lifecycle.py:245`) | Iterates `maeGetSessions()` and returns first session whose `maeGetSetup` is non-nil. Empty/fresh views are intentionally invisible. |
| `open_gui_session` | `(client, lib: str, cell: str, *, timeout: int = 60) -> str` (`lifecycle.py:294`) | Closes background sessions, closes/reuses GUI windows, calls `deOpenCellView(lib,cell,"maestro","maestro",nil,"a")`, returns matching session. |
| `close_gui_session` | `(client, session: str, save: bool = True, *, timeout: int = 60) -> None` (`lifecycle.py:360`) | Saves/promotes when requested, closes by window number, purges Maestro cellviews. |
| `purge_maestro_cellviews` | public alias of `_purge_maestro_cellviews(client, *, timeout=60) -> None` (`lifecycle.py:126`; `__init__.py:9`) | Executes `dbPurge(cv)` for open cellviews whose `viewName == "maestro"`. |

Private but behaviorally important helpers are `_get_session_windows` (`lifecycle.py:144-186`), `_close_background_sessions` (`lifecycle.py:189-210`), `_find_session_for_cell` (`lifecycle.py:273-287`), `_close_gui_window` (`lifecycle.py:426-468`), and the X11 senders (`lifecycle.py:24-119`).

### 2.4 Maestro reader and snapshot API

| Entry point | Exact signature | Return shape / behavior |
|---|---|---|
| `filter_sdb_xml` | `(xml_text: str) -> str` (`_parse_sdb.py:68`) | Rebuilds `<setupdb>` with only direct `<active>` children named by YAML `maestro_sdb.active_keep`; returns `""` on XML parse error. |
| `filter_active_state_xml` | `(xml_text: str, *, valid_test_names: set[str] | None = None) -> str` (`_parse_sdb.py:131`) | Rebuilds `<statedb>` with retained `<Test>` blocks and retained `<component Name=...>` children; optionally removes test tombstones; returns `""` on parse error. |
| `brief_bundle` | `(client, *, sess: str, lib: str, cell: str, view: str) -> dict` (`bundle.py:59`) | `{"raw_sections": [(label, raw_text), ...]}`; one SKILL round-trip, four probes. |
| `full_bundle` | `(client, *, sess: str, lib: str, cell: str, view: str) -> dict` (`bundle.py:143`) | `{"raw_sections": ..., "test": str, "current_history": str, "hist_files": list[str], "hist_files_mtime": list[tuple[str,int]], "lib_path": str, "scratch_root": str}`; two SKILL calls plus shell mtime scans. |
| `natural_sort_histories` | `(hist_files: list[str]) -> list[str]` (`session.py:131`) | Extracts `.rdb`-anchored and `Interactive.N`/`MonteCarlo.N` history names, natural-sorts them. |
| `sort_histories_by_mtime` | `(hist_files_mtime: list[tuple[str, int]]) -> list[str]` (`session.py:154`) | Buckets companion files by history and sorts newest mtime first. |
| `format_skill_sections` | `(sections: list[tuple[str, str]]) -> str` (`snapshot.py:83`) | Returns `""` for empty input; otherwise `"[label] raw\n\n..."` plus trailing newline. |
| `snapshot` | `(client, *, output_root: str | None = None, history: str | None = None) -> dict` (`snapshot.py:429`) | Brief mode returns metadata + raw SKILL sections. Disk mode adds `output_dir` and `latest_history`. |
| `read_results` | `(client, session: str, lib: str = '', cell: str = '', history: str = '', *, include_raw: bool = False) -> dict` (`runs.py:37`) | Structured dict described below; `{}` for missing lib/cell/test/history or download failure. |
| `export_waveform` | `(client, session: str, expression: str, local_path: str, *, analysis: str = 'ac', history: str = '', precision: int | None = None, width: int | None = None, number_notation: str | None = None) -> str` (`runs.py:328`) | Returns `local_path`; validates precision 1..16, width >=4, notation in `{suffix, engineering, scientific, none}`. |

`read_results` return shape:

```text
{
  "history": str,
  "tests": [str, ...],
  "points": [
    {
      "point": int,
      "parameters": {str: str, ...},
      "outputs": {
        output_name: {
          "value": str,
          "spec": str,
          "weight": str,
          "pass_fail": str
        }
      }
    }
  ],
  "outputs": [                      # backward-compatible flat projection
    {"point": int, "name": str, "value": str, "spec_status": str}
  ],
  "overall_spec": str | None,
  "overall_yield": str | None,
  # "raw_csv": str                 # only when include_raw=True
}
```

`snapshot` return shape (brief mode; `output_root=None`):

```text
{
  "session": str,
  "app": "assembler" | "explorer" | None,
  "lib": str,
  "cell": str,
  "view": str,
  "mode": "Editing" | "Reading" | "",
  "unsaved": bool,
  "raw_sections": [(skill_label: str, raw_skill_output: str), ...]
}
```

With `output_root`, the dict additionally contains `"output_dir"` and `"latest_history"` (`snapshot.py:483-515`). The on-disk directory contains `maestro.sdb`, `state_from_sdb.xml`, `active.state`, `state_from_active_state.xml`, `state_from_skill.txt`, and `<history>/` artifacts (`snapshot.py:405-422`; `skills/virtuoso/references/maestro-python-api.md:94-116`).

### 2.5 Maestro waveform-viewer API

| Entry point | Exact signature | Return shape |
|---|---|---|
| `maestro_open_waveform_viewer_skill` | `(lib: str, cell: str, history: str, *, signals: list[str] | tuple[str, ...], view: str = 'maestro', application: str = 'Assembler', test: str | None = None, result: str = 'tran', results_dir: str | Path | None = None) -> str` (`waveform_viewer.py:35`) | SKILL source string |
| `maestro_close_waveform_viewer_skill` | `(*, window: int | str | None = None, session: str | None = None) -> str` (`waveform_viewer.py:146`) | SKILL source string |
| `open_waveform_viewer` | `(client: Any, lib: str, cell: str, history: str, *, signals: list[str] | tuple[str, ...], view: str = 'maestro', application: str = 'Assembler', test: str | None = None, result: str = 'tran', results_dir: str | Path | None = None, timeout: int = 60) -> Any` (`waveform_viewer.py:184`) | Raw `VirtuosoResult` |
| `close_waveform_viewer` | `(client: Any, *, window: int | str | None = None, session: str | None = None, timeout: int = 30) -> Any` (`waveform_viewer.py:219`) | Raw `VirtuosoResult` |

Open SKILL returns a list shaped `("opened" lib cell view history retained_session window_id)`; close SKILL returns `("closed" session window_id)`. The open path checks callability of `maeOpenSetup`, `maeOpenResults`, `maeGetResultTests`, `maeGetOutputValue`, `openResults`, `awvCreatePlotWindow`, `awvPlotWaveform`, `v`, `hiCloseWindow`, and `maeCloseSession` (`waveform_viewer.py:112-142`). On failure it attempts `hiCloseWindow` and `maeCloseSession` cleanup (`waveform_viewer.py:138-142`).

### 2.6 Spectre runner API

| Entry point | Exact signature | Return/observable shape |
|---|---|---|
| `spectre_mode_args` | `(mode: str) -> list[str]` (`runner.py:83`) | Lowercases/trims mode; raises `ValueError` for unknown mode; returns one of the tables below. |
| `SpectrePool` | `(simulator: SpectreSimulator, max_workers: int = 4)` (`runner.py:523`) | Context manager; holds a `ThreadPoolExecutor`. |
| `SpectrePool.max_workers` | property `-> int` (`runner.py:533`) | configured worker count |
| `SpectrePool.submit` | `(netlist: Path, params: dict | None = None) -> Future[SimulationResult]` (`runner.py:538`) | immediate future; rejects after shutdown |
| `SpectrePool.wait_all` | `(futures: list[Future[SimulationResult]]) -> list[SimulationResult]` (`runner.py:555`) | submission-order results |
| `SpectrePool.shutdown` | `(wait: bool = True, *, cancel_futures: bool = False) -> None` (`runner.py:562`) | idempotent close |
| `SpectreSimulator` | `(spectre_cmd='spectre', spectre_args=None, timeout=600, work_dir=None, output_format='psfascii', remote_host=None, remote_user=None, remote_work_dir=None, jump_host=None, jump_user=None, ssh_key_path=None, ssh_config_path=None, keep_remote_files=False, remote=False, ssh_runner=None, profile=None)` (`runner.py:586-604`) | simulator instance |
| `SpectreSimulator.from_env` | `(cls, spectre_cmd='spectre', spectre_args=None, timeout=600, work_dir=None, output_format='psfascii', keep_remote_files=False, ssh_runner=None, profile=None) -> SpectreSimulator` (`runner.py:659`) | selects local if resolved Spectre host is localhost; otherwise constructs remote simulator |
| `SpectreSimulator.local` | `(cls, spectre_cmd='spectre', spectre_args=None, timeout=600, work_dir=None, output_format='psfascii') -> SpectreSimulator` (`runner.py:719`) | local simulator |
| `run_simulation` | `(self, netlist: Path, params: dict | None = None) -> SimulationResult` (`runner.py:738`) | one simulation |
| `parallel_pool` | `(self, max_workers: int = 4) -> SpectrePool` (`runner.py:771`) | explicit pool |
| `set_max_workers` | `(self, n: int) -> None` (`runner.py:787`) | deprecated compatibility API |
| `submit` | `(self, netlist: Path, params: dict | None = None) -> Future[SimulationResult]` (`runner.py:808`) | deprecated compatibility API |
| `shutdown` | `(self) -> None` (`runner.py:826`) | releases compatibility pool |
| `run_parallel` | `(self, tasks: list[tuple[Path, dict]], max_workers: int = 4) -> list[SimulationResult]` (`runner.py:833`) | batch results, submission order |
| `wait_all` | static `(futures: list[Future[SimulationResult]]) -> list[SimulationResult]` (`runner.py:855`) | catches future exceptions into `SimulationResult(status=ERROR)` |
| `check_license` | `(self) -> dict[str, Any]` (`runner.py:873`) | local: `{ok, spectre_path, version, licenses, error?}`; remote additionally `{raw_output, stderr}` |

Mode argument table (`runner.py:46-55`; validated by `spectre_mode_args`):

| Mode | Arguments |
|---|---|
| `spectre` | `[]` |
| `aps` | `["+aps"]` |
| `x` | `["+x"]` |
| `cx` | `["+preset=cx", "+mt"]` |
| `ax` | `["+preset=ax", "+mt"]` |
| `mx` | `["+preset=mx", "+mt"]` |
| `lx` | `["+preset=lx", "+mt"]` |
| `vx` | `["+preset=vx", "+mt"]` |

`run_simulation` accepts a `params` dict with at least these legacy conventions:

```text
{
  "include_files": [Path | str, ...],  # staged next to the netlist
  "spectre_args": [str, ...],          # appended to simulator-level args
}
```

`_build_spectre_argv` adds `-64` unless `-64`/`-32` is present, `+lqtimeout 900` unless supplied, `-maxw 5`, `-maxn 5`, `+escchars`, optional `-format`, optional `-raw`, mode args, `+logstatus`, and optional `+log` (`runner.py:91-125`). This is an implementation detail that the new upper layer must reconstruct explicitly or treat as legacy output-only behavior.

### 2.7 Spectre PSF parser and helper API

| Entry point | Exact signature | Return shape / behavior |
|---|---|---|
| `parse_spectre_psf_ascii` | `(psf_path: Path) -> SimulationResult` (`parsers.py:18`) | `data` is the parsed dict; `metadata["psf_header"]` is optional; missing/empty/parse failure maps to ERROR/FAILURE. |
| `parse_psf_ascii_directory` | `(output_dir: Path) -> dict[str, Any]` (`parsers.py:70`) | Merged flat data from one transient/DC/AC result plus all `*.info` files. |
| `parse_sweep_psf_directory` | `(output_dir: Path) -> dict[int, dict[str, Any]]` (`parsers.py:200`) | 1-based point index → parsed signal dict; `{}` if no sweep layout recognized. |
| `read_psf_ascii` | `(path: Path) -> dict[str, Any]` (`psf.py:14`) | Returns `result.data` or raises `ValueError` with parser errors. |
| `result_file` | `(raw_psf: Path, filename: str) -> Path` (`psf.py:23`) | Requires exactly one relative, non-escaping, non-symlink-escaping match below `raw_psf`; otherwise raises. |
| `scalar` | `(data: Mapping[str, Any], raw_key: str) -> float` (`psf.py:45`) | Requires exact real finite scalar; rejects bool/complex/list/string/non-finite. |
| `vector` | `(data: Mapping[str, Any], raw_key: str) -> list[complex]` (`psf.py:60`) | Requires non-empty finite numeric vector; converts to complex list. |
| `frequency_hz` | `(data: Mapping[str, Any], raw_key: str = 'freq') -> list[float]` (`psf.py:75`) | Requires real, strictly increasing frequency vector. |

`parse_psf_ascii_directory` prefixes merged keys by analysis: transient keys stay unprefixed, DC keys become `dc_<key>`, AC keys become `ac_<key>`, and each `*.info` file contributes `<stem>_<key>` (`parsers.py:70-197`). `parse_sweep_psf_directory` instead returns point-indexed dicts and is wired into `result.metadata["sweep_points"]` by the runner (`runner.py:450-466`).

### 2.8 Internal-but-observed result assembly contract

Although `_build_simulation_result` is private (`runner.py:383`), its output is the public `SimulationResult` consumed by every example, so its shape is part of the observable contract:

- `status`: `SUCCESS` when return code and error classification are clean; `PARTIAL` when a failure exists but some output files exist; `FAILURE` when no output files exist (`runner.py:434-448`).
- `data`: for single-point PSF ASCII, merged `parse_psf_ascii_directory` output; otherwise `{}` unless the parser finds files (`runner.py:450-454`).
- `errors`: classified read-in, license, convergence, file-not-found, crash, or raw error lines (`runner.py:394-418`).
- `warnings`: lines containing `warning` but not `0 warnings` (`runner.py:420-425`).
- `metadata`: `returncode`, `output_dir`, `output_files`, optional `sweep_points`, and caller-supplied remote timing/command metadata (`runner.py:456-468`).
- `tool_version` is not populated by the legacy builder.

## 3. Capability decomposition

The tables below are the business capabilities that a new upper-layer package must re-develop. “Business input” and “business output” are the API-level concepts; SKILL text, shell commands, and file paths are implementation steps, not upper-layer caller concepts.

### 3.1 Maestro capabilities

| Capability | Business inputs | Business outputs | Sub-steps observed in legacy code | Required middle interfaces |
|---|---|---|---|---|
| M1. Background session open/close | library, cell | session id; clean close | `maeOpenSetup(lib, cell, "maestro")`; strip/validate session; later `maeCloseSession(?forceClose t)` | `execute_skill` |
| M2. GUI session open/reuse/close | library, cell; `save`; per-call timeout | editable GUI session id; saved/discarded state | probe windows/sessions; close background sessions; reuse editable target; close reading/other windows; `deOpenCellView(..., "a")`; find session by title; save/promote if needed; `hiCloseWindow`; purge cellviews | `execute_skill`; for X11 dialog dismissal, `run_gui_command` |
| M3. Ensure a Maestro view exists | library, cell | on-disk `maestro` view | `maeOpenSetup`; `maeSaveSetup`; close background session | `execute_skill` |
| M4. Read focused Maestro state | current GUI focus; optional history | session metadata and raw SKILL sections | one focused-window probe (`hiGetCurrentWindow`, `davSession`, window names, sessions); brief probes for readPath/setup/enabled analyses/per-analysis settings | `execute_skill` |
| M5. Full snapshot / inventory | output root; optional history | timestamped snapshot directory plus metadata | full bundle probes; download `maestro.sdb` and `active.state`; filter XML; write raw SKILL sections; find newest history by mtime/current/natural sort; `find|tar` per-point artifacts; download and extract | `execute_skill`, `download_file`, `run_command`; possibly `run_gui_command` for focus |
| M6. Configure tests, analyses, outputs, specs | test/analysis/output names and SKILL option lists | raw acknowledgement output | `maeCreateTest`, `maeSetDesign`, `maeSetAnalysis`, `maeAddOutput`, `maeSetSpec` | `execute_skill` |
| M7. Configure variables and parameters | names, values, optional type scope (`test`, `corner`) | raw acknowledgement output | `maeSetVar`, `maeGetVar`, `maeDeleteVar`/`axlRemoveElement`, `maeGetParameter`, `maeSetParameter` | `execute_skill` |
| M8. Configure environment/simulation options | test, SKILL alist options | raw acknowledgement output | `maeSetEnvOption`, `maeSetSimOption` | `execute_skill` |
| M9. Corner setup and load | corner name, model file/section, variable map, CSV path | corner name or acknowledgement | `maeSetCorner`; per-variable `maeSetVar`; `axlGetMainSetupDB`/`axlGetCorner`/`axlPutModel`/`axlSetModelFile`/`axlSetModelSection`; `maeLoadCorners` | `execute_skill`; `upload_file` if a local CSV must be staged |
| M10. Run-mode/job control | run mode, job mode/policy | acknowledgement | `maeSetCurrentRunMode`, `maeSetJobControlMode`, `maeSetJobPolicy` | `execute_skill` |
| M11. Start simulation asynchronously | session, optional callback, accept timeout | history name | build `maeRunSimulation` with optional escaped session/callback; return raw output | `execute_skill` |
| M12. Run and wait | session, end-to-end timeout | `(history, status)` | define callback writing marker; start with callback; diagnose nil; optionally dismiss modal and retry once; poll marker via local FS or shell `cat`; clean marker; raise timeout | `execute_skill`, `run_command` (or token-appropriate file polling); `run_gui_command` for dialog/X11 recovery |
| M13. Export netlist/setup/results | test/corner/output dir; file paths | files on the relevant role | `maeCreateNetlistForCorner`, `maeExportOutputView`, `maeWriteScript` | `execute_skill`; `download_file` where caller needs local bytes |
| M14. Read all result points and specs | session, lib/cell, optional history | structured points/outputs/spec status/yield | find latest history; `maeExportOutputView` to remote CSV; download; parse CSV; query overall spec/yield | `execute_skill`, `download_file` |
| M15. Export one OCEAN waveform | session, expression, local path, analysis/history/format | local text waveform | find history; `maeOpenResults`; resolve results dir; validate history; `openResults`; `selectResults`; `ocnPrint`; download; delete remote temp | `execute_skill`, `download_file` |
| M16. Open/close interactive waveform viewer | lib/cell/history/signals/test/result/raw results dir | raw SKILL result containing session/window handles; close acknowledgement | build validated SKILL; open setup/results; create AWV window; plot waveforms; retain session; close window/session deterministically | `execute_skill`; focus/dismiss may require `run_gui_command` |
| M17. Set Maestro simulator mode | session, test, mode | applied `(uniMode, spectreXPreset)` | `maeGetTestSession`; `asiSetHighPerformanceOptionVal`; save setup; read back and verify | `execute_skill` (example-level operation; not exported by legacy package) |
| M18. Export sweep subpoints | result root, signals, point count, analysis, remote temp, local output | one text waveform per point/signal | make remote temp dir; for each point call `openResults`, `selectResult`, `ocnPrint`; download each file | `execute_skill`, `run_command` or file APIs for temp dir, `download_file` |

Important business-level caveats:

- `open_gui_session` considers a fresh/empty Maestro view valid, whereas `find_open_session` does not. A new API must expose this distinction rather than silently using one helper for both (`lifecycle.py:245-270`, `lifecycle.py:346-357`).
- `close_gui_session` has non-trivial state transitions: save dirty Editing sessions, promote dirty Reading sessions when no edit conflict, discard when another editor exists, and handle save dialogs with an X11 Alt+N thread (`lifecycle.py:360-468`).
- `read_results` uses Cadence’s Detail CSV as the source of truth; it deliberately does not trust `maeExportOutputView`’s return value and uses the existence of the remote file as the success signal (`runs.py:132-162`).

### 3.2 Spectre capabilities

| Capability | Business inputs | Business outputs | Sub-steps observed in legacy code | Required middle interfaces |
|---|---|---|---|---|
| S1. Build an invocation | mode, spectre command, per-run args, netlist, output format | argv/command line | `spectre_mode_args`; resolve `spectre_cmd` into binary + prefix; inject `-64`, log/raw/format options, queue/warning/notice options | upper-layer pure Python; final execution through `run_spectre_command` |
| S2. Stage a netlist and includes | netlist, Verilog-A/model include files | remote/local run directory containing inputs | local: copy includes into work dir; remote: upload netlist and existing includes into UUID run dir | `upload_file`; for local/remote file staging in the new architecture, upload to the command/file roles |
| S3. Run one Spectre simulation | netlist, params, mode/args, timeout, output format | `SimulationResult` | local subprocess or remote task; set cwd, source cshrc if configured; capture stdout/stderr and return code; locate `.raw`/`.psf`; download remote raw/aux files | `run_spectre_command`; `download_file` for raw results |
| S4. Parallel fixed batch | list of `(netlist, params)`, max workers | ordered list of `SimulationResult` | scoped `ThreadPoolExecutor`; one pool per call; unique local/remote run directory per task; wait in submission order; convert task exception to error result | upper-layer scheduling plus `run_spectre_command` / file interfaces; middle channel budget is per token |
| S5. Incremental pool | max workers; submissions over time | futures and ordered results | `SpectrePool` owns a `ThreadPoolExecutor`; reject submissions after shutdown; context manager waits/closes | same as S4; no persistent shell may be assumed |
| S6. License check | configured Spectre binary/profile | dict with path/version/licenses | local `shutil.which` + `spectre -V` + `lmstat -a`; remote command sources cshrc as needed, runs `spectre -V`, `lmstat -a`, parses `SPECTRE_PATH=` and `Users of` lines | `run_spectre_command` or `run_command` depending on role |
| S7. Parse one PSF ASCII file | file path | `SimulationResult` with flat signal dict and PSF header metadata | read text; parse HEADER/TYPE/SWEEP/TRACE/VALUE/END; parse swept or non-swept data | pure Python upper-layer parser; `download_file` first if remote |
| S8. Aggregate a result directory | output directory | flat merged signal dict | resolve scan root; choose canonical transient/DC/AC candidates; parse `*.info` files; prefix keys by analysis/stem | pure Python; `download_file` for remote directories |
| S9. Parse parametric sweep output | output directory | `{point_index: {signal: values}}` | recognize `<sweep>/<N>/...` and flat `sw*-NNN_*` layouts; one-based indexing | pure Python; `download_file` recursively |
| S10. Typed result access | parsed dict, raw key | finite scalar/vector/frequency | validate key/type/finiteness/monotonicity; reject escaping result-file patterns and symlink escapes | pure Python |
| S11. Result IO | parsed data/result, target path | CSV waveform bundle and JSON summary | rectangular CSV writer; compact summary with status/signals/lengths/errors/warnings/metadata; timing/count printers | pure Python, local filesystem only |
| S12. Measurement/derived metrics | waveform arrays | delay, bandwidth, quantization, power, noise, FOM, pass/fail | examples implement interpolation, magnitude/dB, searchsorted-like logic, trapezoid integration, crossings, code reconstruction | pure Python/numpy; consume data returned by S3/S7/S8 |
| S13. Netlist parameterization | base `.scs`, parameter value | per-point `.scs` file | `str.replace` / regex substitution; preserve expressions; regenerate each netlist (CLI `-param` is documented as broken) | pure Python then `upload_file` + `run_spectre_command` |
| S14. External EVAS ADC/DAC flow | `.scs`, output dir | `tran.csv` and plots | call `evas.netlist.runner.evas_simulate`; parse CSV with numpy | not compatible with current five-interface baseline; would need an explicit business adapter or be out of scope |

Capability-to-middle summary:

| Legacy capability | Middle interface(s) | Why |
|---|---|---|
| Maestro session/config/run/result SKILL | `execute_skill` | All Maestro `mae*`, `asi*`, OCEAN, and window queries are SKILL evaluations. |
| Maestro marker polling, metadata `find`, temp cleanup | `run_command` | Legacy uses `cat`, `find`, `rm`, `mkdir`, `tar`, or shell command strings. |
| Maestro XML/result/waveform transfer | `download_file`, `upload_file` | Raw `.sdb`, `active.state`, Detail CSV, OCEAN text, or local CSV corners must cross the role boundary. |
| GUI dialog/window/X11 operations | `run_gui_command` | New role explicitly covers one-shot X11/window/CIW-related commands; it must not become a persistent GUI session. |
| Spectre binary invocation | `run_spectre_command` | Spec reserves this role for one-shot `spectre`/license/environment commands. |
| Standalone parsing and analysis | none | PSF/CSV/JSON parsing is pure Python and does not need a middle call. |

## 4. Data formats and parsers

### 4.1 Maestro `maestro.sdb` XML

**Origin:** Cadence Maestro setup database on the GUI/file role, normally `<lib_path>/<cell>/<view>/<view>.sdb` (`snapshot.py:67-75`). It is XML whose top level is `<setupdb>` and whose children include `<active>` plus many historical snapshots.

**How legacy code obtains it:** `snapshot(output_root=...)` uses `full_bundle` to get the library read path, then `client.download_file` downloads `<lib_path>/<cell>/<view>/<view>.sdb` to the snapshot directory (`bundle.py:191-212`, `snapshot.py:60-80`).

**How it is parsed:** Legacy deliberately does not build a Python object model. `filter_sdb_xml` parses with `xml.etree.ElementTree`, creates a new `<setupdb>`, and copies only direct `<active>` children whose tag is in the YAML `maestro_sdb.active_keep` list (`_parse_sdb.py:68-106`). It returns `""` on `ET.ParseError` or an unreadable config.

**Default keep list:** `currentmode`, `jobcontrolmode`, `corners`, `tests`, `vars`, `parameters`, `specs`, `parametersets`, `overwritehistoryname` (`snapshot_filter.yaml:26-37`; hard fallback `_parse_sdb.py:55-58`). History snapshots and GUI preferences are dropped by design.

**What a new upper package must replicate:** download the raw XML through the file interface, persist it if required, expose the filtered high-signal XML and/or structured projection, and preserve the distinction between current setup and historical snapshots. The YAML whitelist should be a packaged asset or explicit upper-layer configuration; do not hard-code a one-off parse.

### 4.2 Maestro `active.state` XML

**Origin:** Per-test Maestro state on disk, sibling to `maestro.sdb` (`snapshot.py:76-80`). It contains `<statedb>` and multiple `<Test Name="...">` blocks.

**How legacy code obtains it:** `client.download_file` of `<lib_path>/<cell>/<view>/active.state` (`snapshot.py:76-80`).

**How it is parsed:** `filter_active_state_xml` copies only components named in `active_state.components_keep`. If `valid_test_names` is supplied, it drops `<Test>` blocks that no longer appear in the sibling `maestro.sdb` active tests, eliminating Cadence tombstones (`_parse_sdb.py:109-174`). Default component keep list: `adeInfo`, `analyses`, `variables`, `rfstim`, `turboOptions`, `mdlOptions`, `mtsSetup`, `graphicalStimuli` (`snapshot_filter.yaml:64-82`; fallback `_parse_sdb.py:59-65`). The comments document omitted components such as `outputs`, `environmentOptions`, `modelSetup`, `simulatorOptions`, `convergence`, `cosimOptions`, `emirOptions`, and `fault*`.

**What a new upper package must replicate:** the raw copy and filtered view, the tombstone-removal behavior, and at minimum the high-signal fields that are not reliably available from `maeGetAnalysis`, especially PSS/pnoise options, RF stimulus, `turboOptions`, MDL/MTS/graphical stimuli, and pnoise jitter-event data.

### 4.3 `snapshot_filter.yaml` whitelist/filter mechanism

The YAML is both configuration and documentation. It has exactly three top-level sections: `maestro_sdb`, `active_state`, and `per_point` (`snapshot_filter.yaml:26,64,143`).

| Section | Keys | Consumer | Effect |
|---|---|---|---|
| `maestro_sdb.active_keep` | `currentmode`, `jobcontrolmode`, `corners`, `tests`, `vars`, `parameters`, `specs`, `parametersets`, `overwritehistoryname` | `filter_sdb_xml` | Keeps only those direct children of `<active>`; history and GUI state are dropped. |
| `active_state.components_keep` | `adeInfo`, `analyses`, `variables`, `rfstim`, `turboOptions`, `mdlOptions`, `mtsSetup`, `graphicalStimuli` | `filter_active_state_xml` | Keeps only those `<component>` children under each live `<Test>`. |
| `per_point.netlist` | `netlist`, `input.scs`, `qpInformation.ils`, `exprOutputs.json`, `paramInfo.ils` | `snapshot._per_point_list` | Server-side `find -name` clause and local `fnmatch` patterns for per-point input artifacts. |
| `per_point.psf` | `spectre.out`, `logFile`, `dcOp.dc`, `dcOpInfo.info`, `variables_file`, `*.ac`, `*.dc`, `*.tran`, `*.noise`, `*.pss`, `*.pnoise`, `*.pac`, `*.pxf`, `*.stb`, `*.xf`, `*.sens` | `snapshot._per_point_list` | Per-point result/log selection; `*.raw` is explicitly excluded because it is large/binary. |

The file is loaded through `lru_cache(maxsize=4)` at `_parse_sdb.py:26-39`, with hard-coded fallback keep sets if YAML is missing/unreadable. `_per_point_list` falls back to `_DEFAULT_NETLIST_FILES` and `_DEFAULT_PSF_FILES` (`snapshot.py:148-171`). The remote snapshot builds `find` clauses from those lists and pipes matched files into `tar`; the local branch mirrors the same patterns with `fnmatch.fnmatchcase` (`snapshot.py:213-260`, `snapshot.py:326-402`). Editing the YAML changes what the snapshot pulls without code changes (`snapshot_filter.yaml:12-13`).

The no-raw policy is explicit: `*.raw` is marked `[NEVER]` and explained as MB-scale binary PSF, with the comment to use `reader.runs.read_results` for waveform data (`snapshot_filter.yaml:224-231`). A new implementation must preserve or deliberately replace this output-size policy.

### 4.4 Raw SKILL text/alist output

**Origin:** Maestro `mae*`, `asi*`, OCEAN, and window APIs return SKILL atoms or parenthesized alists as text (`execute_skill().output`).

**How collected:** `brief_bundle` and `full_bundle` issue one SKILL `list(...)` call whose outputs are split into labeled raw sections; `_fetch_window_state` splits focused-window/SKILL data (`bundle.py:73-98,163-189`; `session.py:76-112`). Legacy does not generally convert alists to Python dicts; `state_from_skill.txt` stores `[label] raw_output` pairs (`snapshot.py:83-102`).

**Parser:** `_parse_skill.py` re-exports `_tokenize_top_level`, `_scan_top_groups`, `_parse_sexpr`, and `_parse_skill_str_list` from `virtuoso_bridge.virtuoso.skill_output` (`_parse_skill.py:3-17`; shared implementation `src_bak/virtuoso_bridge/virtuoso/skill_output.py:6-95`). The tokenizer is quote/paren aware; `parse_skill_str_list` recursively extracts strings.

**What a new upper package must replicate:** quote-aware splitting, nil/t handling, string unescaping, and robust truncation behavior if it wants to parse SKILL returns. If it follows the legacy “raw text is canonical” stance, it must preserve raw text and label-to-expression mapping instead.

### 4.5 Maestro Detail CSV (`maeExportOutputView ?view "Detail"`)

**Origin:** Cadence result export selected by `read_results`, written to a remote temp path and downloaded (`runs.py:132-152`). The export call is:

```text
maeExportOutputView(
  ?session ...
  ?testName ...
  ?historyName ...
  ?view "Detail"
  ?fileName "/tmp/vb_results_<uuid>.csv"
)
```

**Parser:** `_parse_detail_csv` recognizes a multi-point CSV whose rows are `Point,Test,Output,Nominal,Spec,Weight,Pass/Fail`, and a single-point variant whose header omits `Point` (`runs.py:213-314`). `Parameters: K=V, ...` starts a new point; output rows create `value/spec/weight/pass_fail`; the parser also emits a flattened compatibility list.

**Fetch/success contract:** `maeExportOutputView` may return `t`, `nil`, or the filename; the code treats download-file existence as the arbiter (`runs.py:133-162`; regression at `test_bak/test_maestro_read_results.py:134-162`).

**What a new upper package must replicate:** the two CSV variants, parameter grouping, quoted-comma handling via `csv`, per-point output map, `tests`, overall spec/yield, and optional raw CSV retention. It should not use the SKILL return string as the sole success signal unless the new middle contract provides a stronger file/materialization guarantee.

### 4.6 OCEAN waveform text

**Origin:** `export_waveform` calls `maeOpenResults`, resolves the actual results directory, calls `openResults`/`selectResults`/`ocnPrint`, then downloads the text file (`runs.py:385-425`). `open_waveform_viewer` instead creates an interactive AWV window and leaves the results session alive (`waveform_viewer.py:49-142`).

**Format:** flat text numeric columns produced by `ocnPrint`; examples parse it as whitespace-separated numeric pairs (`examples/01_virtuoso/maestro/06b_rc_simulate_and_read.py:28-36`). Formatting is controlled by `precision` (1..16), `width` (>=4), and `number_notation` in `{suffix, engineering, scientific, none}`; default number notation is `scientific` (`runs.py:340-383`).

**Replication requirement:** preserve the history/path validation rules and format options, fetch the remote file, and expose a parser or documented text contract. Interactive viewing is not a data format; it is GUI state with session/window handles that must be closed.

### 4.7 Maestro history/result directory formats

| Artifact | Origin and naming | Legacy handling | New upper-layer requirement |
|---|---|---|---|
| `<history>.rdb` | Maestro result anchor; may be `Interactive.N`, custom name, or `.RO` Explorer run | History extraction/sorting (`session.py:33-38,115-128`) | Detect/retain the anchor; do not assume nested integer names only. |
| `<history>.log` | Maestro history log | Captured as an extra snapshot artifact (`snapshot.py:225-246,300-311`) | Download under file role and preserve for review. |
| `<history>.msg.db` | Maestro message database | Captured as an extra result artifact (`snapshot.py:240-245`) | Treat as opaque unless a parser is explicitly added. |
| `results/maestro/<history>/<point>/<test>/netlist/...` | Per-point netlist inputs | Selected via YAML `per_point.netlist` | Download only listed artifacts; preserve relative layout. |
| `results/maestro/<history>/.../psf/...` | Per-point simulation results/logs | Selected via YAML `per_point.psf` | Download listed text PSF/log files; exclude binary/raw by default. |
| `active.state` / `maestro.sdb` | Setup state | Raw + filtered snapshot tracks | Keep raw and filtered forms separate; filter is lossy by design. |

`_dump_run_artifacts` uses a server-side `find ... | tar -chf ... -P -T -` and then downloads/extracts the tarball; it follows symlinks and manually resolves GNU tar hard-link members because Maestro per-point `netlist/` is largely symlinked (`snapshot.py:248-317`). The local snapshot branch uses `Path.rglob` plus `shutil.copy2` with the same YAML patterns (`snapshot.py:326-402`). A new implementation must either reproduce this layout-fidelity behavior or explicitly simplify it.

### 4.8 Standalone Spectre PSF ASCII

**Origin:** `SpectreSimulator` writes `-format psfascii` output under the netlist’s `.raw` or `.psf` directory (`runner.py:145-188` local; `runner.py:240-377` remote). `parse_spectre_psf_ascii` reads one file with UTF-8 replacement decoding and returns a `SimulationResult` (`parsers.py:18-48`).

**Sections:** `HEADER`, `TYPE`, `SWEEP`, `TRACE`, `VALUE`, `END`. `_parse_psf_ascii_content` dispatches to swept parsing when `SWEEP` exists, otherwise non-swept parsing (`parsers.py:300-316`). The parser recognizes:

- swept/transient/AC rows: sweep variable boundaries, trace/group mapping, complex `(real imag)` phasors, scalar values;
- delta-compressed output: a signal omitted at a step carries forward; a signal not seen yet at the first step becomes `math.nan`, not `0.0` (`parsers.py:382-471`);
- non-swept rows: `TYPE`-defined `STRUCT` members flattened as `instance:field`, typed numeric values, bare numeric values, and legacy string tokens (`parsers.py:473-583`).

**Directory aggregation:** `parse_psf_ascii_directory` scans for preferred transient names (`tran.tran.tran`, `tran.tran`), DC names (`dc.dc`, `dcOp.dc`, `spectre.dc`), AC names (`ac.ac`, `ac.ac.ac`), and all `*.info`, adding prefixes as described in §2.7 (`parsers.py:70-197`). `_spectre_psf_scan_root` handles nested `.raw/<name>` and child directories that contain PSF files (`parsers.py:50-68`).

**Sweep layouts:** classic subdirectories `sw*.sweep*/<N>/...` and Spectre X/LX flat files `sw*-NNN_*` are both supported; flat indices are converted from zero-based to one-based (`parsers.py:200-269`).

**Binary PSF:** not parsed by this scope. The reference explicitly says `output_format="psfbin"` is unsupported by the in-tree parser (`skills/spectre/SKILL.md:229-239`). A new upper package must either continue forcing `psfascii`, add a binary parser, or make binary results opaque.

### 4.9 Spectre `.raw`, `.log`, `spectre.out`, and `.measure`

| Format | Legacy handling | Gap / re-development note |
|---|---|---|
| `.raw` directory | Local runner returns it as `output_dir`; remote runner recursively downloads `remote_raw_dir` to `<stem>.raw` and handles nested `<stem>.raw/<stem>.raw` (`runner.py:177-189`, `runner.py:320-376`). | A new upper package must treat `.raw` as an output directory, not a single file; use recursive `download_file`. |
| `spectre.out` / `logFile` / per-point logs | Remote runner downloads optional `spectre.out`, `spectre.fc`, `spectre.ic` (`runner.py:344-354`); error classification uses stdout+stderr, not a tail of `spectre.out` (`runner.py:391-418`). | The legacy runner does not poll log files while the command runs. The AGENTS-level guidance requires future long-running wrappers to tail the tool log for terminal failure markers on every poll. |
| `*.log` | Maestro captures `<history>.log`; standalone parser does not parse it. | Preserve/download or implement a dedicated parser; do not silently infer success from a nonzero-length log. |
| `.measure` | No `.measure` parser or writer exists in the scoped source, tests, examples, or references. The only measurement input is the Spectre netlist directive `measurement=[pm0]` and Maestro output/spec data (`skills/spectre/references/netlist_syntax.md:51-64`; `examples/02_spectre/assets/strongarm_cmp/tb_cmp_strongarm.scs:85`). | Treat `.measure` support as a new capability, not a legacy port. Define the file grammar and whether it is parsed locally, via OCEAN, or as a CSV/JSON projection. |
| `spectre.out` / stdout fatal markers | `_build_simulation_result` scans for read-in errors, license errors, convergence failures, missing files, crashes, and fatal output even when exit code is zero (`runner.py:394-497`). | Reimplement these classifications after `run_spectre_command` returns stdout/stderr; include log-tail checks for long runs. |
| `variables_file` | Captured by snapshot filter as exact per-point design-variable values (`snapshot_filter.yaml:203-204`). | Treat as a PSF-like text snapshot or opaque artifact; no structured parser is present. |

### 4.10 CSV/JSON result bundles

`examples/02_spectre/_result_io.py` defines the example-level bundle contract:

- `save_waveforms_csv(data, path)` writes a rectangular CSV with `time` first when present, then all other list-valued keys; missing values become empty cells (`_result_io.py:22-52`).
- `save_summary_json(result, path, *, extra=None)` writes `status`, `ok`, `tool_version`, signal names, per-signal lengths, errors, warnings, metadata, plus extras (`_result_io.py:55-83`).
- `print_timing_summary` prints `upload_total`, `remote_exec`, `download_total`, `parse_results`, and `total` when numeric (`_result_io.py:13-19,86-94`).
- `print_result_counts` prints error/warning counts (`_result_io.py:97-100`).

The ADC/DAC assets use an external `evas.netlist.runner.evas_simulate` wrapper and write `tran.csv`, not the legacy `SpectreSimulator` JSON path (`analyze_adc_dac_ideal_4b.py:14-30,126-152`; `validate_adc_dac_ideal_4b.py:28-56`). This is real usage evidence but requires a separate decision: adapt EVAS to the five-interface architecture, expose its outputs through a dedicated package, or declare it out of scope.

### 4.11 Spectre netlist `.scs`

The reference contract is a text netlist with `simulator lang=spectre`, includes, instances, analyses (`tran`, `ac`, `pss`, `pnoise`), save controls, and parameter replacements (`skills/spectre/references/netlist_syntax.md:5-100`). The examples generate per-point netlists with `str.replace` or regex and then run them; they do not rely on a `-param` CLI option (`examples/02_spectre/05_parallel_sweep.py:70-76,145-155`). The new upper layer should implement template/parameter substitution in pure Python and upload the resulting files.

## 5. Orchestration and polling patterns

### 5.1 Maestro async run plus callback marker

Legacy `run_and_wait` is the key long-running Maestro pattern (`writer.py:491-575`):

1. Compute one end-to-end deadline with `time.monotonic() + timeout` (`writer.py:506-512`).
2. Generate a nonce and marker `/tmp/vb_sim_done_<nonce>`; remove any stale marker (`writer.py:518-520`).
3. Define a unique SKILL callback procedure. The callback executes `system(sprintf(nil "echo done > <marker>"))` rather than using buffered SKILL `outfile`/`fprintf` (`writer.py:522-529`).
4. Call `maeRunSimulation(?callback <procedure>)` with the remaining timeout, receiving the history name. If the result is nil, run diagnostics (`_diagnose_run_not_started`), attempt to dismiss a modal form via `hiFormDone` and `client.dismiss_dialog()`, and retry once (`writer.py:531-571`).
5. Poll the marker. Local mode checks `Path(marker).exists()` and reads its contents; remote mode runs `cat <marker> 2>/dev/null` with `timeout=min(10, remaining)`; sleep is also capped at `min(2, remaining)` (`writer.py:372-417`).
6. On success, remove the marker and return `(history, status)`; on budget exhaustion, raise `TimeoutError("Simulation did not finish within <timeout>s")` (`writer.py:574-575`, `writer.py:412-417`).

The budget is deliberately shared: the run-start request consumes time and the wait receives only the remaining amount (`test_bak/test_maestro_writer.py:78-102`). A new upper package must reproduce one deadline, not separate uncoordinated timeouts.

**Why this is not a generic `system()`/rc check:** the callback marker is a completion signal, not a simulation status check. The AGENTS guidance notes that `system()` return codes are unreliable for tools that fork or write logs, and that any long poll wrapper must also tail the tool log for terminal failure markers. The legacy Maestro callback does not do that because it only needs to know that Maestro called back; the new business layer should still validate the history and result artifacts.

### 5.2 Maestro dialog and window orchestration

Maestro operations can block the SKILL channel when a GUI dialog appears. Legacy detection and recovery are distributed:

- `_get_session_windows` parses window titles and states with `hiGetWindowList`, `axlGetWindowSession`, `hiGetWindowName`, and pattern matching for `Editing`/`Reading` and trailing `*` (`lifecycle.py:144-186`).
- `_close_gui_window` starts a daemon thread before `hiCloseWindow` if the window is modified, sleeps 0.5 s, and sends X11 Alt+N to dismiss a save dialog (`lifecycle.py:426-468`).
- `_try_recover_blocking_form` first attempts `hiFormDone(hiGetCurrentForm())`, then falls back to `client.dismiss_dialog()` (`writer.py:471-488`).
- `simulation-flow.md` documents that `hiFormDone(hiGetCurrentForm())` is the programmatic dialog dismisser and that GUI dialogs block `execute_skill` (`skills/virtuoso/references/maestro-skill-api.md:442-447`).

The new architecture does not provide a persistent GUI session. A re-development must treat dialog detection/dismissal as discrete `run_gui_command` calls, or as separate SKILL calls when the SKILL channel is not blocked. The legacy background X11 thread has no direct equivalent in a one-shot GUI command; the upper package must define a race-free sequence or deliberately omit automatic dismissal.

### 5.3 Maestro result polling and materialization

`read_results` does not poll a log. It:

1. Resolves lib/cell from arguments or `maeGetEnvOption` (`runs.py:88-99`).
2. Gets the first test with `maeGetSetup` (`runs.py:108-116`).
3. If no history is supplied, scans project results newest-first, calls `maeOpenResults`, checks `maeGetResultOutputs`, and closes results (`runs.py:118-130,186-210`).
4. Exports Detail CSV to a unique remote temp path (`runs.py:132-147`).
5. Attempts `download_file`; download/materialization is the success criterion, regardless of the SKILL return value (`runs.py:149-162`).
6. Reads overall spec/yield and parses the CSV (`runs.py:174-180`).

This is a “produce artifact, then download as arbiter” pattern. A new upper package should use `execute_skill` to request the export and `download_file` to decide whether it exists, then parse locally. It must define cleanup for temp files on the correct file role.

### 5.4 Standalone Spectre synchronous run

Legacy standalone Spectre does not use a marker callback. It runs a blocking subprocess/remote task:

- Local: `subprocess.run(command, capture_output=True, text=True, timeout=timeout, cwd=cwd)`; `FileNotFoundError`, `TimeoutExpired`, and `OSError` become `_SpectreRunResult(success=False, error=...)` (`runner.py:169-210`).
- Remote: upload netlist/includes; execute a csh/sh command in a UUID remote run directory; wait for the remote task; download raw results recursively and selected aux files; clean the remote run directory unless `keep_remote_files` (`runner.py:216-377`).
- Result assembly then parses the output directory and classifies errors (`runner.py:383-475`).

`run_spectre_command` in the new architecture is a one-shot command, so the upper layer must construct the full command including environment setup and output path, and must separately fetch outputs through the file interface. There is no persistent cwd/env between calls. If the Spectre role is split from the file role, the upper package must account for the spec’s explicit non-guarantee of cross-role file visibility (`spec/design-concepts/中层/3-路由设计.md:97-99`).

### 5.5 Parallel Spectre patterns

`run_parallel` creates one scoped `ThreadPoolExecutor`, submits one task per `(netlist, params)`, and waits in submission order (`runner.py:833-871`). `SpectrePool` provides incremental submission and context-managed shutdown (`runner.py:514-580`). Each task reserves a unique local directory `<stem>__<8-hex>` (`runner.py:760-767`) and the remote path uses a UUID run id (`runner.py:230-231`). Future exceptions become `SimulationResult(status=ERROR, errors=["Task <i> failed: ..."])` rather than escaping (`runner.py:855-868`).

A new upper package can reuse the scheduling logic in pure Python, but must route each actual simulation through `run_spectre_command` and each transfer through the file interface. It cannot assume that legacy `ThreadPoolExecutor` concurrency is permitted: the middle layer accounts for channel/thread budgets per token and may return `kind=rejected` (`spec/design-concepts/总览/1-四层整体架构与接口.md:263,340-350`).

### 5.6 Log tailing and failure-marker policy

Legacy standalone Spectre reads stdout/stderr after the command completes. It has no in-loop tail. The scoped reference documents a real failure mode in which a wrapper returns zero while Spectre prints a fatal error; `_has_fatal_spectre_error` exists specifically to catch that (`runner.py:490-497`; test `test_bak/test_spectre_parsers.py:314-336`). The AGENTS instructions additionally require future wrappers to poll the tool’s own log for terminal-failure markers on every poll iteration.

Therefore a new upper-layer long-running Spectre package should implement:

1. a unique remote run directory;
2. a command string that redirects/logs to a known file;
3. a poll loop using `run_command`/`run_spectre_command` with bounded intervals;
4. a tail/read of the log each iteration;
5. success only when the expected result artifact or terminal success marker exists;
6. failure fast on `error`, `translation failed`, `OPEN_FAILED`, fatal Spectre, convergence-failure, or license sentinels;
7. an end-to-end timeout shared across upload, execution, and download.

## 6. Pure Python vs SKILL vs external-tool split

### 6.1 Pure Python

| Area | Legacy code | Re-development implication |
|---|---|---|
| XML filtering/YAML loading | `_parse_sdb.py:21-174` | Keep as pure upper-layer parsing; package the YAML asset or accept a config path. |
| SKILL-output tokenization/parsing | `_parse_skill.py`, shared `skill_output.py` | Pure Python; needed only when converting raw SKILL returns. |
| History discovery/sorting | `session.py:25-175` | Pure Python; no middle interface. |
| Detail CSV parser | `runs.py:213-321`; tests `test_maestro_read_results.py:57-91` | Pure Python; preserve string-valued cells rather than coercing. |
| Waveform-option validation | `runs.py:360-377` | Pure Python parameter validation. |
| Snapshot filename/path selection | `snapshot.py:148-171,405-422` | Pure Python planning; actual bytes cross `download_file`/`run_command`. |
| PSF ASCII parser | `parsers.py:18-583` | Pure Python; can be moved into an upper package without middle calls. |
| Typed PSF helpers | `psf.py:14-83` | Pure Python validation and local-path security. |
| CSV/JSON result bundles | `examples/02_spectre/_result_io.py:22-100` | Pure Python; examples only, but a reasonable model for a new result package. |
| Delay/bandwidth/noise/FOM measurement | `examples/02_spectre/05_parallel_sweep.py:79-109`; `assets/strongarm_cmp/analyze_strongarm_pss_pnoise.py:15-99` | Pure Python/NumPy; no Virtuoso or Spectre API dependency. |
| Parallel scheduling bookkeeping | `runner.py:514-580,833-871` | Pure Python scheduling wrapper; actual commands still route through middle. |

### 6.2 SKILL round-trips

| Area | Legacy SKILL surface | New middle call |
|---|---|---|
| Maestro lifecycle/state | `maeOpenSetup`, `maeCloseSession`, `maeGetSessions`, `deOpenCellView`, `maeMakeEditable`, `hiCloseWindow`, `dbPurge`, title/window probes | `execute_skill` |
| Maestro setup mutation | `maeCreateTest`, `maeSetDesign`, `maeSetAnalysis`, `maeAddOutput`, `maeSetSpec`, `maeSetVar`, `maeGetVar`, `maeSetParameter`, `maeSetEnvOption`, `maeSetSimOption`, `maeSetCorner`, `axl*`, `maeLoadCorners`, run/job modes, `maeSaveSetup` | `execute_skill` |
| Maestro simulation/status | `maeRunSimulation`, callback procedure, `hiFormDone`, diagnostics | `execute_skill` |
| Maestro result access | `maeOpenResults`, `maeGetResultOutputs`, `maeCloseResults`, `maeExportOutputView`, `maeGetOverallSpecStatus`, `maeGetOverallYield` | `execute_skill` |
| OCEAN and waveform viewer | `openResults`, `selectResults`, `ocnPrint`, `awvCreatePlotWindow`, `awvPlotWaveform`, `v`, `maeGetOutputValue`, window/session cleanup | `execute_skill` |
| Docs’ fallback APIs | `asi*` equivalents for older Virtuoso environments and `sevRun(sevSession(win))` for ADE Explorer (`maestro-skill-api.md:36-68`) | `execute_skill`; the upper package must choose/version-detect. |

### 6.3 External processes/tools

| Tool/process | Legacy usage | New lower/upper boundary |
|---|---|---|
| `spectre` | local `subprocess.run` or remote shell; mode args; output/raw/log paths (`runner.py:91-377`) | `run_spectre_command` (one-shot). |
| `lmstat` | license lines in local/remote license check (`runner.py:900-949`) | `run_spectre_command` or `run_command` depending on the registered role; not middle business logic. |
| `csh` | source Cadence/Mentor cshrc before Spectre or version check (`runner.py:165-166,255-277,932-940`) | Build the source/prefix into each one-shot command; environment is not retained. |
| shell utilities | `find`, `tar`, `rm`, `cat`, `mkdir` for snapshots/markers/temp files (`snapshot.py:256-323`; `writer.py:404-405`; `examples/01_virtuoso/maestro/09_export_sweep_subpoints.py:110`) | `run_command`; file transfer through `upload_file`/`download_file`. |
| X11 key injection | `python2.7` + `ctypes` X11/XTest in `lifecycle.py:79-119` | `run_gui_command`; no persistent GUI session. |
| `scp`-style transfer | `client.download_file` / `client.upload_file` in legacy (`snapshot.py:36-44`; runner remote download) | `download_file`/`upload_file`. |
| `evas.netlist.runner` | ADC/DAC examples call external `evas_simulate` (`analyze_adc_dac_ideal_4b.py:14-16`) | Not part of the five interfaces; needs an explicit decision. |

### 6.4 Mixed pipelines that need careful decomposition

| Pipeline | Pure Python part | SKILL part | External/file part |
|---|---|---|---|
| Full Maestro simulation | choose netlist/cell, parse results | open session/evaluate setup/start run/callback/result export | marker file, CSV download, waveform download |
| Snapshot | select histories/filter XML/format sections | focused-window and full bundle probes | XML download, mtime `find`, tar download/extract |
| Maestro waveform export | validate format and parse downloaded text | open/select/print OCEAN | remote temp file download/delete |
| Standalone Spectre run | build argv, parse PSF, classify output | none | upload netlist/includes, run Spectre, download raw/log |
| Parallel sweep | generate point netlists, schedule, measure | none | upload/run/download all points |
| License check | parse output into result dict | none | run Spectre/lmstat, source environment |

## 7. State/files/IPC dependencies that will not exist in the new upper layer

### 7.1 Direct legacy client and transport dependencies

| Legacy dependency | Evidence | Why it is unsafe in the new upper layer | Required replacement/risk |
|---|---|---|---|
| `VirtuosoClient` as first argument to every function | `lifecycle.py:217-423`; `writer.py:32-673`; `runs.py:37-425`; `snapshot.py:429-517` | Upper packages may depend only on the `Middle` protocol, not on concrete client classes. | Replace client parameter with an injected `Middle` and a token per call. High risk at every function boundary. |
| `client.execute_skill` | All SKILL wrappers | Middle call needs `timeout` and `token`; legacy often omits token and has varying timeout behavior. | Route through `middle.execute_skill`; decide per-call deadlines and `VirtuosoResult.error` mapping. |
| `client.download_file` / `client.upload_file` | `snapshot.py:36-44,67-80`; `runs.py:149-153,423`; examples | The new file role may be different from the Skill/daemon host and is not guaranteed to share paths (`3-路由设计.md:97-99`). | Use `download_file`/`upload_file`; resolve paths per role; split-host behavior must be explicit. High risk. |
| `client.ssh_runner` | `lifecycle.py:447`; `writer.py:388,516`; `snapshot.py:196` | Upper layer must not touch SSH objects, tunnels, or transport internals. | Replace with `run_command`/file interfaces. Marker polling and `find`/`tar` commands must be re-expressed. |
| `client._tunnel._ssh_runner` | `bundle.py:270` | Private transport reach-through. | Replace mtime lookup with `run_command("find ... -printf ...")` or a file-interface protocol. |
| `client.dismiss_dialog` | `writer.py:485` | It is a concrete GUI-control method. | Use `run_gui_command` for X11/dialog operations or a SKILL `hiFormDone` path when available. |
| `client.open_window` | `maestro-skill-api.md:543-545` | Not part of the new upper interface. | Open/focus must be decomposed into SKILL or GUI commands with a defined focus contract. |
| `SSHClient.is_running`, `SSHClient.from_env`, `SSHRunner` | `runner.py:693-704,1009-1025` | The new middle layer owns routing and tunnels; upper code cannot import/use them. | Resolve Spectre/command/file roles through the middle implementation; no direct transport object. |
| `subprocess.run` | `runner.py:170,891,901`; `lifecycle.py:32-38` | Direct process invocation violates upper-layer boundary. | `run_spectre_command`, `run_command`, or `run_gui_command` as appropriate. |

### 7.2 Environment, configuration, and profile state

| Legacy state | Evidence | New-layer risk |
|---|---|---|
| `VB_REMOTE_HOST`, `VB_REMOTE_USER`, `VB_GUI_HOST`, `VB_DAEMON_HOST`, `VB_SPECTRE_HOST`, `VB_JUMP_HOST`, ports | `global .env`; `runner.py:18-38,633-654`; `from_env` at `runner.py:659-716` | The new architecture uses registration/token/roles, not `.env`/profile/transport globals. Any upper function that reads these directly is invalid. |
| `VB_CADENCE_CSHRC`, `VB_MENTOR_CSHRC` | `runner.py:256-266,987-1000`; `check_license` `runner.py:922-940` | Environment setup must be encoded into the one-shot command or supplied by the role, not inherited from an upper-layer `.env`. |
| `VB_SPECTRE_BIN`, profile suffix | `runner.py:607-614,916-920` | The spec records `role.spectre.bin` at registration; the upper layer should use that value rather than environment variables. |
| `VB_OUTPUT_DIR`, `artifact_dir` | `runner.py:20,145,1054-1058`; tests `test_bak/test_spectre_runtime_paths.py:13-33` | The new upper layer cannot assume a local artifact root or a shared filesystem; output location must be a business input or role-derived contract. |
| `profile` and `.env` resolution | `runner.py:605,628,676-680` | Profiles are legacy multi-server routing. New upper packages must not implement profile/registry/tunnel semantics. |
| `load_vb_env()` | `runner.py:18,606,678` | Environment mutation is not an upper-layer operation. |
| CWD/environment persistence | local subprocess `cwd`; remote `cd` is folded into one command (`runner.py:169-175,271-287`) | `run_spectre_command` is one-shot; every call must re-establish cwd/env and cannot rely on a prior shell. |

### 7.3 Remote filesystem and POSIX assumptions

| Assumption | Evidence | Risk in the new architecture |
|---|---|---|
| Remote `/tmp` is writable and visible to the Maestro/result tool | marker `/tmp/vb_sim_done_*` (`writer.py:519`), CSV `/tmp/vb_results_*` (`runs.py:137`), waveform `/tmp/vb_wave_*` (`_skill.py:18-22`), tarball `/tmp/vb_snap_*` (`snapshot.py:211`) | Skill/daemon, command, and file roles may be split; a temp path on one role may not be visible to another. Use a registered role root and explicit file transfer. High risk. |
| Maestro scratch root can be derived from `asiGetAnalogRunDir` | `bundle.py:206-211,233-240` | Path derivation is environment-specific and may fail; snapshot treats scratch as optional, but a new business API should expose failure/partial status. |
| Per-point `netlist/` and `psf/` trees preserve a particular layout and contain symlinks | `snapshot.py:248-317,326-342` | `download_file(recursive=True)` does not promise symlink preservation; it follows symlinks according to the file contract (`1-四层整体架构与接口.md:286-290`). Artifact mapping must match the new transfer semantics. |
| `find -printf`, GNU `tar --ignore-failed-read`, `-h`, hard-link rows | `bundle.py:284-295`; `snapshot.py:256-317` | Not portable to non-GNU roles and not a middle-layer guarantee. A new implementation should use explicit file lists or a portable archive strategy. |
| POSIX shell syntax | `cat`, `rm -f`, `mkdir -p`, `find`, `tar`, `csh`, backticks | New command roles may use different shells or wrappers. The upper package must specify shell semantics, or the middle contract must be documented accordingly. |
| X11 and Python 2.7 availability | `lifecycle.py:84-119` | A GUI command role may not provide Python 2.7, `ctypes`, or XTest. Use a supported GUI command tool or declare dialog automation unsupported. |
| Cadence GUI focus/window state | `hiGetCurrentWindow`, `hiGetWindowList`, `davSession`, title parsing | The new upper layer has no guaranteed persistent window/focus state; `run_gui_command` is one-shot. Focus-sensitive snapshot semantics must be redefined or exposed explicitly. |

### 7.4 Result/state and IPC dependencies

| Dependency | Evidence | Re-development risk |
|---|---|---|
| `maeRunSimulation(?callback ...)` behavior and callback timing | `writer.py:522-538`; docs `simulation-flow.md:67-74` | Callback semantics are Cadence/version-dependent. The upper layer must define whether it supports callbacks or falls back to artifact polling. |
| `maeWaitUntilDone` | reference only `maestro-skill-api.md:353-360`; not implemented in the scoped writer | Blocking the SKILL channel can break the bridge; do not use as the default. |
| `maeOpenResults`/`maeCloseResults` global result context | `runs.py:186-210,403-417` | Result context is process-global/shared. Concurrent upper-layer reads may interfere; serialize or scope access. |
| `hiFormDone` / modal dialogs | `writer.py:471-488`; `maestro-skill-api.md:442-447` | A blocked Skill channel cannot be fixed by another `execute_skill`; must use a GUI command or external dismissal path. |
| `system("echo ... > marker")` callback | `writer.py:522-529` | `system()` return codes are unreliable; use it only to create a marker, and verify the marker/artifact separately. |
| `ocnPrint`, `openResults`, `selectResults` session state | `runs.py:403-421`; example `09_export_sweep_subpoints.py:62-76` | OCEAN context persists across SKILL calls. Concurrent operations or a session reset can poison later exports. |
| `lmstat`/license server state | `runner.py:900-949` | License availability is external, not deterministic; report as information and do not use it as a hard simulation gate unless explicitly designed. |
| Cadence version differences | `maestro-skill-api.md:45-68`; `writer.py:343-345` result-return comments | `mae*` vs `asi*`, Explorer vs Assembler, and export-return behavior vary. Version detection/fallback is business logic that has not been centralized. |
| ADE Explorer session model | docs `maestro-skill-api.md:36-43`; error hint `writer.py:565-570` | `maeRunSimulation` may not start Explorer; new code must detect Explorer and use `sevRun(sevSession(window))` or reject it explicitly. |
| Pnoise jitter-event table | `maestro-skill-api.md:449-503` | Not fully automatable via `maeSetAnalysis`; the legacy workaround edits `active.state` directly. A new upper package must decide whether to support this via file copy/transform or declare it unsupported. |
| CDF/schematic preconditions | `maestro-skill-api.md:444-447`; example `06a_rc_create.py:82-96` | The simulation setup may depend on schematic check/save and GUI context. This is outside the Maestro reader/writer and must be explicit in a business workflow or rejected. |

### 7.5 Risk ranking for the port

| Rank | Risk | Reason |
|---|---|---|
| Critical | Split-role file visibility | Maestro and Spectre code heavily assume remote paths are visible to the same process that runs commands; the new spec explicitly does not guarantee this. |
| Critical | No concrete client/SSH/tunnel in upper layer | Almost every legacy entry point takes `VirtuosoClient`; this is a mechanical but pervasive rewrite. |
| High | Background vs GUI simulation contradiction | The code, tests, examples, and reference docs disagree (§9.1). |
| High | Blocking GUI dialogs and X11 dismissal | The Skill channel blocks; one-shot GUI commands may not reproduce the legacy thread race. |
| High | One-shot Spectre command semantics | Legacy `subprocess`/remote task retains a run directory and cwd; middle `run_spectre_command` does not retain cwd/env. |
| High | Artifact retrieval and cleanup | Raw directories, temp CSV/waveforms, tarballs, and markers can land on different roles. |
| Medium | PSF parser breadth | Delta compression, complex phasors, struct flattening, flat/subdir sweeps, escape characters, and binary gap. |
| Medium | Version/API drift | `mae*`/`asi*`/`sev*` and CSV export behavior differ across Virtuoso releases. |
| Medium | Error/status semantics | Legacy often returns `{}`, throws `RuntimeError`, or returns a partial result; new contract should use structured status/errors. |
| Medium | SKILL string escaping | Some writer functions escape inputs; many interpolate directly. A centralized escaping policy is missing. |

## 8. Test/example evidence

### 8.1 Maestro facade tests

`test_bak/test_maestro_ops.py`

| Assertion | Evidence |
|---|---|
| `VirtuosoClient.local().maestro` is `MaestroOps`. | `test_maestro_ops.py:8-11` |
| `MaestroOps` exposes exactly the expected 37 client-bound names, including lifecycle, snapshot/read/export, all writer functions, waveform viewer, and migration. | `test_maestro_ops.py:14-29` |
| Facade forwards the owner object and positional arguments unchanged. | `test_maestro_ops.py:32-45` |
| Keyword-only configuration (`enable`, `options`, `session`) is forwarded unchanged. | `test_maestro_ops.py:48-77` |

Observable behavior to preserve: the facade is a pure owner-injecting adapter; it must not reimplement or rename the underlying operations.

### 8.2 Maestro result/reader tests

`test_bak/test_maestro_read_results.py`

| Assertion | Evidence |
|---|---|
| Multi-point Detail CSV yields `history`, one test, two points, per-point parameters, per-point outputs, and a four-entry flat output list. | `test_maestro_read_results.py:34-69` |
| Empty CSV yields empty `points`, `outputs`, `tests`. | `test_maestro_read_results.py:71-75` |
| Single-point CSV without a Point column yields one point, no `Detail Results` row, and three output entries. | `test_maestro_read_results.py:46-54,78-91` |
| `maeExportOutputView` returning `t` must not cause an empty result if the CSV materialized. | `test_maestro_read_results.py:134-162` |
| Missing CSV produces a warning naming `maeExportOutputView` and returns `{}`. | `test_maestro_read_results.py:164-183` |
| `maeGetSetup` returning nil (especially fresh Explorer) returns `{}` and logs `maeGetSetup returned no test`. | `test_maestro_read_results.py:186-201` |
| Default OCEAN export uses `?numberNotation 'scientific` and omits precision/width. | `test_maestro_read_results.py:215-230` |
| Explicit precision/width/notation are emitted. | `test_maestro_read_results.py:233-251` |
| All four supported number notations are accepted. | `test_maestro_read_results.py:254-272` |
| Invalid precision/width/notation types and ranges raise before any SKILL call. | `test_maestro_read_results.py:275-303` |

Observable behavior to preserve: result export must be artifact-materialization driven, parser output must remain string-preserving, and invalid format options must fail without side effects.

### 8.3 Maestro writer tests

`test_bak/test_maestro_writer.py`

| Assertion | Evidence |
|---|---|
| Omitting `session` produces the current-session form `maeCreateNetlistForCorner("tran_test" "tt" "/tmp/tran_tt")`. | `test_maestro_writer.py:30-43` |
| `add_output` escapes every string parameter, including name, test, output type, signal, expression, and session. | `test_maestro_writer.py:46-64` |
| `run_simulation` forwards the timeout to the SKILL request and escapes session/callback. | `test_maestro_writer.py:67-75` |
| `run_and_wait(timeout=60)` passes 60 to the run-start call and 48 to the poll after 12 seconds of simulated start latency. | `test_maestro_writer.py:78-102` |
| Remote marker polling caps `cat` timeout at 10/remaining seconds and sleep at 2/remaining seconds; a 3-second budget produces command timeouts `[3, 1]` and sleeps `[2, 1]`, then raises `TimeoutError` matching `within 3s`. | `test_maestro_writer.py:105-128` |
| Explicit session is appended to the corner-netlist SKILL. | `test_maestro_writer.py:131-145` |
| `session` is keyword-only for `create_netlist_for_corner`. | `test_maestro_writer.py:148-158` |
| The facade forwards the explicit session to the same corner-netlist operation. | `test_maestro_writer.py:161-174` |

Observable behavior to preserve: exact SKILL construction, keyword-only session, selected escaping, one end-to-end wait budget, and bounded remote polling. Note that only selected writer functions are tested for escaping; many other writer functions still interpolate raw strings.

### 8.4 Maestro waveform-viewer tests

`test_bak/test_maestro_waveform_viewer.py`

| Assertion | Evidence |
|---|---|
| Open SKILL includes capability checks, `maeOpenSetup`, `maeOpenResults`, `openResults`, `v(...)`, `awvCreatePlotWindow`, and `awvPlotWaveform`. | `test_maestro_waveform_viewer.py:13-31` |
| Successful open sets `vbOpenOk = t` and returns a list containing library, cell, view, history, session, and window id. | `test_maestro_waveform_viewer.py:33-45` |
| Failed open closes any window/session and raises `"open waveform viewer failed"`. | `test_maestro_waveform_viewer.py:47-60` |
| Library/cell/history/signal/test/result/results-dir strings are escaped. | `test_maestro_waveform_viewer.py:63-81` |
| When `results_dir` is supplied, a failed raw `openResults` is an error. | `test_maestro_waveform_viewer.py:83-93` |
| `test` and `result` semantics are documented. | `test_maestro_waveform_viewer.py:95-100` |
| Without `results_dir`, missing signal falls back to `maeGetOutputValue`. | `test_maestro_waveform_viewer.py:102-113` |
| Empty signals raises. | `test_maestro_waveform_viewer.py:115-117` |
| Close SKILL validates `window(7)`, closes `maeCloseSession`, checks `maeGetSessions()`, and raises if the session remains. | `test_maestro_waveform_viewer.py:120-130` |
| Session is escaped; accepted window forms are `window:7` and `window(8)`; blank/invalid/unsafe targets reject. | `test_maestro_waveform_viewer.py:132-162` |
| `open_waveform_viewer` executes generated SKILL and forwards timeout; docstring documents the raw-result handle contract. | `test_maestro_waveform_viewer.py:165-198` |
| `close_waveform_viewer` executes generated close SKILL and forwards timeout. | `test_maestro_waveform_viewer.py:200-222` |

Observable behavior to preserve: explicit signal validation, fallback path, raw result list shape, deterministic cleanup, and strict window-reference validation.

### 8.5 Snapshot-filter test

`test_bak/test_maestro_snapshot_filter.py:9-11` asserts that `exprOutputs.json` is both in `_DEFAULT_NETLIST_FILES` and in the YAML-derived `_per_point_list("netlist", ...)`. This pins the YAML override/fallback behavior and the importance of output-expression definitions in a snapshot.

### 8.6 Spectre parser tests

`test_bak/test_spectre_parsers.py`

| Assertion | Evidence |
|---|---|
| Swept `"time"` vector is parsed exactly. | `test_spectre_parsers.py:37-78` |
| A signal present at every step retains its values. | `test_spectre_parsers.py:76-77` |
| A signal absent at the first step yields `NaN` at that step, then its real values. | `test_spectre_parsers.py:80-90` |
| AC `(real imag)` values remain Python complex phasors. | `test_spectre_parsers.py:93-117` |
| Classic `sw*.sweep*/<N>/...` layouts yield one-based point keys. | `test_spectre_parsers.py:140-182` |
| Flat Spectre X/LX `sw*-NNN_*` layouts are recognized and zero-based file indices become one-based point keys. | `test_spectre_parsers.py:152-193` |
| No recognized sweep layout returns `{}`. | `test_spectre_parsers.py:196-200` |
| STRUCT operating-point values are flattened as `M0:gm`, `M0:vth`, `M0:region`. | `test_spectre_parsers.py:207-242` |
| `_build_simulation_result` places sweep data at `metadata["sweep_points"]`. | `test_spectre_parsers.py:249-271` |
| `"Circuit read-in complete"` is not a read-in error. | `test_spectre_parsers.py:273-284` |
| Actual `"error reading..."` is classified as `"netlist read error"`. | `test_spectre_parsers.py:287-300` |
| Successful convergence chatter is not a failure. | `test_spectre_parsers.py:302-311` |
| A zero-exit run with `ERROR (SFE-23)` becomes failure. | `test_spectre_parsers.py:314-324` |
| A zero-exit PSS `SPCRTRF-15044` convergence failure is marked `"convergence failure"`. | `test_spectre_parsers.py:327-336` |

Observable behavior to preserve: delta-compression semantics, NaN (not zero) for missing early samples, complex phasors, one-based sweep points, struct flattening, and fatal-output classification independent of exit code.

### 8.7 Spectre PSF-helper tests

`test_bak/test_spectre_psf.py` pins:

- `scalar` accepts a finite real and rejects missing, complex, list, NaN, bool, and string values (`test_spectre_psf.py:18-32`).
- `vector` accepts numeric values/complexes and rejects empty, non-finite, bool, and string vectors (`test_spectre_psf.py:35-54`).
- `frequency_hz` rejects complex, non-increasing, and non-numeric frequency vectors (`test_spectre_psf.py:35-54`).
- `result_file` requires exactly one match below a raw root; a wildcard matching two files raises (`test_spectre_psf.py:57-68`).
- Absolute paths, `..`, and symlink escapes are rejected (`test_spectre_psf.py:71-85`).
- `read_psf_ascii` returns `{"time": [0.0], "vout": [1.25]}` for a minimal file and raises `ValueError` containing `"no data parsed"` for an empty/invalid file (`test_spectre_psf.py:88-101`).

### 8.8 Spectre runtime-path tests

`test_bak/test_spectre_runtime_paths.py` pins:

- Local Spectre defaults to `<VB_OUTPUT_DIR>/spectre/<netlist-stem>` and does not write raw output next to the netlist (`test_spectre_runtime_paths.py:13-33`).
- Per-run `spectre_args` are passed and `include_files` are staged into the work directory (`test_spectre_runtime_paths.py:36-57`).
- Configured Cadence cshrc causes `["csh", "-fc", "... source /eda/cadence.cshrc ..."]` (`test_spectre_runtime_paths.py:60-78`).
- Synchronous local simulation keeps a configured work directory (`test_spectre_runtime_paths.py:94-110`).
- Parallel local runs receive unique `<stem>__<8-hex>` directories under `work_dir` (`test_spectre_runtime_paths.py:113-135`).
- Parallel remote runs receive unique local download directories under `work_dir` (`test_spectre_runtime_paths.py:138-165`).
- Each batch creates its own executor with the requested worker count and shuts it down (`test_spectre_runtime_paths.py:168-203`).
- Explicit `SpectrePool` owns its lifecycle and rejects submission after context exit (`test_spectre_runtime_paths.py:206-222`).
- Worker count must be a positive integer; zero/bool-like invalid values raise (`test_spectre_runtime_paths.py:225-231`).
- Deprecated simulator-owned pool state does not leak into scoped batches and cannot be resized after first submission (`test_spectre_runtime_paths.py:234-261`).

### 8.9 Example evidence for Maestro

| Example | Observable behavior that pins the intended business flow |
|---|---|
| `01_read_focused_maestro.py:18-33` | `snapshot()` without an output root returns focused session/lib/cell/view metadata; non-Maestro focus produces a user-facing error. |
| `02_snapshot_with_metrics.py:36-53` | `snapshot(output_root=...)` returns `output_dir` and writes a disk snapshot. The docstring additionally claims `state_from_skill.json`, `histories.json`, `latest_history.json`, `raw_skill.json`, and `probe_log.json`, which the current source does **not** write; see §9.2. |
| `03_bg_open_read_close_maestro.py:52-95` | Background open, `maeGetSetup`, and close in `finally`; failures are surfaced as diagnostics. |
| `04_gui_open_snapshot_close.py:40-60` | GUI open returns a session, snapshot must return the same focused session, and close happens in `finally`. |
| `05_gui_session_lifecycle.py:103-271` | Reuse of Editing sessions, conversion of Reading to Editing, background/lock cleanup, save-before-close, Reading* discard/promote behavior, and SKILL-channel liveness (`1+1 == 2`) after close. |
| `06a_rc_create.py:98-121` | Programmatic creation of test, AC analysis, outputs/spec, sweep variable, save, and close. |
| `06b_rc_simulate_and_read.py:65-141` | Background `run_and_wait`, `read_results`, OCEAN magnitude/phase export, whitespace waveform parsing, and `-3 dB` interpolation. This conflicts with the GUI-only rule in the reference docs (§9.1). |
| `07_ensure_maestro_view.py:44-93` | A missing `maestro` view is created by `maeOpenSetup` + `maeSaveSetup`, then GUI-open succeeds and is closed with `save=False`. |
| `08_set_simulator_mode.py:69-185` | Simulator mode is set with `asiSetHighPerformanceOptionVal`, persisted with `maeSaveSetup`, then read back and verified. |
| `09_export_sweep_subpoints.py:51-128` | OCEAN `openResults`/`selectResult`/`ocnPrint` per sweep point, remote temp dir creation via `system("mkdir -p ...")`, and per-file download. |

### 8.10 Example evidence for Spectre

| Example | Observable behavior that pins the intended business flow |
|---|---|
| `01_inverter_tran.py:89-162` | Mode parsing, `SpectreSimulator.from_env`, single run, `result.data["time"]/["VIN"]/["VOUT"]`, CSV/plot/summary outputs, timing summary. |
| `01_veriloga_adc_dac.py:25-53,172-253` | Per-case include files, `run_simulation(netlist, {"include_files": include_files})`, waveform keys, CSV/JSON outputs. |
| `02_cap_dc_ac.py:30-116` | DC scalars (`dc_VDD`, `dc_VO`), AC complex vectors (`ac_freq`, `ac_VO`), magnitude/dB conversion, bandwidth measurement, summary JSON. |
| `03_check_license.py:37-86` | `check_license()` returns path/version/licenses/raw stdout/stderr and is mapped to a success/failure JSON summary. |
| `04_strongarm_pss_pnoise.py:52-143` | Single-point PSS/Pnoise run, `extract_metrics(raw_dir, vcm=...)`, metrics JSON, time-domain plot, summary JSON. |
| `05_parallel_sweep.py:129-231` | Generate one netlist per load value, `run_parallel(...)`, per-result delay measurement, plot, succeeded/failed summary. |
| `assets/strongarm_cmp/analyze_strongarm_pss_pnoise.py:25-99` | Parse `pss.td.pss` and `pnoiseMpm0.0.sample.pnoise`, compute average current/power, crossing times, integrated noise, FOM, pass/fail. |
| `assets/adc_dac_ideal_4b/analyze_adc_dac_ideal_4b.py:14-30,126-152` | External `evas_simulate` writes `tran.csv`; analysis uses `numpy.genfromtxt` with named fields, post-reset masks, code reconstruction, quantization error. |
| `assets/adc_dac_ideal_4b/validate_adc_dac_ideal_4b.py:50-95` | Validation of distinct codes, code span, output range, integer codes, truncation error bounds, and LSB bounds. |

## 9. Open questions / ambiguities

### 9.1 Background vs GUI simulation is contradictory across the legacy evidence

The reference docs say background sessions cannot reliably run simulations and that `run_and_wait`’s callback never fires in background; GUI mode is required (`skills/virtuoso/references/maestro-python-api.md:19-28`; `skills/virtuoso/references/simulation-flow.md:1-5`). However:

- `writer.run_and_wait` itself has no GUI check and only takes a session string (`writer.py:491-575`).
- Example `06b_rc_simulate_and_read.py` explicitly opens a background session and calls `run_and_wait` (`examples/01_virtuoso/maestro/06b_rc_simulate_and_read.py:2-6,65-78`).
- Example `05_gui_session_lifecycle.py` is a GUI-only lifecycle matrix, so it does not resolve the contradiction.

Question: which session mode is normative for the new upper-layer simulation package? If background is supported, the business API needs a separate background-run contract and must not close the session while the run is in flight. If GUI-only is normative, example `06b` should be treated as stale or environment-specific.

### 9.2 Snapshot output is documented differently from the source

`examples/01_virtuoso/maestro/02_snapshot_with_metrics.py:4-22` claims the disk dump includes `state_from_skill.json`, `histories.json`, `latest_history.json`, `raw_skill.json`, and `probe_log.json`. The actual scoped implementation writes `state_from_skill.txt` and the raw/filtered XML files, plus run artifacts, but there is no writer for those JSON files or `histories.json`/`probe_log.json` (`snapshot.py:83-102,405-422`). The reference API documents the simpler actual layout (`maestro-python-api.md:94-116`).

Question: is the JSON/history metadata part of a newer or older branch that should be preserved, or is the example stale? The new upper package needs one canonical snapshot result schema.

### 9.3 How should the upper layer represent recoverable “empty” results?

`read_results` returns `{}` for missing lib/cell, no test, no history, or failed download (`runs.py:100-130,149-162`), while writer helpers raise `RuntimeError` on SKILL errors (`writer.py:20-25`). Snapshot raises only when `output_root` is requested with no focused window (`snapshot.py:483-485`), and many snapshot download/subprocess failures are silently swallowed (`snapshot.py:36-44,262-264,289-295,318-323`). The new `VirtuosoResult`/`SimulationResult` models can express `ERROR`, `FAILURE`, and `PARTIAL`, but the legacy package uses several inconsistent conventions.

Question: should the new business API preserve legacy empty-dict semantics for compatibility, or normalize to explicit structured status plus partial artifacts? The answer changes every parser/reader contract.

### 9.4 What is the contract for split-role files and paths?

The legacy Maestro and Spectre code assumes remote paths returned by Cadence or by the remote runner can be consumed by the same `download_file` client. The new spec explicitly allows `daemon`, `command`, `file`, `gui`, and `spectre` to be on different hosts with no shared filesystem, and says cross-role file visibility is not guaranteed (`spec/design-concepts/中层/3-路由设计.md:50-55,97-99`).

Questions:

- If Skill returns `/home/user/project/...`, which role owns that path?
- Does `download_file` address the file role’s root or the same host as the Command/Skill role?
- How should snapshot tar/marker/temp paths be chosen when more than one role is remote?
- Should the upper package require same-host deployment for Maestro/Spectre workflows, or expose a “path portability” precondition?

### 9.5 What can `run_gui_command` actually do?

Legacy GUI behavior depends on X11, window focus, `hiGetWindowList`, `hiFormDone`, title parsing, and a Python 2.7 XTest key injector (`lifecycle.py:24-119,144-186,426-468`). The new GUI interface is explicitly one-shot and does not keep a persistent shell/session (`spec/design-concepts/总览/1-四层整体架构与接口.md:209`; `3-路由设计.md:68-75`).

Questions:

- Is a command such as a window enumeration or dismiss command allowed to run concurrently while the Skill channel is blocked?
- Who supplies the window id/display, and how is focus established deterministically?
- Can the upper layer implement the legacy save-dialog race as a sequence of `run_gui_command`s, or must automatic dialog handling be omitted?

### 9.6 One-shot Spectre commands, environment, and working directory

The legacy runner builds a `cwd`, sources cshrc, and executes Spectre with an explicit raw/log path (`runner.py:145-175,255-287,1048-1070`). The new `run_spectre_command` is a one-shot command with no persistent cwd/env and returns only `CommandResult`.

Questions:

- Should the upper layer always construct `cd <run_dir> && source <env> && exec <spectre> ...`, and how does it obtain `role.spectre.bin`?
- Does the Spectre role share the file role’s run directory? If not, how are netlists/includes/raw results transferred?
- How should `timeout=600` legacy behavior be translated to the middle default of 30 seconds? The upper package must pass an explicit larger timeout.

### 9.7 Spectre command-line parameters and output handling

The reference says `-param X=Y` is broken on Spectre 21.1 and recommends regenerating netlists (`skills/spectre/SKILL.md:63-80`). Examples already do template/regex substitution (`examples/02_spectre/05_parallel_sweep.py:70-76,145-155`). Binary PSF is unsupported (`SKILL.md:229-239`), `.measure` is unsupported by the scoped parser, and `spectre.out` is downloaded but not tailed during the run.

Questions:

- Does the new upper layer own template parameterization, or should callers provide fully materialized `.scs` files?
- Is PSF ASCII mandatory, and how should binary PSF be represented?
- Should `.measure` be a separate business result format or remain out of scope?
- What is the canonical log/terminal marker for success/failure on each supported Spectre version?

### 9.8 How should Maestro/Explorer/ASI version fallback be modeled?

The legacy package is predominantly `mae*`, but the reference documents `asi*` fallback and `sevRun` for ADE Explorer (`maestro-skill-api.md:36-68`), and `run_and_wait`’s error message explicitly tells the user to use `sevRun` for Explorer (`writer.py:565-570`). There is no central capability detector in the scoped source.

Questions:

- Is Explorer in scope for the new upper package?
- Should the package detect `fboundp('maeRunSimulation)`/`sevSession(window)` and branch, or expose separate Assembler/Explorer APIs?
- Which Virtuoso/IC versions must be supported for `maeExportOutputView`, `maeGetOverallSpecStatus`, `maeGetOverallYield`, and `maeOpenResults`?

### 9.9 SKILL string escaping and injection safety

Only `add_output`, `run_simulation`, and waveform-viewer builders use `escape_skill_string`; many writer functions interpolate names, values, paths, and sessions directly (`writer.py:76-87,123-129,349-354`; waveform `waveform_viewer.py:65-80`). Tests pin escaping for `add_output`, `run_simulation`, and waveform viewer, but not for all writer APIs (`test_maestro_writer.py:46-75`; `test_maestro_waveform_viewer.py:63-81`).

Questions:

- Are all Maestro identifiers/paths trusted by contract, or must the new upper layer centralize escaping for every SKILL-bound string?
- What validation is required for expressions such as OCEAN expressions, model files, and corner values?
- Should escaping reject control characters rather than merely backslash-escape them?

### 9.10 Concurrency, cancellation, and retry semantics

Legacy `run_parallel` and `SpectrePool` use private `ThreadPoolExecutor`s (`runner.py:514-580,833-871`), while the new middle layer owns per-token thread/channel budgets and may reject capacity (`1-四层整体架构与接口.md:263,340-350`). `run_and_wait` retries once after a suspected modal dialog (`writer.py:541-551`), but the new result/error contract says Skill timeouts are “unknown effect” and must not be automatically retried (`1-四层整体架构与接口.md:277-279`).

Questions:

- What concurrency limit should the upper package expose, and how should it handle `CommandResult(kind="rejected")`?
- Which legacy single-retry paths are safe under the new “unknown effect” rule?
- How should cancellation be represented when `run_spectre_command`/`run_command` are synchronous one-shot calls?

### 9.11 Is `evas.netlist.runner` part of the target system?

The ADC/DAC examples use an external `evas_simulate` wrapper and `tran.csv` rather than the scoped `SpectreSimulator` (`analyze_adc_dac_ideal_4b.py:14-30`). The new architecture has no EVAS interface.

Questions:

- Should ADC/DAC EVAS behavior be redeveloped as a separate upper package over the five interfaces, or treated as an external tool outside this migration?
- If it is ported, what role owns EVAS execution and how are its CSV results transferred/parsed?

### 9.12 `read_results` and result-context concurrency

`read_results` calls `maeOpenResults`, `maeGetResultOutputs`, and `maeCloseResults` around history discovery (`runs.py:186-210`), while `export_waveform` also opens/closes OCEAN results (`runs.py:403-421`). These operations mutate a shared Cadence result context.

Questions:

- Does the new upper package serialize all result-reading operations per session?
- Can result reads run concurrently with waveform exports, or must they share a lock/queue?
- How should a stale results context after an error be reset deterministically?

### 9.13 Pnoise jitter-event support

The reference documents that the pnoise jitter-event table cannot be fully automated through SKILL; the workaround is to copy/edit `active.state` and reopen Maestro (`maestro-skill-api.md:449-503`). This requires file transfer plus a text replacement/generation step and is explicitly not implemented in `waveform_viewer.py:59-60`.

Questions:

- Is jitter-event authoring in scope for the new upper package?
- If yes, should it be a structured XML transform rather than the legacy `sed` workaround?
- Which role owns the source/destination `active.state`, and how is Maestro prevented from holding a stale in-memory copy?

### 9.14 Long-run completion and result validation

The legacy Maestro marker only proves that Cadence called the completion callback; it does not prove that simulation succeeded, that expected result files were written, or that all sweep points completed (`writer.py:522-575`). The standalone Spectre runner infers success after the process returns and parses whatever output directory exists (`runner.py:383-475`).

Questions:

- What is the canonical success predicate for a Maestro run: history name, `maeGetOverallSpecStatus`, result count, expected artifact set, or a combination?
- Should the new upper package always read results after `run_and_wait` before reporting business success?
- What polling interval/timeout defaults should replace the legacy 600-second Maestro and Spectre budgets?

### 9.15 Where should the upper package boundaries be drawn?

The scoped capability set spans four distinct business domains:

1. Maestro session/config editing;
2. Maestro simulation execution and result reading;
3. Spectre standalone simulation and result parsing;
4. waveform/result visualization and measurement.

Questions:

- Should these be one package or separate `maestro`, `spectre`, and `result_analysis` packages?
- Which parsed models belong in `src/pyapi/models.py` versus package-local dataclasses?
- Should `SimulationResult` be the common result type for Maestro and Spectre, or should Maestro return a richer setup/simulation result while Spectre uses `SimulationResult`?
- What compatibility period, if any, is required for the legacy `client.maestro.*` facade names?

---

## Appendix A. Practical porting checklist

| Area | Minimum functionality to reject regression |
|---|---|
| Maestro sessions | Background open/close; GUI open/reuse/close with save/discard; focused-window metadata; purge stale cellviews. |
| Maestro configuration | Test, analysis, outputs, specs, variables, parameters, env/sim options, corners, run/job modes, save/migration. |
| Maestro execution | Async run start, non-blocking completion wait, shared deadline, modal-dialog recovery, Explorer rejection/branching. |
| Maestro results | Latest-history selection, Detail CSV export/download/parse, per-point parameters/outputs/specs, overall spec/yield, raw CSV option. |
| Maestro snapshot | Raw and filtered `maestro.sdb`/`active.state`, raw SKILL sections, YAML whitelist, per-point netlist/PSF artifact selection, newest-history resolution. |
| Waveforms | OCEAN text export with format validation; signal fallback for viewer; explicit session/window cleanup. |
| Spectre execution | Mode args, netlist/include staging, local/remote command construction, timeout, raw/log retrieval, exit-code and fatal-output classification. |
| Spectre parallel | Fixed batch and incremental pool semantics, unique work dirs, submission-order results, failure-as-result behavior, capacity rejection handling. |
| Spectre parsing | PSF ASCII swept/non-swept, delta compression, NaN, complex phasors, struct flattening, directory aggregation, both sweep layouts. |
| Spectre results | CSV/JSON bundle, scalar/vector/frequency validation, delay/bandwidth/noise/power/FOM measurement patterns. |
| Safety/contracts | Structured result mapping, token use, no SSH/subprocess/socket/registry in upper layer, escaping, artifact cleanup, split-role path policy. |
