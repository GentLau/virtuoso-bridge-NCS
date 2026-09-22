# Legacy Schematic + Symbol Upper-Layer Inventory

**Scope analysed:** `src_bak/virtuoso_bridge/virtuoso/schematic/`, `src_bak/virtuoso_bridge/virtuoso/symbol/`, the requested legacy tests, and the schematic/symbol examples. Read-only exploration; the only file written is this report.

**Classification baseline:** new upper-layer packages may call only `execute_skill`, `run_command`, `upload_file`, `download_file`, `run_gui_command`, and `run_spectre_command` (five roles: Skill, command, file, GUI, Spectre), as specified in `spec/design-concepts/总览/1-四层整体架构与接口.md:183-187` and `spec/design-concepts/中层/3-路由设计.md`. This report deliberately calls out every legacy dependency that violates, or needs adaptation for, that boundary.

---

## 1. Module inventory

Line counts below are physical lines (`newline count + 1`). “Public” in this table means exported by the module `__all__` or directly used by the scoped examples/tests; it does not imply semver stability.

### 1.1 Schematic production modules

| Legacy file | Lines | One-line purpose |
|---|---:|---|
| `src_bak/virtuoso_bridge/virtuoso/schematic/__init__.py` | 276 | Package facade and `client.schematic` proxy; exposes the importer, reader, netlist, planner, and SKILL-operation surface. |
| `src_bak/virtuoso_bridge/virtuoso/schematic/editor.py` | 78 | Context manager that opens a schematic, accumulates SKILL commands, runs `schCheck`, saves, and executes the batch. |
| `src_bak/virtuoso_bridge/virtuoso/schematic/ops.py` | 520 | Pure SKILL-string builders for instances, wires, labels, pins, inherited connections, terminal stubs, and checks. |
| `src_bak/virtuoso_bridge/virtuoso/schematic/reader.py` | 589 | Unified topology/geometry/parameter reader plus three legacy readers; embeds a large one-call SKILL extractor and Python line parser. |
| `src_bak/virtuoso_bridge/virtuoso/schematic/planner.py` | 992 | Pure-Python deterministic placement/constraint planner, plan application to an editor, and readback verifier. |
| `src_bak/virtuoso_bridge/virtuoso/schematic/netlist.py` | 886 | Netlist export/import orchestration, generated SKILL, `spiceIn` staging, local/remote command execution, and result/log parsers. |
| `src_bak/virtuoso_bridge/virtuoso/schematic/params.py` | 236 | Reads active schematic/instance masters, filters CDF parameters, and applies parameter callbacks through one generated SKILL program. |
| `src_bak/virtuoso_bridge/virtuoso/schematic/cdf_param_filters.yaml` | 73 | Default lib/cell-to-CDF-parameter allowlist used by the reader and `set_instance_params`. |

### 1.2 Symbol production modules

| Legacy file | Lines | One-line purpose |
|---|---:|---|
| `src_bak/virtuoso_bridge/virtuoso/symbol/__init__.py` | 175 | Package facade and `client.symbol` proxy; exposes manual drawing, generation, and readback APIs. |
| `src_bak/virtuoso_bridge/virtuoso/symbol/editor.py` | 59 | Context manager that opens a symbol cellview, accumulates commands, checks the pin list, saves, and executes the batch. |
| `src_bak/virtuoso_bridge/virtuoso/symbol/ops.py` | 328 | SKILL-string builders for symbol geometry, semantic labels, pins/terminals, ordering, and symbol checks. |
| `src_bak/virtuoso_bridge/virtuoso/symbol/generator.py` | 403 | Wraps Cadence TSG (`schSchemToPinList`/`schPinListToSymbol`) with temp-view verification, replacement backup, rollback, cleanup, and result parsing. |
| `src_bak/virtuoso_bridge/virtuoso/symbol/reader.py` | 271 | Builds/parses a structured SKILL readback of terminals, labels, port/pin/term order, bounding boxes, and selection boxes. |

### 1.3 Requested tests documenting behavior

| Test file | Lines | Behavior documented |
|---|---:|---|
| `test_bak/test_schematic_ops.py` | 132 | Exact generated SKILL for net expressions, inherited overrides, stubs, label binding, escaping, and validation. |
| `test_bak/test_schematic_planner.py` | 373 | Deterministic placement, hard/soft constraint behavior, collisions, readback conversion/verification, and plan application. |
| `test_bak/test_schematic_reader.py` | 272 | Reader error paths, timeout forwarding, named-vs-current cellview ownership, cleanup errors, incomplete targets, and unified delegation. |
| `test_bak/test_schematic_netlist.py` | 835 | OCEAN export SKILL, recursive download/replacement safety, `spiceIn` staging, local/remote execution, imports, and failure handling. |
| `test_bak/test_symbol_generator.py` | 633 | TSG generation result, pin-order handling, overwrite/rollback semantics, cleanup failures, and strict response parsing. |
| `test_bak/test_symbol_ops.py` | 253 | Exact symbol geometry/label/pin SKILL, editor lifecycle/error handling, and `client.symbol` exposure. |
| `test_bak/test_symbol_reader.py` | 304 | Structured S-expression parsing, semantic-label fields, validation failures, custom view types, and transport response normalization. |

### 1.4 Examples documenting intended usage

| Example | Lines | Business use demonstrated |
|---|---:|---|
| `examples/01_virtuoso/schematic/01a_create_rc_stepwise.py` | 96 | Stepwise RC schematic creation, terminal labels, VDC update, and window opening. |
| `examples/01_virtuoso/schematic/01b_create_rc_load_skill.py` | 88 | Same RC flow through the batch editor helper. |
| `examples/01_virtuoso/schematic/02_read_connectivity.py` | 70 | Legacy topology-only connectivity read. |
| `examples/01_virtuoso/schematic/03_read_instance_params.py` | 54 | Legacy per-instance CDF parameter read with optional parameter filter. |
| `examples/01_virtuoso/schematic/04_test_set_instance_params_analoglib.py` | 117 | CDF parameter updates for analogLib cells, strict filtering, and readback verification. |
| `examples/01_virtuoso/schematic/05_rename_instance.py` | 49 | Raw-SKILL instance rename in the active schematic. |
| `examples/01_virtuoso/schematic/06_delete_instance.py` | 60 | Raw-SKILL instance deletion. |
| `examples/01_virtuoso/schematic/07_delete_cell.py` | 44 | Raw-SKILL active-cell close/delete. |
| `examples/01_virtuoso/schematic/08_import_cdl_cap_array.py` | 223 | CDL import via SSH/`spiceIn`, DB verification, and symbol generation. |
| `examples/01_virtuoso/schematic/09_create_pins.py` | 75 | Explicit-position and instance-terminal pin creation. |
| `examples/01_virtuoso/schematic/10_create_wire.py` | 170 | Polyline wires, terminal-to-terminal wires, clean labels, branch labels, and pins. |
| `examples/01_virtuoso/schematic/11_read_schematic_unified.py` | 113 | Unified topology/position/CDF-parameter/notes readback. |
| `examples/01_virtuoso/schematic/12_plan_differential_pair.py` | 94 | Planner inputs, deterministic application, and readback verification. |
| `examples/01_virtuoso/symbol/01_rc_create_with_symbol.py` | 120 | Schematic creation followed by TSG symbol generation and view verification. |
| `examples/01_virtuoso/symbol/02_bus10_create_with_symbol.py` | 123 | 20-pin symbol generation with geometric pin ordering. |
| `examples/01_virtuoso/symbol/03_manual_symbol_semantics.py` | 83 | Manual symbol geometry and native pin/instance/logical label semantics. |

---

## 2. Public API surface

### 2.1 Package-facade exports

`src_bak/virtuoso_bridge/virtuoso/schematic/__init__.py:232-275` exports `SchematicOps`, `SchematicEditor`, all schematic operation builders, all netlist helpers listed below, and the complete planner model. `src_bak/virtuoso_bridge/virtuoso/symbol/__init__.py:151-174` exports `SymbolOps`, `SymbolEditor`, generation types/helpers, all symbol operation builders, and symbol readback helpers.

Important distinction: `reader.py` and `params.py` are not re-exported from `schematic/__init__.py`; nevertheless, examples import them directly (`examples/01_virtuoso/schematic/02_read_connectivity.py:15`, `examples/01_virtuoso/schematic/03_read_instance_params.py:16`, `examples/01_virtuoso/schematic/04_test_set_instance_params_analoglib.py:24`). They are therefore part of the observed legacy feature surface even though the package facade omits them.

### 2.2 `SchematicOps` — the `client.schematic` facade

Defined at `src_bak/virtuoso_bridge/virtuoso/schematic/__init__.py:68-229`.

| Entry point | Exact signature | Return |
|---|---|---|
| constructor | `__init__(self, owner: VirtuosoClient) -> None` | Stores concrete client in `self._owner`. |
| create | `create(self, lib: str, cell: str, view: str = "schematic", timeout: int = 60) -> SchematicEditor` | Context-manager editor opened in destructive mode `"w"`. |
| modify | `modify(self, lib: str, cell: str, view: str = "schematic", timeout: int = 60) -> SchematicEditor` | Context-manager editor opened in append mode `"a"`. |
| edit (deprecated) | `edit(self, lib: str, cell: str, view: str = "schematic", mode: Literal["a", "w"] = "a", timeout: int = 60) -> SchematicEditor` | Compatibility wrapper; emits `DeprecationWarning`. |
| read | `read(self, lib: str \| None = None, cell: str \| None = None, *, include_positions: bool = False, param_filters: str \| Path \| None \| _UseReaderDefault = _USE_READER_DEFAULT, timeout: int = 300) -> dict[str, Any]` | Unified schematic dictionary; sentinel preserves the standalone reader's default filter. |
| plan | `plan(self, request: SchematicPlanRequest, *, config: SchematicPlannerConfig \| None = None) -> SchematicPlan` | Pure-Python `SchematicPlan`. |
| create_from_plan | `create_from_plan(self, lib: str, cell: str, plan: SchematicPlan, *, view: str = "schematic", timeout: int = 60) -> None` | Creates/overwrites the cellview and applies the plan through `SchematicEditor`. |
| export_netlist | `export_netlist(self, lib: str, cell: str, output_dir: str \| Path, *, view: str = "schematic", simulator: str = "spectre", recreate_all: bool = True, timeout: int = 120) -> SchematicNetlistExportResult` | Typed dictionary described in §2.7. |
| import_netlist | `import_netlist(self, lib: str, cell: str, netlist_file: str \| Path, *, language: str = "Spectre", sim_name: str = "spectre", output_sim_name: str = "spectre", ref_libs: list[str] \| tuple[str, ...] = ("analogLib", "basic"), netlist_view: str = "netlist", schematic_view: str = "schematic", overwrite: bool = False, dev_map_file: str \| Path \| None = None, run_dir: str \| Path \| None = None, timeout: int = 300) -> Any` | Legacy type annotation is `Any`; implementation returns the final SKILL conversion result, not `NetlistImportResult` (`netlist.py:398-409`). |

### 2.3 `SchematicEditor`

Defined at `src_bak/virtuoso_bridge/virtuoso/schematic/editor.py:31-76`.

- `__init__(self, client: VirtuosoClient, lib: str, cell: str, view: str = "schematic", mode: str = "a", timeout: int = 60) -> None`
- `__enter__(self) -> SchematicEditor`: appends the `dbOpenCellViewByType(...)` statement generated by `open_cell_view` (`editor.py:51-53`).
- `add(self, skill_cmd: str) -> None`: appends one already-built SKILL command (`editor.py:55-57`).
- `add_net_label_to_transistor(self, instance_name: str, drain_net: str | None = None, gate_net: str | None = None, source_net: str | None = None, body_net: str | None = None) -> None`: appends only non-`None` labels for `D/G/S/B` (`editor.py:59-70`).
- `__exit__(self, exc_type, exc_val, exc_tb) -> None`: with no body exception, appends `schCheck()`, appends `save_current_cellview()`, calls legacy `client.execute_operations(...)`, then normalizes the old response via `ensure_operation_response` (`editor.py:72-77`).

The editor has no explicit returned result: success is silent, failure raises `RuntimeError`.

### 2.4 Schematic SKILL operation builders (`schematic/ops.py`)

All return a SKILL expression as `str`; they are pure string builders and do not call Virtuoso themselves.

- `schematic_create_inst(master_expr: str, instance_name: str, x: float, y: float, orientation: str, *, cv_expr: str = "cv") -> str` (`ops.py:14-28`)
- `schematic_create_inst_by_master_name(lib: str, cell: str, view: str, instance_name: str, x: float, y: float, orientation: str, *, cv_expr: str = "cv", view_type: str | None = None, mode: str = "r") -> str` (`ops.py:30-65`)
- `schematic_create_wire(points: Iterable[tuple[float, float]], *, cv_expr: str = "cv", route_style: str = "route", route_mode: str = "full") -> str` (`ops.py:67-78`)
- `schematic_create_wire_label(x: float, y: float, text: str, justification: str, rotation: str, *, cv_expr: str = "cv", style: str = "stick", height: float = 0.0625) -> str` (`ops.py:80-98`)
- `schematic_create_net_stub(net_name: str, x: float, y: float, *, direction: str = "right", length: float = 0.5, cv_expr: str = "cv", route_style: str = "route", route_mode: str = "full", justification: str = "centerCenter", rotation: str | None = None, style: str = "stick", height: float = 0.0625) -> str` (`ops.py:109-147`). Valid directions are `up/down/left/right`; length must be positive.
- `schematic_create_net_expression(net_name: str, net_expression: str, x: float, y: float, *, cv_expr: str = "cv", justification: str = "lowerLeft", rotation: str = "R0", font_style: str = "stick", height: float = 0.0625) -> str` (`ops.py:150-182`)
- `schematic_set_netset_property(instance_name: str, property_name: str, net_name: str, *, cv_expr: str = "cv") -> str` (`ops.py:184-198`)
- `schematic_label_instance_term(instance_name: str, term_name: str, net_name: str, *, cv_expr: str = "cv", justification: str | None = None, rotation: str = "R0", style: str = "stick", height: float = 0.0625, extension_length: float | None = None, cosmetic: str = "default", auto_rotation: bool = False, bind_label_to_wire: bool = False) -> str` (`ops.py:282-366`). `cosmetic="clean"` changes defaults to `0.5`/`lowerCenter`.
- `schematic_label_instance_term_offset(instance_name: str, term_name: str, net_name: str, *, cv_expr: str = "cv", justification: str = "centerLeft", rotation: str = "R0", style: str = "stick", height: float = 0.0625, extension_length: float = 0.5, branch_length: float = 0.25, branch_direction: str = "up", auto_rotation: bool = False) -> str` (`ops.py:377-454`); validates `branch_direction`.
- `schematic_create_pin(pin_name: str, x: float, y: float, orientation: str, *, cv_expr: str = "cv", direction: str = "inputOutput") -> str` (`ops.py:462-476`); maps direction to `basic/ipin`, `basic/opin`, or `basic/iopin`.
- `schematic_create_pin_at_instance_term(instance_name: str, term_name: str, pin_name: str, *, cv_expr: str = "cv", direction: str = "inputOutput", orientation: str = "R0") -> str` (`ops.py:478-495`)
- `schematic_create_wire_between_instance_terms(from_instance: str, from_term: str, to_instance: str, to_term: str, *, cv_expr: str = "cv", route_style: str = "route", route_mode: str = "full") -> str` (`ops.py:497-515`)
- `schematic_check(*, cv_expr: str = "cv") -> str` (`ops.py:517-519`)

### 2.5 Schematic readers (`schematic/reader.py`)

#### Unified reader

`read_schematic(client: VirtuosoClient, lib: str | None = None, cell: str | None = None, *, include_positions: bool = False, param_filters: str | Path | None = <module default YAML>, timeout: int = 300) -> dict` (`reader.py:181-234`).

Return shape (`reader.py:244-357`):

```text
{
  "instances": [
    {
      "name": str, "lib": str, "cell": str,
      "params": dict[str, str],
      "terms": dict[str, str],
      # only when include_positions=True:
      "xy": [float, float], "orient": str,
      "bBox": [[float, float], [float, float]],
      "numInst": int, "view": str,
      # optional:
      "nlAction": str
    }, ...
  ],
  "nets": {
    str: {
      "connections": list[str],       # "instance.terminal"
      "numBits": int,
      "sigType": str,                  # default "signal"
      "isGlobal": bool
    }, ...
  },
  "pins": {
    str: {"direction": str, "numBits": int}, ...
  },
  "notes": [
    {"text": str,
     # only when include_positions=True:
     "xy": [float, float] | None, "font": str,
     "height": float, "orient": str, "justify": str}
  ]
}
```

Named `lib/cell` reads open an owned read-only cellview and close it under `unwindProtect`; the no-argument form reads `geGetEditCellView()` and does not close it (`reader.py:127-151`, tests at `test_bak/test_schematic_reader.py:42-82`).

#### Legacy readers, retained for compatibility

- `read_placement(client, lib=None, cell=None) -> dict` (`reader.py:416-458`) returns:
  `{"instances": [{"name": str, "lib": str, "cell": str, "xy": str, "orient": str}], "pins": [{"name": str, "direction": str}], "labels": [{"text": str, "xy": str}], "wires": [str]}`. Unlike the unified reader, positions/wires/labels are raw strings.
- `read_connectivity(client, lib=None, cell=None) -> dict` (`reader.py:486-527`) returns:
  `{"instances": [{"name", "lib", "cell"}], "nets": [{"name", "connections": list[str]}], "pins": [{"name", "direction"}]}`.
- `read_instance_params(client, lib=None, cell=None, filter_params: list[str] | None = None) -> list[dict]` (`reader.py:554-588`) returns one record per instance:
  `{"name": str, "lib": str, "cell": str, "params": dict[str, str]}`. `filter_params=None` means all parameters.

### 2.6 Schematic parameter setter (`schematic/params.py`)

`set_instance_params(client, inst_name: str, *, w: str | None = None, wf: str | None = None, l: str | None = None, nf: str | None = None, m: str | None = None, param_filters: str | Path | None = <bundled YAML>, strict: bool = False, **kwargs: str) -> dict[str, str]` (`params.py:161-235`).

Business behavior:

1. Rejects simultaneous `w` and `wf` (`params.py:193-194`).
2. Maps `wf -> Wfg` and `nf -> fingers`; passes `w/l/m` and arbitrary `**kwargs` through (`params.py:196-207`, constants at `params.py:38-41`).
3. Resolves the currently active schematic via `geGetEditCellView()` (`params.py:90-102`).
4. Resolves the instance's master lib/cell via read-only SKILL (`params.py:105-123`).
5. Matches the instance against YAML filters; rejects/strict-raises or warns/drops disallowed parameters (`params.py:214-228`).
6. Applies allowed values in one SKILL program that invokes CDF callbacks, calls `cdfUpdateInstParam`, `schCheck`, and `dbSave` (`params.py:43-70`, `126-158`).
7. Returns the parameters actually submitted after filtering, not a fresh readback (`params.py:229-235`).

### 2.7 Netlist export/import API (`schematic/netlist.py`)

#### SKILL builders

- `schematic_export_netlist_skill(lib: str, cell: str, *, view: str = "schematic", simulator: str = "spectre", recreate_all: bool = True) -> str` (`netlist.py:123-159`). Emits OCEAN calls `simulator(...)`, `design(...)`, optional `ddsRefresh`, `createNetlist(?recreateAll ... ?display nil)`, and `simplifyFilename(...)`; `simulator` must be a simple SKILL symbol (`netlist.py:39-42`).
- `schematic_import_netlist_skill(lib: str, cell: str, *, netlist_view: str = "netlist", schematic_view: str = "schematic", overwrite: bool = False, param_file: str | Path = "", spicein_log_file: str | Path = "") -> str` (`netlist.py:245-321`). It only performs database conversion through `conn2Sch` and `dbCopyCellView`; it deliberately does not invoke `spiceIn` or `system()` (`netlist.py:255-260`, tests at `test_bak/test_schematic_netlist.py:155-176`).

#### Export orchestrator

`export_schematic_netlist(client, lib: str, cell: str, output_dir: str | Path, *, view: str = "schematic", simulator: str = "spectre", recreate_all: bool = True, timeout: int = 120) -> SchematicNetlistExportResult` (`netlist.py:162-242`).

`SchematicNetlistExportResult` is a `TypedDict` with exact keys (`netlist.py:24-32`):

```text
{
  "source_file": str,       # returned remote input.scs path
  "source_dir": str,        # remote containing directory
  "output_dir": str,        # local installed directory
  "input_file": str,        # local output_dir/input.scs
  "skill_result": Any,      # original SKILL result object/dict
  "download_result": Any    # original download result, output rewritten to destination
}
```

Substeps: execute the generated netlisting SKILL; derive an absolute POSIX `source_dir`; recursively download to a temporary sibling directory; require `input.scs`; atomically replace the existing destination preserving it until the new package is complete (`netlist.py:193-242`).

#### Import orchestrator

`import_netlist_schematic(client, lib: str, cell: str, netlist_file: str | Path, *, language: str = "Spectre", sim_name: str = "spectre", output_sim_name: str = "spectre", ref_libs: list[str] | tuple[str, ...] = ("analogLib", "basic"), netlist_view: str = "netlist", schematic_view: str = "schematic", overwrite: bool = False, dev_map_file: str | Path | None = None, run_dir: str | Path | None = None, timeout: int = 300) -> Any` (`netlist.py:324-409`). The current implementation returns the final SKILL result from `conn2Sch` conversion (`netlist.py:398-409`).

Substeps:

1. Discover working directory, `PATH`, `LD_LIBRARY_PATH`, license variables, and Cadence install directory through SKILL (`netlist.py:514-528`, `_context_value` at `531-532`).
2. Resolve a run directory; if omitted, default to `/tmp/virtuoso_bridge_netlist_import_<sanitized-lib>_<sanitized-cell>_<uuid>/` (`netlist.py:674-685`).
3. Run a SKILL preflight that rejects equal views and existing targets unless overwrite is enabled (`netlist.py:486-511`).
4. Choose a local or remote execution path based on `getattr(client, "ssh_runner", None)` (`netlist.py:362-396`).
5. Stage/write `spiceIn.il` and `cds.lib`; upload local inputs when needed; run `spiceIn -param <param_file>` (local `subprocess` or remote command runner) (`netlist.py:535-658`, `688-870`).
6. Run `schematic_import_netlist_skill(...)` to convert the imported netlist view to schematic (`netlist.py:398-409`).

#### Result/log parsers

- `NetlistImportResult` dataclass fields: `status: str`, `lib`, `cell`, `param_file`, `spicein_log_file`, `conn2sch_log_file`, `reason`, `netlist_file`, `netlist_view`, `schematic_view` (all optional strings except `status`) (`netlist.py:412-430`). `ok` is exactly `status == "imported"`.
- `parse_netlist_import_output(output: str) -> NetlistImportResult` accepts JSON or a single SKILL list beginning with `"imported"`; unknown/empty/malformed input yields `status="unknown"` plus a reason (`netlist.py:433-468`).
- `classify_netlist_import_log(text: str) -> list[str]` detects four coarse categories: missing master/device mapping, missing include/source netlist, pin mismatch, and syntax/parse error (`netlist.py:471-483`).

### 2.8 Planner and plan model (`schematic/planner.py`)

The planner is explicitly pure Python and only emits existing editor operations (`planner.py:1-5`).

#### Enums

- `ConstraintStrength`: `HARD = "hard"`, `SOFT = "soft"` (`planner.py:22-26`).
- `ConstraintLevel`: `RELAXED = "relaxed"`, `CONFLICT = "conflict"` (`planner.py:29-33`).
- `DeviceKind`: `NMOS = "nmos"`, `PMOS = "pmos"`, `OTHER = "other"` (`planner.py:36-41`).
- `infer_device_kind(cell: str) -> DeviceKind`: `pmos`/`pch` wins as PMOS, then `nmos`/`nch`, else OTHER (`planner.py:69-77`).

#### Input dataclasses

- `SchematicInstanceSpec(name, lib, cell, terminals={}, view="symbol", kind=None, orientation=None, output_stage=False)` (`planner.py:80-121`). Validates non-empty names; infers/normalizes `kind`; uppercases MOS terminal names `D/G/S/B`.
- `SchematicPinSpec(name, direction="inputOutput", row=None, orientation="R0")` (`planner.py:124-140`).
- `GridPositionConstraint(instance, col=None, row=None, strength=ConstraintStrength.HARD)` (`planner.py:143-164`); requires at least one of `col`/`row`.
- `DifferentialPairConstraint(left, right, row=None, center_col=1.5, separation=1.0, strength=ConstraintStrength.HARD)` (`planner.py:167-190`); requires different names and positive separation.
- `SchematicPlannerConfig(grid_spacing=1.5, nmos_row=0.0, other_row=1.0, pmos_row=2.0, pin_column=-1.0, output_column=5.0, output_column_step=1.0)` (`planner.py:193-220`); positive/finite validation.

#### Request and result dataclasses

- `SchematicPlanRequest(instances, pins=(), positions=(), differential_pairs=())` (`planner.py:246-259`).
- Class method `SchematicPlanRequest.from_readback(cls, schematic, *, grid_spacing=1.5, strength=ConstraintStrength.HARD, differential_pairs=(), output_instances=())` (`planner.py:261-330`). It requires `xy` on every instance; converts absolute `xy` to grid `col/row`; preserves orientation and terminal nets; assigns pins in sorted-name order with rows `0..n-1`.
- `ConstraintDiagnostic(level, code, message, subjects=())` (`planner.py:223-230`).
- `SchematicPlanningError(diagnostics)` (`planner.py:233-243`); exposes `.diagnostics` and composes conflict messages into the exception text.
- `GridPlacement(col, row, x, y, orientation)` (`planner.py:333-341`).
- `PlannedInstance(spec, placement)` (`planner.py:344-347`).
- `PlannedPin(name, direction, col, row, x, y, orientation)` (`planner.py:350-358`).
- `ReadbackMismatch(code, subject, expected, actual)` with `__str__` (`planner.py:361-372`).
- `SchematicReadbackReport(mismatches)` with `ok` and `require_valid()` (`planner.py:375-390`).
- `SchematicPlan(instances, pins, diagnostics, grid_spacing)` (`planner.py:393-541`) with:
  - `instance(self, name: str) -> PlannedInstance` (`planner.py:402-406`);
  - `apply(self, editor: Any) -> None` (`planner.py:408-451`);
  - `verify_readback(self, schematic: Mapping[str, Any], *, tolerance: float = 1e-6) -> SchematicReadbackReport` (`planner.py:453-541`).

`apply` emits instance creation, labels MOS terminals through `editor.add_net_label_to_transistor`, labels other terminals individually, and creates planned pins. It does **not** synthesize connectivity or route wires (`planner.py:408-451`). `verify_readback` checks expected instance existence/lib/cell/position/orientation/term-net maps, unexpected instances, expected/unexpected pins, and pin direction (`planner.py:463-541`).

#### Planner engine

`SchematicPlanner.__init__(self, config: SchematicPlannerConfig | None = None) -> None` (`planner.py:561-562`) and `plan(self, request: SchematicPlanRequest) -> SchematicPlan` (`planner.py:564-848`).

The algorithm deterministically validates duplicate/unknown constraints, sorts constraints, assigns polarity rows and core/output columns, applies explicit positions and differential-pair rules with hard/soft precedence, resolves grid collisions, verifies pair results, and converts grid coordinates to absolute `x/y` using `grid_spacing` (`planner.py:564-848`).

### 2.9 `SymbolOps` — the `client.symbol` facade

Defined at `src_bak/virtuoso_bridge/virtuoso/symbol/__init__.py:40-148`.

- `__init__(self, owner: VirtuosoClient) -> None`
- `create(self, lib: str, cell: str, view: str = "symbol", view_type: str = "schematicSymbol", timeout: int = 60) -> SymbolEditor`
- `modify(self, lib: str, cell: str, view: str = "symbol", view_type: str = "schematicSymbol", timeout: int = 60) -> SymbolEditor`
- `edit(self, lib: str, cell: str, view: str = "symbol", view_type: str = "schematicSymbol", mode: str = "a", timeout: int = 60) -> SymbolEditor` — deprecated warning.
- `generate_from_schematic(self, lib: str, cell: str, *, schematic_view: str = "schematic", symbol_view: str = "symbol", sort_pins: SymbolPinSort | None = None, overwrite: bool = False, timeout: int = 60) -> SymbolGenerationResult`
- `read_ports(self, lib: str, cell: str, view: str = "symbol", view_type: str = "schematicSymbol", timeout: int = 30) -> dict[str, Any]`

### 2.10 `SymbolEditor`

Defined at `src_bak/virtuoso_bridge/virtuoso/symbol/editor.py:15-58`: constructor stores client/lib/cell/view/view_type/mode/timeout; `__enter__` adds `open_cell_view(...)`; `add(skill_cmd)` appends; `__exit__` adds `symbol_check()` and `save_current_cellview()` and calls legacy `client.execute_operations(...)`, raising through `ensure_operation_response` on failure.

### 2.11 Symbol SKILL operation builders (`symbol/ops.py`)

- `symbol_create_line(layer: str, purpose: str, points: Iterable[tuple[float, float]], *, cv_expr: str = "cv") -> str` (`ops.py:30-38`)
- `symbol_create_rect(layer: str, purpose: str, x0: float, y0: float, x1: float, y1: float, *, cv_expr: str = "cv") -> str` (`ops.py:41-52`)
- `symbol_create_polygon(layer: str, purpose: str, points: Iterable[tuple[float, float]], *, cv_expr: str = "cv") -> str` (`ops.py:55-63`)
- `symbol_create_ellipse(layer: str, purpose: str, x0: float, y0: float, x1: float, y1: float, *, cv_expr: str = "cv") -> str` (`ops.py:66-77`)
- `symbol_create_label(layer: str, purpose: str, x: float, y: float, text: str, justification: str, rotation: str, font: str, height: float, *, cv_expr: str = "cv", label_type: str | None = None) -> str` (`ops.py:80-113`)
- `symbol_create_pin_name(pin_name: str, x: float, y: float, *, justification: str = "centerLeft", rotation: str = "R0", font: str = "stick", height: float = 0.0625, cv_expr: str = "cv") -> str` (`ops.py:147-170`)
- `symbol_create_instance_label(x: float, y: float, *, text: str = "[@instanceName]", justification: str = "centerLeft", rotation: str = "R0", font: str = "stick", height: float = 0.0625, cv_expr: str = "cv") -> str` (`ops.py:173-196`)
- `symbol_create_logical_label(x: float, y: float, *, text: str = "[@partName]", justification: str = "centerCenter", rotation: str = "R0", font: str = "stick", height: float = 0.0625, cv_expr: str = "cv") -> str` (`ops.py:199-222`)
- `symbol_create_selection_box(x0: float, y0: float, x1: float, y1: float, *, cv_expr: str = "cv") -> str` (`ops.py:225-240`)
- `symbol_create_pin(pin_name: str, x: float, y: float, *, direction: str = "inputOutput", half_size: float = 0.0625, cv_expr: str = "cv", label: bool = True, label_x: float | None = None, label_y: float | None = None, label_justification: str = "centerLeft", label_rotation: str = "R0", label_font: str = "stick", label_height: float = 0.0625) -> str` (`ops.py:243-308`)
- `symbol_set_term_order(term_names: Iterable[str], *, cv_expr: str = "cv") -> str` (`ops.py:311-313`)
- `symbol_check(*, cv_expr: str = "cv") -> str` (`ops.py:316-326`), using `schSymbolToPinList(...)`, not `schCheck`.

### 2.12 Symbol generation

- `symbol_generate_from_schematic_skill(lib: str, cell: str, *, schematic_view: str = "schematic", symbol_view: str = "symbol", sort_pins: SymbolPinSort | None = None, overwrite: bool = False) -> str` (`generator.py:47-256`). `SymbolPinSort` is `Literal["alphanumeric", "geometric"]` (`generator.py:17-20`).
- `generate_symbol_from_schematic(client: Any, lib: str, cell: str, *, schematic_view: str = "schematic", symbol_view: str = "symbol", sort_pins: SymbolPinSort | None = None, overwrite: bool = False, timeout: int = 60) -> SymbolGenerationResult` (`generator.py:259-309`).
- `SymbolGenerationResult` fields (`generator.py:34-44`): `lib: str`, `cell: str`, `schematic_view: str`, `symbol_view: str`, `action: Literal["created","replaced"]`, `terminal_names: tuple[str, ...]`, `pin_order: tuple[str, ...]`.
- `SymbolGenerationAction = Literal["created", "replaced"]` (`generator.py:18`).

Generation behavior is one SKILL round-trip: collect source terminal names/directions/widths and `schGetPinOrder`; generate into a temporary symbol view; verify terminals/order; optionally back up an existing target; copy into place; verify installed terminals/order; close/delete temp objects; roll back and retain a backup on failure (`generator.py:94-256`). Python validates sort mode, sends the SKILL, parses the structured protocol, verifies parsed pin-order/terminal-set equality, and raises on malformed output (`generator.py:288-309`, `312-393`).

### 2.13 Symbol readers (`symbol/reader.py`)

- `symbol_read_ports_skill(lib: str, cell: str, *, view: str = "symbol", view_type: str = "schematicSymbol") -> str` (`reader.py:21-88`).
- `parse_symbol_ports_output(output: str) -> dict[str, Any]` (`reader.py:91-154`).
- `read_symbol_ports(client: Any, lib: str, cell: str, *, view: str = "symbol", view_type: str = "schematicSymbol", timeout: int = 30) -> dict[str, Any]` (`reader.py:157-187`).

Return shape (`reader.py:105-154`):

```text
{
  "terms": [
    {"name": str, "direction": str, "numBits": int,
     "bbox": [[float,float],[float,float]] | None}
  ],
  "labels": [
    {"text": str, "labelType": str, "xy": [float,float] | None,
     # when the full 11-field record is present:
     "layerName": str, "purpose": str, "justify": str, "orient": str,
     "font": str, "height": float,
     "bbox": [[float,float],[float,float]] | None}
  ],
  "pinOrder": [str, ...],
  "portOrder": [str, ...],
  "termOrder": [str, ...],
  "selectionBoxes": [bbox, ...]
}
```

The parser accepts only one complete top-level SKILL list and rejects legacy TSV, malformed `readFailed`, trailing data, and incomplete records (`reader.py:91-102`, `190-212`; tests at `test_bak/test_symbol_reader.py:44-82`).

---

## 3. Capability decomposition

Each capability below is written as a redevelopment target: business inputs, outputs, substeps, and the middle interfaces required.

### C1. Schematic cellview lifecycle and batch edit

| Field | Decomposition |
|---|---|
| Business inputs | `lib`, `cell`, `view`, mode (`create` vs append), optional timeout, ordered edit commands. |
| Business outputs | A created/modified schematic cellview; success/failure; old code returns an `SchematicEditor` object and succeeds silently. |
| Substeps | Build `dbOpenCellViewByType(...)` with mode `w`/`a`; append commands; append `schCheck`; append `dbSave`; execute as one batch; normalize old response. |
| Middle interfaces | `execute_skill` only. The legacy `execute_operations` batch method is not one of the five interfaces; upper code must compose a `progn`/batch and call `execute_skill` itself. |
| Legacy references | `schematic/__init__.py:74-116`; `schematic/editor.py:34-77`; shared builder `virtuoso/ops.py:42-58`, `95-101`; operation response normalization `virtuoso/editor.py:10-24`. |

### C2. Schematic instance, wire, label, pin, and inherited-connection operations

| Field | Decomposition |
|---|---|
| Business inputs | Master identity or master expression; instance name/position/orientation; point lists; terminal names; net names; wire-label style/justification/rotation/height; pin name/direction/orientation; inherited net expression/property. |
| Business outputs | SKILL expressions that create database objects; when executed, instances, wires, labels, pins, nets, and properties in the schematic. |
| Substeps | Validate a few local arguments (`net_stub` direction/length, offset branch direction); escape strings; format points and layer-purpose pairs; select the SKILL constructors; optionally wrap in `let`/`progn` with object lookup/error checks. |
| Middle interfaces | `execute_skill` for execution. The operation builders themselves need no middle interface because they are pure string transforms. |
| Legacy references | `schematic/ops.py:14-519`; examples `09_create_pins.py:33-49`, `10_create_wire.py:88-143`; tests `test_schematic_ops.py:13-130`. |

### C3. CDF instance parameter set/get

| Field | Decomposition |
|---|---|
| Business inputs | Instance name; shorthand `w/wf/l/nf/m`; arbitrary CDF parameter keyword values; filter YAML path or `None`; `strict`; optional active schematic context. |
| Business outputs | Dictionary of parameters actually submitted after filtering; warnings or `ValueError` for rejected params. Readback separately returns `{"name","lib","cell","params"}` records. |
| Substeps | Resolve active schematic; resolve instance master; load/match YAML allowlist; map `wf -> Wfg`, `nf -> fingers`; build parameter table; open the cellview; set CDF values; invoke callbacks; call `cdfUpdateInstParam`; `schCheck`; `dbSave`. |
| Middle interfaces | `execute_skill` for active-cellview/master resolution and the update. Local YAML loading is pure Python but the asset must be packaged or mapped to an upper-layer resource. |
| Legacy references | `schematic/params.py:43-70`, `74-123`, `126-235`; `cdf_param_filters.yaml:1-72`; example `04_test_set_instance_params_analoglib.py:43-80`. |

### C4. Schematic unified readback

| Field | Decomposition |
|---|---|
| Business inputs | Optional `lib/cell` (or active CIW cellview); `include_positions`; optional parameter filter YAML; timeout. |
| Business outputs | Structured dictionary of instances, terms, CDF params, nets, pins, notes, optional `xy/orient/bBox/numInst/view`, and optional `nlAction`. |
| Substeps | Build a single SKILL program with sections `INSTANCES/NETS/PINS/NOTES/END`; optionally open an owned read-only CV; extract nested DB properties; parse line records; filter CDF params by lib/cell; close owned CV in `unwindProtect`. |
| Middle interfaces | `execute_skill` only; the YAML file is local pure-Python input. |
| Legacy references | `schematic/reader.py:61-234`, `237-357`; examples `11_read_schematic_unified.py:98-107`; tests `test_schematic_reader.py:18-271`. |

### C5. Schematic planning, application, and verification

| Field | Decomposition |
|---|---|
| Business inputs | Ordered/unordered `SchematicInstanceSpec` list; `SchematicPinSpec` list; exact grid constraints; differential-pair constraints; planner config; optional output-stage flags; optional source readback for recreation. |
| Business outputs | `SchematicPlan` containing sorted `PlannedInstance`s, `PlannedPin`s, diagnostics, and `grid_spacing`; optionally a `SchematicReadbackReport`. |
| Substeps | Validate specs; infer device kind; normalize hard/soft strengths; detect duplicate/unknown refs; assign polarity rows and deterministic columns; apply explicit positions; apply pair symmetry (`R0`/`MY`); resolve soft collisions; report hard conflicts; emit editor commands; compare readback. |
| Middle interfaces | None for planning/verification, which are pure Python. Application uses the C1/C2 path and therefore `execute_skill`. |
| Legacy references | `schematic/planner.py:22-541`, `558-969`; example `12_plan_differential_pair.py:34-92`; tests `test_schematic_planner.py:86-372`. |

### C6. Schematic netlist export package

| Field | Decomposition |
|---|---|
| Business inputs | `lib`, `cell`, `view`, simulator, `recreate_all`, local output directory, timeout. |
| Business outputs | `SchematicNetlistExportResult` with remote source file/dir, local output dir/input file, SKILL result, and download result; on disk, `input.scs` plus adjacent netlist support files. |
| Substeps | Validate simulator symbol; generate one OCEAN netlisting SKILL expression; execute; require absolute source path; recursively download containing directory; require `input.scs`; swap/replace target directory while preserving old contents on failure. |
| Middle interfaces | `execute_skill` + `download_file` (`recursive=True`). No `run_spectre_command` is used; export only creates a netlist. |
| Legacy references | `schematic/netlist.py:24-242`; tests `test_schematic_netlist.py:20-152`, `664-834`. |

### C7. Netlist-to-schematic import (`spiceIn` + `conn2Sch`)

| Field | Decomposition |
|---|---|
| Business inputs | Target lib/cell; local or already-remote netlist path; language, sim/output sim names, reference libraries, netlist/schematic views, overwrite, optional device map, optional run directory, timeout. |
| Business outputs | Netlist view created by external `spiceIn`, then schematic view created by `conn2Sch`; current function returns the final SKILL result. |
| Substeps | Discover Cadence environment; preflight target views; resolve run directory; stage netlist/devmap and control files; run `spiceIn`; generate `spiceIn.il` and `cds.lib`; invoke `conn2Sch`/copy/overwrite SKILL; optionally parse/classify logs. |
| Middle interfaces | `execute_skill` (context/preflight/conversion), `upload_file` (local inputs/control files), `run_command` (mkdir/test/`spiceIn`), and `download_file` if logs or artifacts must be returned. `run_spectre_command` is not appropriate: `spiceIn` is not Spectre simulation. |
| Legacy references | `schematic/netlist.py:245-409`, `486-883`; example `08_import_cdl_cap_array.py:81-210`; tests `test_schematic_netlist.py:155-663`. |

### C8. Raw schematic mutation examples that must become explicit business APIs or be deliberately dropped

| Operation | Legacy evidence | Business behavior | Middle need |
|---|---|---|---|
| Rename active instance | `examples/01_virtuoso/schematic/05_rename_instance.py:31-43` | Locates instance in `geGetEditCellView()`, assigns `inst~>name`, then runs `schCheck`/`dbSave`. | `execute_skill`; explicit target validation should replace active-CIW dependence. |
| Delete active instance | `examples/01_virtuoso/schematic/06_delete_instance.py:25-54` | Lists active instances, saves, `dbDeleteObject(inst)`, checks/saves. | `execute_skill`. |
| Delete active cell | `examples/01_virtuoso/schematic/07_delete_cell.py:23-38` | Finds schematic window, saves, closes window, deletes DB cell object. | `execute_skill` and possibly `run_gui_command` if window manipulation is separated. |
| Change analogLib VDC parameter through `schHiReplace` | `01a_create_rc_stepwise.py:85-88`; `10_create_wire.py:140-143` | Uses an editor helper to replace matching instance property values. | `execute_skill`; this overlaps C3 but uses a different mechanism. |

These four flows are not wrapped by `SchematicOps`; they document business behavior that was previously left to users as raw SKILL.

### C9. Manual symbol creation/editing

| Field | Decomposition |
|---|---|
| Business inputs | Symbol lib/cell/view/view_type; geometry layer/purpose/coordinates; text/label type/justification/rotation/font/height; pin name/direction/size/label options; term order. |
| Business outputs | A saved schematic-symbol cellview with geometry, native semantic labels, terminals/nets/pins, selection box, and term order. |
| Substeps | Open symbol cellview; emit `dbCreate*` or `schCreateSymbolLabel`; create net/term/pin entities; optionally create selection box; set `cv~>termOrder`; run `schSymbolToPinList` check; save. |
| Middle interfaces | `execute_skill` only. `SymbolEditor.__exit__` must replace legacy `execute_operations` with a composed `execute_skill` call. |
| Legacy references | `symbol/__init__.py:46-107`; `symbol/editor.py:18-58`; `symbol/ops.py:30-326`; example `03_manual_symbol_semantics.py:32-74`; tests `test_symbol_ops.py:25-252`. |

### C10. Automatic schematic-to-symbol generation

| Field | Decomposition |
|---|---|
| Business inputs | Lib/cell; schematic and symbol view names; `sort_pins` in `alphanumeric`/`geometric`; overwrite flag; timeout. |
| Business outputs | `SymbolGenerationResult` with created/replaced action, final terminal names, and final pin order; or a `RuntimeError` with body/cleanup/rollback detail. |
| Substeps | Reject same source/target views; validate sort mode; capture `ssgSortPins`; collect source terms and effective pin order; generate into UUID temp view; validate temp result; back up target; copy/overwrite; validate installed result; restore environment; delete temp; rollback on failure. |
| Middle interfaces | `execute_skill` only. The temporary views are DB objects, not filesystem assets. |
| Legacy references | `symbol/generator.py:20-393`; examples `symbol/01_rc_create_with_symbol.py:71-77`, `02_bus10_create_with_symbol.py:57-64`; tests `test_symbol_generator.py:48-632`. |

### C11. Symbol semantics and structured readback

| Field | Decomposition |
|---|---|
| Business inputs | Lib/cell/view/view_type. |
| Business outputs | Dictionary with `terms`, `labels`, `pinOrder`, `portOrder`, `termOrder`, and `selectionBoxes`, including layer/purpose/label type and geometry metadata. |
| Substeps | Open symbol read-only; enumerate terminals and pin figure bbox; enumerate labels with semantics; find `instance/drawing` selection boxes; read pin/port/term order; close under `unwindProtect`; parse one complete SKILL S-expression. |
| Middle interfaces | `execute_skill` only. |
| Legacy references | `symbol/reader.py:21-187`, `190-271`; example `03_manual_symbol_semantics.py:66-74`; tests `test_symbol_reader.py:15-303`. |

### Capability-to-middle-interface summary

| Capability | Skill | Command | File upload | File download | GUI | Spectre |
|---|---:|---:|---:|---:|---:|---:|
| C1 lifecycle/batch | required | — | — | — | optional for window display | — |
| C2 edit builders/execution | required for execution | — | — | — | — | — |
| C3 CDF params | required | — | — | — | — | — |
| C4 readback | required | — | — | — | — | — |
| C5 planner/apply | required for apply only | — | — | — | — | — |
| C6 netlist export | required | — | — | required | — | — |
| C7 netlist import | required | required | required | optional | — | — |
| C8 raw mutations | required | — | — | — | optional | — |
| C9 manual symbol | required | — | — | — | — | — |
| C10 symbol generation | required | — | — | — | — | — |
| C11 symbol readback | required | — | — | — | — | — |

No scoped capability requires `run_spectre_command`. GUI is not required by the core APIs; only open/reuse-window helpers in examples are UI-facing (`virtuoso/ops.py:60-93`).

---

## 4. SKILL-vs-Python split

### 4.1 Per-capability split

| Capability | Pure Python logic | Required SKILL round-trip / generated SKILL | Embedded SKILL / assets |
|---|---|---|---|
| C1 lifecycle/batch | Command accumulation, argument storage, context-manager control flow, response normalization. | One round-trip executing open + edits + check + save. | `dbOpenCellViewByType`, `schCheck`, `dbSave`; generated in `virtuoso/ops.py:42-58`, `95-101`. |
| C2 primitive edit builders | Validation/escaping/coordinate formatting and construction of SKILL strings. | Round-trip only when the caller submits generated strings to an editor. | `dbCreateInst`, `schCreateWire`, `schCreateWireLabel`, `schCreateNetExpression`, `dbReplaceProp`, `schCreatePin`, terminal bbox/transform expressions. |
| C3 CDF params | YAML load/match, shorthand mapping, allowlist/strict filtering, warning generation, parameter-table rendering. | Three separate calls in `set_instance_params`: active schematic lookup, instance master lookup, update/callback batch. | `geGetEditCellView`, `dbOpenCellViewByType`, `cdfGetInstCDF`, `cdfGetCellCDF`, callback `evalstring`, `cdfUpdateInstParam`, `schCheck`, `dbSave`, plus a `makeTable`/`setarray` parameter table (`params.py:43-70`, `90-158`). |
| C4 readback | YAML filtering, line-protocol parsing, type defaults, point/bbox parsing, named-vs-current ownership policy. | One large read SKILL call. | `dbOpenCellViewByType`, `geGetEditCellView`, DB traversals (`instances`, `instTerms`, `nets`, `terminals`, `shapes`), CDF traversal, `unwindProtect`, `dbClose` (`reader.py:61-234`, `416-588`). |
| C5 planner | All validation, constraint precedence, deterministic sorting, collision resolution, coordinate math, readback comparison. | None for planning/verifying; only the normal editor path when applying. | Emits existing C2 builders; no new SKILL language (`planner.py:1-5`, `408-451`). |
| C6 export | Absolute-path checks, temp-directory naming, download result adaptation, atomic replace/backup, `input.scs` existence check. | One netlisting SKILL call; then file download. | `simulator`, `design`, `ddsRefresh`, `createNetlist`, `simplifyFilename`; embedded as a string (`netlist.py:123-159`). |
| C7 import | Local-path/control-file collision checks, UUID run-dir naming, parameter-file text generation, environment mapping, shell quoting, local/remote branch selection, result parsing/classification. | Context discovery, preflight, and `conn2Sch`/copy conversion are SKILL calls. | `getWorkingDir`, `getShellEnvVar`, `cdsGetInstPath`, `ddGetObj`, `conn2Sch`, `dbOpenCellViewByType`, `dbCopyCellView`, `ddDeleteObj`, `unwindProtect`, `dbClose`; external `spiceIn -param` command. |
| C8 raw mutations | None in package; examples contain argument/list parsing only. | One SKILL call per mutation, often plus check/save. | `geGetEditCellView`, `inst~>name = ...`, `dbDeleteObject`, `hiCloseWindow`, `ddDeleteObj`, `schHiReplace` (`examples/.../05_rename_instance.py:31-42`, `06_delete_instance.py:25-53`, `07_delete_cell.py:23-36`, `01a_create_rc_stepwise.py:85-88`). |
| C9 manual symbol | Validation/escaping, bbox/point rendering, semantic-label choice, pin-size/label placement math. | One batch round-trip for all commands plus check/save. | `dbCreateLine/Rect/Polygon/Ellipse/Label`, `schCreateSymbolLabel`, `dbCreateNet/Term/Pin`, `cv~>termOrder`, `schSymbolToPinList`, `dbSave` (`symbol/ops.py`, `symbol/editor.py`). |
| C10 symbol generation | Sort-mode validation, UUID temp/backup names, strict result parsing, terminal/pin-order consistency check. | One very large SKILL call containing generation, validation, backup, install, rollback, and cleanup. | `schGetPinOrder`, `schSchemToPinList`, `schPinListToSymbol`, `dbCopyCellView`, `dbFindOpenCellViewByName`, `schGetEnv`/`schSetEnv`, `ddGetObj`/`ddDeleteObj`, `unwindProtect` (`generator.py:47-256`). |
| C11 symbol readback | Single-complete-list validation, recursive S-expression parse, record normalization, bbox/point conversion, error aggregation. | One read-only SKILL call. | `dbOpenCellViewByType`, terminal/pin bbox traversal, label traversal, `schGetPinOrder`, `cv~>portOrder`, `cv~>termOrder`, `unwindProtect`, `dbClose` (`symbol/reader.py:21-187`). |

### 4.2 SKILL string generation and assets

- All scoped SKILL is **embedded as Python strings/f-strings** or assembled from constants. There is no scoped `.il` asset loaded from disk.
- The reader templates are module constants (`schematic/reader.py:61-175`, `389-412`, `461-483`, `530-551`); the symbol reader template is in `symbol/reader.py:29-88`.
- The symbol generator is a complex embedded SKILL program with temporary view names and rollback logic (`symbol/generator.py:94-256`); it is not a simple one-line wrapper.
- Netlist import writes `spiceIn.il` and `cds.lib` as staged control files (`schematic/netlist.py:688-757`). Those are artifacts needed by an external tool, not SKILL loaded by the CIW.
- Parameter callbacks are dynamically evaluated in SKILL with `evalstring(cb)` (`schematic/params.py:62-66`), so Python cannot precompute callback behavior.

### 4.3 What is safe in the new upper layer

Pure Python planning, validation, escaping, path-independent result parsing, and data-model conversion remain upper-layer responsibilities. DB access and mutation must be submitted through `execute_skill`; external tools must use `run_command`/`run_spectre_command`; file staging must use `upload_file`/`download_file`. In particular, do not retain `client.execute_operations`, `client.ssh_runner`, `client._tunnel`, `subprocess`, or `system()`/`csh()` as upper-layer mechanisms (`spec/design-concepts/总览/1-四层整体架构与接口.md:133-136`).

---

## 5. State/files/IPC dependencies that will not exist in the new upper layer

### 5.1 Direct concrete-client dependencies

| Legacy dependency | Where observed | Why it is a risk | Required replacement |
|---|---|---|---|
| Concrete `VirtuosoClient` (`from_env`, constructor injection) | `schematic/__init__.py:71`, `params.py:90-127`, `reader.py:181-220`, `symbol/__init__.py:43`, `symbol/reader.py:157-170`, all examples. | New upper packages receive a `Middle`, not SSH/tunnel/client objects. | Depend on the `Middle` protocol and require `token` on every call; keep business methods transport-neutral. |
| `client.execute_operations()` | `schematic/editor.py:76`, `symbol/editor.py:57`. | This legacy batch method is not one of the five interfaces and has no counterpart in `Middle`. | Compose a single executable SKILL batch and call `middle.execute_skill`. |
| Old `VirtuosoResult`/dict response normalization | `virtuoso/editor.py:10-24`, `reader.py:220-227`, `symbol/reader.py:171-187`. | New middle returns `VirtuosoResult` with `status/output/errors/warnings/metadata/log`; legacy helper accepts object/dict shapes and sometimes expects nested `result`. | Use the normative `VirtuosoResult` fields (`src/pyapi/models.py`) and make error policy explicit. |
| `client.download_file`/`client.upload_file` returning legacy results | `schematic/netlist.py:211-223`, `811-813`; examples `08_import_cdl_cap_array.py:151-152`. | New middle returns `CommandResult(returncode, stdout, stderr, kind)` for file transfers. | Use `middle.download_file`/`middle.upload_file` and check `returncode`/`kind`, not old `.status`/`.errors`. |
| `client.open_window`, `client.get_current_design` | examples `01a:90`, `04:102`, `11:92`, `12`; legacy client facade. | These are legacy convenience methods with no direct five-interface signature. | Model as explicit `execute_skill`/`run_gui_command` business steps, or remove from the core package if not required. |
| Legacy `ExecutionStatus` import | `netlist.py:17`, response helpers. | New upper-layer models are `src/pyapi/models.py`; carrying old status types couples layers. | Convert to the new `VirtuosoResult.status` model at the boundary. |

### 5.2 Filesystem and process assumptions

| Legacy dependency | Where observed | Why it breaks / what to decide |
|---|---|---|
| Local `pathlib.Path` operations on output/run paths | `netlist.py:206-233`, `551-585`, `633-654`, `765-781`; examples `08:148-171`. | The upper layer cannot know whether a path is local, remote, or shared across GUI/deploy/daemon roles. `upload_file`/`download_file` must own transfer; the business package should pass logical paths or role-neutral paths. |
| `subprocess.run` for local `spiceIn` | `netlist.py:573-585`. | Forbidden in the new upper layer. Replace with `middle.run_command` (or a dedicated future command role) and keep timeout/returncode handling. |
| `subprocess.run` + manual `ssh` construction | example `08_import_cdl_cap_array.py:81-90`, `174-177`. | Explicitly exposes SSH, jump hosts, remote username, and command construction; must disappear from upper-layer examples. |
| `client.ssh_runner` branch | `netlist.py:362-396`. | Observable local-vs-remote behavior currently changes which function runs. New upper must not branch on transport; either define distinct business methods or have the middle route a role-neutral command. |
| `client._tunnel`, `_remote_host`, `_remote_user`, `_ssh_runner`, `_profile`, `upload_text` | example `08:83-90`, `137-152`, `171`. | All are private transport/registry details and are forbidden upper-layer dependencies. | Use file/command interfaces; remove private access from redeveloped examples. |
| Default remote path `/tmp/virtuoso_bridge_...` | `netlist.py:674-685`. | Assumes `/tmp` and remote absolute filesystem; may not be visible to GUI/daemon/file roles. | Let middle/config supply scratch root or use opaque run IDs and file services. |
| Local environment mutation with `os.environ.copy()` and Cadence path/license variables | `netlist.py:821-843`. | Upper layer must not manipulate process env or assume local tool installation. | Pass environment/path discovery as a middle/config concern; command role should execute with the correct remote environment. |
| `shutil.rmtree`/rename/backup logic for output packages | `netlist.py:93-120`, `206-233`. | May be valid local business logic, but only if the destination is local to the upper package; must not assume the remote netlist directory is directly manipulable. | Keep local atomic replacement in the package, but make remote staging/download explicit through the file interface. |
| YAML asset path relative to module | `reader.py:33`, `params.py:41`; `cdf_param_filters.yaml`. | Packaging/installation must include the resource; a relocated upper package cannot assume `Path(__file__).parent` layout without a resource strategy. | Embed as a package resource or accept explicit filter model/JSON. |

### 5.3 CIW/session state assumptions

| Legacy dependency | Where observed | Why it is a risk |
|---|---|---|
| `geGetEditCellView()` for parameter setter | `params.py:90-102`. | Mutates the “currently active” schematic, not a caller-specified target. New business API should normally take explicit `lib/cell` (or a validated active-design precondition). |
| `cv` bound by `open_cell_view`; `save_current_cellview` chooses bound `cv` or current edit cellview | `virtuoso/ops.py:42-58`, `95-101`; editors. | The batch relies on CIW variable/session state. A redeveloped upper layer should make the open/save/check sequence one explicit SKILL program and avoid cross-call variable assumptions where possible. |
| `geGetEditCellView()` in raw rename/delete examples | `05_rename_instance.py:32-37`, `06_delete_instance.py:26-52`. | Same implicit active-design coupling; hidden state is not visible to upper-layer validation. |
| Window identity and GUI dialogs | examples `01a:90`, `04:102`, `07:23-36`; symbol generator explicitly avoids GUI dialogs (`generator.py:59-67`). | Window APIs are not portable business contracts; GUI-dependent flows need `run_gui_command` or a deliberate no-GUI SKILL strategy. |
| Temporary DB view names carry UUIDs | `generator.py:64-65`; import temp view `netlist.py:267`. | These are Virtuoso database state, not filesystem state. Cleanup/rollback must remain atomic inside the SKILL call; splitting it across calls would increase orphan risk. |

### 5.4 Asset/parser dependencies

| Dependency | Location | Redevelopment impact |
|---|---|---|
| YAML parser and `fnmatch` | `reader.py:24-30`, `params.py:29-33`. | Pure Python, but the default asset and filter semantics must be preserved or replaced by an explicit typed filter object. |
| `decode_skill_output` | `reader.py:30`, `params.py:35`. | Legacy helper strips/wraps output; new middle returns raw `output`. Parser must define escaping and empty/nil behavior itself. |
| S-expression parser | `symbol/reader.py:9-12`, `symbol/generator.py:12-15`. | Must remain available to upper parsing or be duplicated as a tested pure-Python utility; it is not a transport interface. |
| Response normalizer accepting object/dict/scalar errors | `symbol/reader.py:171`, `response.py:9-44`; tests `test_symbol_reader.py:290-303`. | New `VirtuosoResult` is a stricter model; compatibility shims may be unnecessary, but error normalization tests remain useful behavioral evidence. |
| `.il` loading | Not used by these scoped modules; only legacy client `load_il` exists elsewhere. | No scoped `.il` asset migration is needed, but the generated SKILL strings still need a safe execution wrapper. |

---

## 6. Test/example evidence

### 6.1 `test_bak/test_schematic_ops.py` — generated SKILL contracts

- `test_schematic_create_net_expression_attaches_expression_to_net_wire` pins the `schCreateNetExpression` call, net lookup, wire-not-found guard, point, justification, rotation, font, and height (`test_schematic_ops.py:13-30`).
- `test_schematic_create_net_expression_accepts_custom_cellview_expr` pins `cv_expr` propagation to both `shapes` and the creator call (`test_schematic_ops.py:33-43`).
- `test_schematic_set_netset_property_writes_inherited_override` pins `dbReplaceProp(rbInst "vdd" "netSet" "VDD")` after instance lookup (`test_schematic_ops.py:46-51`); the escaping test pins quotes/backslashes (`54-58`).
- `test_schematic_create_net_stub_draws_short_wire_and_label` pins a `(0,0)->(0.5,0)` wire and midpoint `R0` label (`test_schematic_ops.py:61-65`); vertical stubs auto-rotate to `R90` (`68-72`); explicit rotation wins (`75-79`).
- Validation tests require positive length and known direction (`test_schematic_ops.py:82-89`).
- Label tests preserve legacy behavior: default labels are unbound (`nil`) and the wire still uses `cv` even when `cv_expr` is custom; opt-in `bind_label_to_wire=True` passes the created wire object and uses the custom cellview for both wire and label (`test_schematic_ops.py:92-130`).

### 6.2 `test_bak/test_schematic_planner.py` — deterministic planner behavior

- `test_planner_builds_deterministic_differential_pair_acceptance_plan` asserts forward/reversed input equality, exact pair coordinates/orientations, tail position, output column `5.0`/absolute `x=7.5`, and all pins in column `-1.0` (`test_schematic_planner.py:86-107`).
- Hard position/pair conflict must raise `SchematicPlanningError` and expose `hard_constraint_conflict` (`test_schematic_planner.py:110-132`).
- Pair row defaults adopt a hard member row (`test_schematic_planner.py:135-148`); soft relaxation must produce a `RELAXED` diagnostic (`151-177`).
- Hard grid collisions must fail (`180-195`); soft collisions must move one item and emit `soft_grid_collision_resolved` (`198-214`).
- `from_readback` must convert `xy=(3.0,1.5)` with spacing `1.5` to `(2.0,1.0)`, preserve `MY`/terminal maps, and sort pins (`test_schematic_planner.py:217-243`); missing `xy` must fail with an `include_positions=True` message (`246-253`).
- `plan.apply` must emit `dbCreateInst` and `schCreatePin` and pass MOS nets in `drain_net/gate_net/source_net/body_net` form (`test_schematic_planner.py:256-280`).
- `create_from_plan` must execute `schCheck(cv)` as penultimate command and a `dbSave(rbCv)` command last (`test_schematic_planner.py:283-303`).
- Readback reports must expose mismatch codes, `require_valid()` must raise with details, malformed positions become `position_mismatch` rather than crashing (`test_schematic_planner.py:306-366`), and non-positive grid spacing is rejected (`369-372`).

### 6.3 `test_bak/test_schematic_reader.py` — readback contracts and ownership

- SKILL errors are surfaced as `read_schematic SKILL error`; empty output is an error (`test_schematic_reader.py:18-24`, `245-251`).
- The timeout is forwarded exactly to `execute_skill` (`27-39`).
- Named reads open `("LIB" "CELL" "schematic" "schematic" "r")`, wrap in `unwindProtect`, and close with `dbClose(cv)`; current-cellview reads use `geGetEditCellView()` and do not close it (`42-82`).
- All three legacy readers follow the same named/current ownership and cleanup rules and surface cleanup errors (`85-185`).
- Partial named targets must fail before SKILL execution with `lib and cell must both be non-empty when provided` (`188-215`).
- `SchematicOps.read` delegates to `reader.read_schematic` with the original owner/lib/cell and only passes explicitly overridden kwargs (`218-242`).
- Parser defaults non-numeric bus widths to `1` and preserves names containing `<...>` (`254-271`).

### 6.4 `test_bak/test_schematic_netlist.py` — export/import safety and routing

- Export SKILL must contain OCEAN `createNetlist`, `simulator('spectre)`, `design(...)`, `simplifyFilename`, and the netlist source variable (`test_schematic_netlist.py:20-33`).
- Names must be SKILL-escaped and the simulator must be restricted to a simple symbol (`36-51`).
- Export must download the returned containing directory recursively to a sibling temp path, require `input.scs`, then install the package (`54-105`).
- Existing output is replaced only after a valid download; stale files disappear, while download failure or final replace failure preserves the old output (`test_schematic_netlist.py:664-716`, `798-834`).
- Relative source paths and output directories nested below the remote source directory are rejected (`761-795`); missing `input.scs` is rejected even if another `.scs` was returned (`719-759`).
- Import SKILL must remain DB-only: no `spiceIn`, `system()`, or `conn2sch` shell invocation (`test_schematic_netlist.py:155-176`).
- Local `spiceIn` runs outside SKILL with discovered environment, writes `spiceIn.il`/`cds.lib`, and returns the final conversion result (`test_schematic_netlist.py:191-252`).
- Local control-file collisions and missing local input are rejected before execution (`254-323`); default run directories include a UUID and are unique (`326-365`).
- Remote import stages `netlist_<name>`/`devmap_<name>` under `inputs/`, uploads `spiceIn.il` and `cds.lib`, creates directories, and invokes `bash -lc` with discovered `spiceIn` (`test_schematic_netlist.py:368-429`).
- Already-remote absolute inputs are validated with quoted `test -f`; relative/missing remote inputs are rejected (`432-589`).
- `conn2Sch` errors propagate (`592-626`); `SchematicOps.import_netlist` forwards all documented defaults and timeout (`629-661`).

### 6.5 `test_bak/test_symbol_ops.py` — symbol primitive and editor contracts

- Shape builders produce exact `dbCreateLine/Rect/Polygon/Ellipse` statements (`test_symbol_ops.py:25-41`).
- Drawing labels set `labelType` and escape text; semantic labels use `schCreateSymbolLabel` choices `"pin name"`, `"instance label"`, `"logical label"` with `normalLabel`/`NLPLabel` and explicit failure guards (`test_symbol_ops.py:44-104`).
- Selection box is the `instance/drawing` rectangle (`test_symbol_ops.py:106-113`).
- `symbol_create_pin` must first reject an existing terminal, create/reuse a net, create term, create pin rectangle, optionally create the pin-name label, and create `dbCreatePin` (`test_symbol_ops.py:116-143`); `label=False` omits only the label (`146-155`).
- Repeated pin/direction strings must be escaped (`158-170`); term order renders a SKILL string list (`173-175`).
- `symbol_check` must use `schSymbolToPinList`, not `schCheck`, and fail if pin-list generation fails (`178-185`).
- Symbol editor tests pin command order: open, user geometry, `symbol_check()`, saved command, custom view type forwarding, and both legacy response failure shapes (`188-246`).

### 6.6 `test_bak/test_symbol_reader.py` — semantic readback contracts

- Read SKILL must open the symbol, report term direction/width/bbox, labels and coordinates, selection boxes, and all three orders; the skill contains `unwindProtect` close handling (`test_symbol_reader.py:15-41`).
- Legacy TSV is rejected; malformed/truncated/trailing S-expressions are rejected (`44-82`).
- Label strings preserve tabs/newlines/quotes/backslashes through S-expression parsing (`85-102`).
- Labels must expose `labelType`, `xy`, layer/purpose/justify/orient/font/height/bbox; selection boxes normalize to float pairs (`105-128`).
- `read_symbol_ports` forwards custom `view_type`, normalizes errors/empty output, and supports object, flat dict, and nested dict outputs (`131-179`, `229-287`).
- `test_read_symbol_ports_parses_structured_skill_output` pins term, label, and term-order extraction, while `test_read_symbol_ports_accepts_nested_dict_output` pins support for both flat and nested transport responses (`test_symbol_reader.py:241-287`).
- Scalar errors and non-string output are normalized for compatibility (`test_symbol_reader.py:290-303`); stricter generation payload/order validation is covered separately in `test_bak/test_symbol_generator.py`.

### 6.7 `test_bak/test_symbol_generator.py` — generation and rollback semantics

- Successful generation returns `SymbolGenerationResult` with `created`, terminal names, pin order, custom views, and one SKILL call (`test_symbol_generator.py:48-92`, `321-360`).
- Same source/target view is rejected; `sort_pins` accepts only `alphanumeric`/`geometric` (`95-102`, `153-156`).
- Generated SKILL must escape all names, temporarily set/restore `ssgSortPins`, use a UUID temp symbol view, and avoid GUI dialogs (`105-143`, `145-150`).
- Existing targets are rejected by default; `overwrite=True` uses verified temp generation, opens/copies a backup, performs an atomic replacement, and rolls back from the backup if validation/cleanup fails (`159-214`, `177-199`).
- Source pin order is captured before source close and compared with generated/final order; installed terminals are read back and validated (`247-260`, `381-391`).
- Body failures and cleanup failures are captured separately and combined in the protocol (`264-283`, `449-496`).
- Malformed terminal payloads, duplicate terminals, invalid widths, missing/scalar pin orders, trailing protocol data, and terminal/order set mismatch must raise without a second “readback” call or hanging (`394-420`, `499-554`, `557-629`).
- Empty terminal payload (`nil`) is valid and yields empty tuples (`611-631`).

### 6.8 Example evidence

- `01a`/`01b` demonstrate the primary creation path: open `client.schematic.create`, add master instances, add terminal net labels, rely on context-exit check/save, then optionally mutate a CDF value and open the window (`01a_create_rc_stepwise.py:69-91`, `01b_create_rc_load_skill.py:69-83`).
- `02` and `03` demonstrate the legacy standalone readers and their shapes; `11` explicitly says the unified reader supersedes `read_connectivity`/`read_instance_params`/`read_placement` (`02_read_connectivity.py:14-63`, `03_read_instance_params.py:15-47`, `11_read_schematic_unified.py:4-107`).
- `04` demonstrates a practical parameter workflow: create analogLib devices, make the schematic active, call `set_instance_params(..., strict=True)`, then read back and compare normalized values (`04_test_set_instance_params_analoglib.py:43-110`).
- `09` and `10` demonstrate pin placement and wire/label patterns, including the important note that wire shapes alone have no electrical meaning and must be paired with net labels (`10_create_wire.py:28-31`, `88-143`).
- `12` demonstrates the planner contract end to end: environment-supplied MOS masters, explicit constraints, diagnostics, `create_from_plan`, readback, and `require_valid()` (`12_plan_differential_pair.py:34-92`).
- `08` demonstrates the legacy CDL import route and is also the strongest warning: it reaches into `client._tunnel`, constructs SSH itself, calls `subprocess.run`, uploads text, and later invokes symbol generation (`08_import_cdl_cap_array.py:81-90`, `120-177`, `209-216`).
- Symbol examples demonstrate both generated and manual flows: RC and 20-pin TSG generation (`symbol/01_rc_create_with_symbol.py:71-77`, `02_bus10_create_with_symbol.py:44-64`) and native semantic labels/pins/selection box/term order followed by port readback (`03_manual_symbol_semantics.py:32-74`).

---

## 7. Open questions / ambiguities

1. **Import return contract is inconsistent.** `import_netlist_schematic` is annotated and implemented as returning the final SKILL result (`netlist.py:324-340`, `398-409`), while `NetlistImportResult` and `parse_netlist_import_output` clearly model a structured import result (`netlist.py:412-468`). Decide whether the new upper API should return a structured import model and expose the raw `VirtuosoResult`/paths in steps or metadata.

2. **`parse_netlist_import_output` is not used by the import orchestrator.** The import path returns the raw SKILL result; the parser and `classify_netlist_import_log` are exported but not integrated (`netlist.py:398-409`, `471-483`). It is unclear whether these were intended as future post-processing helpers or are accidental unused surface.

3. **Local-vs-remote input semantics are implicit.** `_stage_remote_input` treats a `Path` as a local file if it exists; otherwise it assumes an absolute POSIX remote path and checks it with `test -f` (`netlist.py:784-804`). This behavior cannot survive the new “upper layer must not know local/remote/port” rule without a deliberate API contract (for example: one method for local upload, one for already-staged remote file, or an opaque file handle).

4. **Scratch directory ownership is unresolved.** The default run directory is hard-coded to `/tmp/virtuoso_bridge_netlist_import_...` (`netlist.py:674-685`). The new middle layer has role-specific roots and may need a shared path visible to GUI/daemon/command/file roles. The normative config/spec should decide whether upper code passes a logical run ID or receives a middle-managed root.

5. **`spiceIn` routing is ambiguous.** It is an external Cadence command, not a Spectre simulation, so `run_command` is the closest current interface; however its correctness depends on the same remote shell/environment and filesystem as the Virtuoso/daemon roles. The new route design should confirm whether `run_command` or a future specialized command role owns it.

6. **The YAML filter resource has no defined upper-layer packaging model.** Both reader and setter use a module-relative file (`reader.py:33`, `params.py:41`). Decide whether this remains a package resource, becomes a typed configuration/model, or is supplied by the caller through the new upper-layer API.

7. **`w` semantics need confirmation.** The docstring says `w` is total width and is related to `wf × nf`, but the implementation stores `params["w"]` directly and only maps `wf -> Wfg` and `nf -> fingers` (`params.py:38-40`, `178-207`). If PDK CDFs expose a different total-width field, the mapping is incomplete; no requested test covers this.

8. **`set_instance_params` return is not a readback.** It returns the filtered submission dictionary (`params.py:229-235`), while the example verifies effectiveness with a separate `client.schematic.read(...)` (`04_test_set_instance_params_analoglib.py:64-80`). A new API should decide whether success means “submitted” or “verified readback.”

9. **Active-CIW behavior is intentional in some legacy flows.** `set_instance_params`, rename, delete, and some examples operate on `geGetEditCellView()` rather than an explicit target (`params.py:90-102`, examples `05-07`). It is not clear whether the new upper API must preserve this convenience or require explicit `lib/cell/view` for reproducibility.

10. **Public visibility of reader/params is inconsistent.** The package `__all__` omits `read_schematic`, `read_placement`, `read_connectivity`, `read_instance_params`, and `set_instance_params`, but examples and docs use them directly (`schematic/__init__.py:232-275`, examples `02:15`, `03:16`, `04:24`). Decide whether the redeveloped API keeps these as public entry points.

11. **Legacy `read_placement` returns raw strings.** Its `xy`, labels, and wires are not parsed into numeric/geometry models (`reader.py:433-458`), unlike unified readback (`reader.py:283-288`, `345-350`). Preserve this distinction only if downstream users depend on it.

12. **Planner wire routing is absent.** The planner explicitly does not synthesize topology or route wires; it only emits instance/label/pin operations (`planner.py:1-5`, `408-451`). If the redevelopment expects “create schematic from netlist spec” including wires, that is a new capability rather than a port of this planner.

13. **Symbol generation’s atomicity boundary is a single huge SKILL string.** Backup/rollback, temp cleanup, terminal verification, and environment restoration all live in the generated program (`generator.py:94-256`). The new upper layer should preserve the single-round-trip atomicity unless the middle interface gains transactional DB support.

14. **`SymbolPinSort` is only a typing alias.** It is `Literal["alphanumeric", "geometric"]` (`generator.py:17-20`), while runtime validation checks a set (`generator.py:312-315`). New models should use a real enum or validated literal consistently.

15. **Symbol readback parser behavior for missing/optional records is only partially pinned.** The full record parser fills defaults for absent optional label fields (`reader.py:130-148`), but the generator/reader tests mostly pin complete records and malformed failures. Define a canonical optional-field policy before reimplementation.

16. **No scoped `.il` asset loading exists.** All schematic/symbol SKILL is embedded or generated (`schematic/reader.py:61-175`, `symbol/generator.py:94-256`). If the new architecture standardizes `.il` assets, this subsystem needs an explicit conversion/loading policy, but no existing scoped file establishes one.

17. **GUI-command mapping is not evidenced.** The only obvious GUI interaction is window opening/reuse (`virtuoso/ops.py:60-93`, examples `01a:90`, `04:102`), which used SKILL in the legacy implementation. Whether the new upper layer should call `run_gui_command` for those steps or keep them as SKILL is a design decision not settled by the scoped code.

18. **Legacy tests pin exact generated SKILL in several places.** This is stronger than behavior-only compatibility (for example `test_schematic_ops.py:25-30`, `test_symbol_ops.py:25-41`, `test_symbol_generator.py:118-142`). If the new implementation aims to preserve semantic behavior rather than textual output, the new tests should assert the resulting DB/readback state instead of exact strings; if textual compatibility is required, the templates must be copied closely.

---

### Executive handoff summary

The legacy schematic subsystem consists of three distinct layers of work: pure Python SKILL builders/planner/parsers, CIW DB mutation/readback through `execute_skill`, and a high-risk netlist-import/export orchestrator that currently reaches into concrete client, SSH, subprocess, and remote filesystem details. The symbol subsystem is cleaner: manual drawing is mostly string generation plus one batch SKILL call, TSG generation is a single carefully validated/transactional SKILL call, and readback is a single structured SKILL call plus a pure-Python S-expression parser. For the new architecture, the safest split is to keep builder/planner/parser logic in upper-layer packages, route every DB action through `execute_skill`, route the external `spiceIn` command through `run_command`, route all staging through the file interfaces, and explicitly redesign the ambiguous local/remote input and scratch-directory contracts before reimplementing netlist import.
