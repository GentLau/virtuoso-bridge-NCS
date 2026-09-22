# Legacy Layout / GDS Import Inventory

Scope: read-only inventory of the legacy layout subsystem and its geometry/format/import dependencies. This report is a re-development input for the new upper layer, which may call only `middle.execute_skill`, `middle.run_command`, `middle.upload_file`, `middle.download_file`, `middle.run_gui_command`, and `middle.run_spectre_command` (`src/pyapi/models.py:98-128`; `spec/design-concepts/总览/1-四层整体架构与接口.md:178-212`).

The key architectural fact is that the legacy code mixes four concerns: pure Python planning/parsing, SKILL text generation, legacy `VirtuosoClient`/SSH access, and Cadence/Visio tool orchestration. The current layout package does not expose a clean five-interface seam. In particular, `streamout.py` reaches through `client.ssh_runner`, runs remote shell commands, uploads/downloads files, and directly manipulates local staging directories (`src_bak/virtuoso_bridge/virtuoso/layout/streamout.py:5-34`, `:761-776`, `:779-1010`, `:1312-1865`, `:1971-2746`).

## 1. Module inventory table

Line counts are physical text lines (including a final newline when present).

| Path | Lines | One-line purpose |
|---|---:|---|
| `src_bak/virtuoso_bridge/virtuoso/layout/__init__.py` | 173 | Public facade: attaches `LayoutOps` to a client and re-exports layout, XStream, and GDS-export APIs. |
| `src_bak/virtuoso_bridge/virtuoso/layout/editor.py` | 76 | `LayoutEditor` context manager that opens/binds a layout, batches SKILL commands, saves on clean exit. |
| `src_bak/virtuoso_bridge/virtuoso/layout/ops.py` | 485 | Pure SKILL-string builders for layout lifecycle, shapes, vias, routing, labels, visibility, selection, reads, and deletion. |
| `src_bak/virtuoso_bridge/virtuoso/layout/reader.py` | 54 | Parses the tab-separated geometry dump produced by `layout_read_geometry` into Python dictionaries. |
| `src_bak/virtuoso_bridge/virtuoso/layout/streamout.py` | 2,956 | Large XStream-Out GDS export orchestrator: validation, staging, SKILL launch, polling, log finalization, publication, and cleanup. |
| `src_bak/virtuoso_bridge/virtuoso/layout/xstream.py` | 369 | Pure XStream request renderer and XStream log parser/models, including terminal-failure detection. |
| `src_bak/virtuoso_bridge/virtuoso/visio.py` | 546 | Schematic-to-Visio model builder plus optional Windows Visio COM drawing/export layer. |
| `test_bak/test_layout_streamout.py` | 5,528 | Extensive behavioral specification for GDS export, remote/local transport, polling, publication, cleanup, and result classification. |
| `test_bak/test_xstream_helpers.py` | 903 | Pure tests for XStream request rendering, request-response parsing, and XStream log semantics. |
| `test_bak/test_export_gds_example.py` | 94 | Pins the GDS example's preflight error JSON contract and exit code. |
| `examples/01_virtuoso/layout/01_create_layout.py` | 135 | Demonstrates `client.layout.create()` with a rectangle, path, label, and parameterized instance. |
| `examples/01_virtuoso/layout/02_add_polygon.py` | 61 | Demonstrates appending a polygon to the currently open layout. |
| `examples/01_virtuoso/layout/03_add_via.py` | 80 | Demonstrates via-by-name and raw via creation. |
| `examples/01_virtuoso/layout/04_multilayer_routing.py` | 65 | Adds the same path geometry on several metal layers. |
| `examples/01_virtuoso/layout/05_bus_routing.py` | 94 | Adds an 8-bit bus route and per-bit labels. |
| `examples/01_virtuoso/layout/06_read_layout.py` | 61 | Executes the geometry dump and parses it through `parse_layout_geometry_output`. |
| `examples/01_virtuoso/layout/07_delete_shapes_on_layer.py` | 60 | Lists shapes, deletes one layer/purpose, then saves. |
| `examples/01_virtuoso/layout/08_clear_routing.py` | 36 | Deletes all shapes while preserving instances. |
| `examples/01_virtuoso/layout/09_clear_current_layout.py` | 41 | Clears all visible figures from the active layout editor. |
| `examples/01_virtuoso/layout/10_delete_cell.py` | 43 | Closes the active cellview and deletes the whole cell. |
| `examples/01_virtuoso/layout/11_read_summary.py` | 47 | Prints the lightweight layout summary. |
| `examples/01_virtuoso/layout/12_layer_visibility.py` | 96 | Exercises hide/show/show-only layer visibility and fit-view. |
| `examples/01_virtuoso/layout/13_select_and_delete.py` | 82 | Selects figures in a bounding box and deletes the selection. |
| `examples/01_virtuoso/layout/14_mosaic_and_nets.py` | 126 | Creates a mosaic, highlights a net, and sets the active LPP. |
| `examples/01_virtuoso/layout/15_export_gds.py` | 136 | CLI wrapper around `client.layout.export_gds()` with JSON result reporting. |
| `examples/01_virtuoso/layout/flower.py` | 161 | Pure geometry demo that decomposes ellipses into polygons and emits paths/labels. |
| `examples/01_virtuoso/digital_import/add_power_labels.py` | 165 | SKILL-only post-import step that finds power/ground terminals and creates labels. |
| `examples/01_virtuoso/digital_import/digital_import.py` | 234 | One-shot local pipeline orchestrator for strmin, ihdl, power labels, and label restyling. |
| `examples/01_virtuoso/digital_import/import_gds.py` | 284 | `strmin` GDS-import wrapper with local staging, cds.lib checks, log-driven completion, and verification. |
| `examples/01_virtuoso/digital_import/import_verilog.py` | 258 | `ihdl` structural-Verilog import wrapper that writes a parameter file and verifies schematic/functional views. |
| `examples/01_virtuoso/digital_import/restyle_labels.py` | 254 | Parses floorplan Tcl side directives and restyles layout labels in one SKILL traversal. |
| `examples/01_virtuoso/assets/layout_ops.il` | 103 | Legacy standalone SKILL procedure contract equivalent to the read/list/delete operations. |
| `examples/circuit.vss` | 4,955 | Visio stencil asset; required by the COM exporter and located by `default_stencil_path()`. |
| `examples/test_visio_export.py` | 88 | Dependency-free smoke test for Visio classification/model building and MST segment generation. |

## 2. Public API surface

### 2.1 Layout facade and editor

`LayoutOps` is the object attached as `client.layout` (`src_bak/virtuoso_bridge/virtuoso/layout/__init__.py:57-58`). It constructs editors but otherwise delegates (`:63-130`).

| API | Exact signature | Return shape / behavior | Reference |
|---|---|---|---|
| `LayoutOps.__init__` | `(self, owner: VirtuosoClient) -> None` | Stores owner as `_owner`; no operation is executed. | `src_bak/virtuoso_bridge/virtuoso/layout/__init__.py:60-61` |
| `LayoutOps.create` | `(self, lib: str, cell: str, view: str = "layout", timeout: int = 60) -> LayoutEditor` | New `LayoutEditor(..., mode="w")`; entering it opens with mode `w` and replaces/opens the target view for writing. | `:63-71` |
| `LayoutOps.modify` | `(self, lib: str, cell: str, view: str = "layout", timeout: int = 60) -> LayoutEditor` | New `LayoutEditor(..., mode="a")`; entering it binds the matching active edit view or opens it append-mode. | `:73-81` |
| `LayoutOps.edit` | `(self, lib: str, cell: str, view: str = "layout", mode: Literal["a", "w"] = "a", timeout: int = 60) -> LayoutEditor` | Deprecated compatibility wrapper; emits `DeprecationWarning`. | `:83-97` |
| `LayoutOps.export_gds` | `(self, library: str, cell: str, output_path: str \| Path, *, stream_map: str \| Path, view: str = "layout", log_path: str \| Path \| None = None, timeout: float = 300.0, poll_interval: float = 0.5, skill_timeout: float = 30.0, finalization_reserve: float = 30.0, cleanup_policy: Literal["success", "always", "never"] = "success", recovery_hook: Callable[[], object] \| None = None) -> GdsExportResult` | Delegates every argument to `export_gds()` and returns its `GdsExportResult`. | `:99-130` |
| `LayoutEditor.__init__` | `(self, client: VirtuosoClient, lib: str, cell: str, view: str = "layout", mode: str = "a", timeout: int = 60) -> None` | Stores client, target, mode, timeout, and an empty command list. | `src_bak/virtuoso_bridge/virtuoso/layout/editor.py:34-49` |
| `LayoutEditor.__enter__` | `(self) -> LayoutEditor` | In `w` mode appends a direct `open_cell_view(..., mode="w")`; otherwise appends `layout_bind_current_or_open_cell_view(...)`. Returns self. | `:51-61` |
| `LayoutEditor.add` | `(self, skill_cmd: str) -> None` | Appends one SKILL command to the batch. | `:63-65` |
| `LayoutEditor.close` | `(self) -> None` | Appends `close_current_cellview()`. | `:67-69` |
| `LayoutEditor.__exit__` | `(self, exc_type, exc_val, exc_tb) -> None` | On clean exit appends `save_current_cellview()` and executes all commands via `client.execute_operations()`; raises through `ensure_operation_response()` if the batch fails. On exception, sends nothing. | `:71-75` |

Re-exported lifecycle helpers that are part of the layout facade:

| API | Exact signature | Return shape / behavior | Reference |
|---|---|---|---|
| `close_current_cellview` | `() -> str` | SKILL that closes the bound `cv` or `geGetEditCellView()`. | `src_bak/virtuoso_bridge/virtuoso/ops.py:103-108` |
| `clear_current_layout` | `() -> str` | SKILL that makes all layers visible, selects all visible figures, deletes them, and redraws. | `src_bak/virtuoso_bridge/virtuoso/ops.py:111-120` |

Public facade export list: `LayoutOps`, `LayoutEditor`, XStream/streamout names, all layout operation builders, and the parser (`src_bak/virtuoso_bridge/virtuoso/layout/__init__.py:133-172`). `test_layout_streamout.py:471-474` pins the XStream/GDS portion of this contract.

### 2.2 SKILL operation builders (`layout/ops.py`)

Every function in this module returns a `str` containing SKILL source. These are planners, not result models. Callers must execute the string through `execute_skill`/`execute_operations`; the Python return is therefore not a `VirtuosoResult`.

#### Lifecycle and state

| API | Exact signature | Python return; runtime effect/output |
|---|---|---|
| `layout_bind_current_or_open_cell_view` | `(lib: str, cell: str, *, view: str = "layout", view_type: str \| None = None, mode: str = "a") -> str` | SKILL expression assigning `cv`; reuses the active matching edit cellview or opens it. |
| `layout_fit_view` | `() -> str` | SKILL expression; zooms the current window to scale 0.9 or returns `nil`. |
| `layout_set_active_lpp` | `(layer: str, purpose: str = "drawing") -> str` | `pteSetActiveLpp("layer purpose")` expression. |

References: `src_bak/virtuoso_bridge/virtuoso/layout/ops.py:47-74`, `:244-254`.

#### Geometry and instance creation

| API | Exact signature | Python return; runtime effect/output |
|---|---|---|
| `layout_create_param_inst` | `(lib: str, cell: str, view: str, instance_name: str, x: float, y: float, orientation: str, *, cv_expr: str = "cv") -> str` | `dbCreateParamInstByMasterName(...)` expression. |
| `layout_create_simple_mosaic` | `(lib: str, cell: str, *, origin: tuple[float, float] = (0.0, 0.0), orientation: str = "R0", rows: int, cols: int, row_pitch: float, col_pitch: float, view: str = "layout", view_type: str \| None = None, instance_name: str \| None = None, cv_expr: str = "cv") -> str` | Opens the master and emits `dbCreateSimpleMosaic(...)`; name is `nil` when omitted. |
| `layout_create_path` | `(layer: str, purpose: str, points: Iterable[tuple[float, float]], width: float, style: str \| None = None, *, cv_expr: str = "cv") -> str` | `dbCreatePath(...)`; optional style is appended only when non-`None`. |
| `layout_create_rect` | `(layer: str, purpose: str, x0: float, y0: float, x1: float, y1: float, *, cv_expr: str = "cv") -> str` | `dbCreateRect(...)` with two corner points. |
| `layout_create_label` | `(layer: str, purpose: str, x: float, y: float, text: str, justification: str, rotation: str, font: str, height: float, *, cv_expr: str = "cv") -> str` | `dbCreateLabel(...)` with explicit justification, rotation, font, and height. |
| `layout_create_via` | `(via_def_expr: str, x: float, y: float, orientation: str, via_params_expr: str, *, cv_expr: str = "cv") -> str` | `dbCreateVia(...)` using an already-resolved via-def expression. |
| `layout_find_via_def` | `(via_name: str, *, cv_expr: str = "cv") -> str` | SKILL `let` resolving a via definition from the cellview techfile; runtime value is via-def or `nil`. |
| `layout_create_via_by_name` | `(via_name: str, x: float, y: float, orientation: str = "R0", via_params_expr: str = "nil", *, cv_expr: str = "cv") -> str` | Resolves the via-def and calls `dbCreateVia`; the builder adds no Python exception path around the runtime via-def result. |
| `layout_via_def_expr_from_name` | `(via_name: str, *, cv_expr: str = "cv") -> str` | Alias for `layout_find_via_def`; reusable expression. |
| `layout_create_polygon` | `(layer: str, purpose: str, points: Iterable[tuple[float, float]], *, cv_expr: str = "cv") -> str` | `dbCreatePolygon(...)` expression. |

References: `src_bak/virtuoso_bridge/virtuoso/layout/ops.py:76-242`.

#### Layer visibility, highlight, and viewport

| API | Exact signature | Runtime effect/output |
|---|---|---|
| `layout_show_only_layers` | `(layers: Iterable[tuple[str, str]]) -> str` | `progn` that first hides all layers, then shows the requested LPPs. |
| `layout_show_layers` | `(layers: Iterable[tuple[str, str]]) -> str` | `progn` of `pteSetVisible(... t ...)`, or the literal `nil` if the iterable is empty. |
| `layout_hide_layers` | `(layers: Iterable[tuple[str, str]]) -> str` | `progn` of `pteSetVisible(... nil ...)`, or literal `nil` if empty. |
| `layout_highlight_net` | `(net_name: str, *, view: str = "layout", view_type: str \| None = None, mode: str = "a") -> str` | Finds a shape whose `shape~>net~>name` matches, centers on its bbox, unmarks previous net, and calls `leMarkNet`; returns a status string or `"ERROR: net not found: ..."`. |

References: `src_bak/virtuoso_bridge/virtuoso/layout/ops.py:256-303`.

#### Selection, deletion, and cell removal

| API | Exact signature | Runtime effect/output |
|---|---|---|
| `layout_select_box` | `(bbox: tuple[float, float, float, float], *, mode_name: str = "replace", view: str = "layout", view_type: str \| None = None, mode: str = "a") -> str` | Accepts `replace`, `add`, or `sub`/`subtract`/`remove`; invalid mode raises `ValueError`. Returns `"selected N figure(s)"` or `"ERROR: no layout window open"`. |
| `layout_delete_selected` | `(*, view: str = "layout", view_type: str \| None = None, mode: str = "a") -> str` | Counts current selection, calls `leHiDelete()` when non-zero, and returns `"deleted N selected figure(s)"`. |
| `layout_delete_shapes_on_layer` | `(layer: str, purpose: str = "drawing", *, view: str = "layout", view_type: str \| None = None, mode: str = "a") -> str` | Iterates shapes and deletes matching LPP; returns a count and target/cell status string. |
| `layout_clear_routing` | `(*, view: str = "layout", view_type: str \| None = None, mode: str = "a") -> str` | Deletes all shapes, calls `dbSave(cv)`, and returns `"deleted N shape(s) ... (instances preserved)"`. |
| `layout_delete_cell` | `(lib: str, cell: str) -> str` | Saves/closes every window for the lib/cell, `ddDeleteObj` deletes the cell, and returns `"deleted: lib/cell"` or `"ERROR: cell not found: lib/cell"`. |

References: `src_bak/virtuoso_bridge/virtuoso/layout/ops.py:305-348`, `:427-484`.

#### Read and inspect

| API | Exact signature | Runtime output |
|---|---|---|
| `layout_read_summary` | `(lib: str, cell: str, *, view: str = "layout", view_type: str \| None = None) -> str` | Returns a SKILL program whose string contains a layout header, shape lines, rectangle bboxes, and instance lines; unreadable input returns `"ERROR: cannot open ..."`. |
| `layout_read_geometry` | `(lib: str, cell: str, *, view: str = "layout", view_type: str \| None = None) -> str` | Returns a SKILL program whose string is tab-separated `shape` and `instance` records; this is the input expected by `parse_layout_geometry_output`. |
| `layout_list_shapes` | `(*, view: str = "layout", view_type: str \| None = None, mode: str = "a") -> str` | Returns a SKILL program producing one `objType [layer purpose]` line per shape, or `"ERROR: no layout window open"`. |

References: `src_bak/virtuoso_bridge/virtuoso/layout/ops.py:350-425`.

### 2.3 Geometry parser (`layout/reader.py`)

| API | Exact signature | Return shape and parsing rules |
|---|---|---|
| `parse_layout_geometry_output` | `(raw: str) -> list[dict[str, Any]]` | Returns one dict per non-empty line. `kind` is the first tab field; later `key=value` fields become `key: str` or `None` for `nil`. `bbox` becomes a two-point list when four numbers are present; `points` becomes a list of coordinate pairs; `xy` becomes a two-float tuple. Malformed point lists remain the original string. |

References: `src_bak/virtuoso_bridge/virtuoso/layout/reader.py:9-53`.

### 2.4 XStream and GDS result API

#### `GdsExportReason`

String-valued enum with exact values (`src_bak/virtuoso_bridge/virtuoso/layout/streamout.py:55-70`):

`completed`, `xstream_failure`, `xstream_errors`, `request_cleanup_error`, `skill_error`, `launch_indeterminate`, `incomplete_log`, `missing_gds`, `empty_gds`, `malformed_log`, `staging_error`, `transport_error`, `publication_error`.

`GdsExportResult` is a frozen dataclass (`src_bak/virtuoso_bridge/virtuoso/layout/streamout.py:73-100`):

| Field | Type/default |
|---|---|
| `status` | `ExecutionStatus` |
| `reason` | `GdsExportReason` |
| `timed_out` | `bool` |
| `library`, `cell`, `view` | `str` |
| `execution_time` | `float` |
| `local_gds_path` | `Path \| None = None` |
| `local_log_path` | `Path \| None = None` |
| `log_result` | `XStreamLogResult \| None = None` |
| `errors`, `warnings` | tuple-normalized in `__post_init__`; default `()` |
| `remote_run_dir` | `str \| None = None` |
| `local_run_dir` | `Path \| None = None` |
| `remote_files_retained` | `bool \| None = None` |
| `ok` property | `status == ExecutionStatus.SUCCESS` |

`export_gds` exact signature (`src_bak/virtuoso_bridge/virtuoso/layout/streamout.py:726-741`):

```python
def export_gds(
    client: object,
    library: str,
    cell: str,
    output_path: str | Path,
    *,
    stream_map: str | Path,
    view: str = "layout",
    log_path: str | Path | None = None,
    timeout: float = 300.0,
    poll_interval: float = 0.5,
    skill_timeout: float = 30.0,
    finalization_reserve: float = 30.0,
    cleanup_policy: CleanupPolicy = "success",
    recovery_hook: Callable[[], object] | None = None,
) -> GdsExportResult
```

`streamout.__all__` is exactly `["GdsExportReason", "GdsExportResult", "export_gds"]` (`src_bak/virtuoso_bridge/virtuoso/layout/streamout.py:2955`).

#### XStream models and pure helpers

| API | Exact signature / fields | Return shape |
|---|---|---|
| `XStreamExportRequest` | Frozen dataclass fields `library`, `top_cell`, `view`, `stream_file`, `layer_map`, `log_file`, `run_dir`, all `str`. | Execution-host request descriptor. |
| `XStreamTranslatedStructure` | Frozen dataclass fields `library`, `cell`, `view`, `structure`, all `str`. | One cellview-to-GDS mapping. |
| `XStreamLogResult` | Frozen dataclass fields `completed: bool`, `completion_line: str \| None`, `error_count: int \| None`, `warning_count: int \| None`, `translated_structures: tuple[...]`, `warnings`, `errors`, `terminal_failures`, `parse_errors`, `current_run_text`. | Parsed current-run log. |
| `xstream_export_gds_skill` | `(request: XStreamExportRequest) -> str` | SKILL text that captures/restores XStream fields and calls `xstOutDoTranslate()`. |
| `parse_xstream_log` | `(text: str) -> XStreamLogResult` | Parses the newest run selected by the last product header/start anchor; raises `TypeError` for non-string input. |

References: `src_bak/virtuoso_bridge/virtuoso/layout/xstream.py:77-112`, `:122-269`. The renderer validates all seven request values as non-empty strings (`:125-129`), captures all old values before mutation (`:137-149`), restores fields under `unwindProtect` (`:159-190`), and returns `("xstreamRequest", "started", ...)` or `("xstreamRequest", "failed", ...)`. Terminal markers are bounded matches for `XSTRM-273`, `Translation failed`, and `OPEN_FAILED` (`:60-73`).

### 2.5 Visio API (`virtuoso/visio.py`)

| API | Exact signature / fields | Return shape |
|---|---|---|
| `Point` / `Segment` | `tuple[float, float]` / `tuple[Point, Point]` type aliases. | Geometry aliases. |
| `default_stencil_path` | `() -> Path \| None` | First existing candidate among `./circuit.vss`, `./examples/circuit.vss`, and `<repo>/examples/circuit.vss`. |
| `PinSpec` | Frozen dataclass: `name: str`, `rel_x: float`, `rel_y: float`. | Relative master pin location. |
| `DeviceSpec` | Frozen dataclass: `device_type`, `master_name`, `size`, `pins`, `name_prefixes=()`, `cell_keywords=()`. | Device-to-master mapping. |
| `VisioPin` | Frozen dataclass: `instance`, `name`, `net`, `x`, `y`. | Placed terminal. |
| `VisioInstance` | Frozen dataclass: `name`, `lib`, `cell`, `device_type`, `master_name`, `x`, `y`, `width`, `height`, `orient="R0"`, `pins={}`. | Placed instance. |
| `VisioNet` | Frozen dataclass: `name`, `pins`, `segments`. | Net and its routed segments. |
| `VisioSchematic` | Frozen dataclass: `instances`, `nets`. | Complete export model. |
| `classify_instance` | `(inst: Mapping[str, Any], library: Sequence[DeviceSpec] = DEFAULT_DEVICE_LIBRARY) -> DeviceSpec` | Cell keyword first, then longest matching instance-name prefix, else `UNKNOWN_DEVICE`. |
| `build_visio_schematic` | `(schematic: Mapping[str, Any], *, scale: float = 1.0, library: Sequence[DeviceSpec] = DEFAULT_DEVICE_LIBRARY, exclude_nets: Iterable[str] = (), exclude_pins: Iterable[str] = ("B",), include_single_pin_nets: bool = False) -> VisioSchematic` | Builds placed instances/pins and Manhattan MST segments. |
| `export_schematic_to_visio` | `(client: Any, lib: str \| None = None, cell: str \| None = None, *, output_path: str \| Path \| None = None, stencil_path: str \| Path \| None = None, visible: bool = True, scale: float = 1.0, exclude_nets: Iterable[str] = (), exclude_pins: Iterable[str] = ("B",)) -> VisioSchematic` | Calls legacy `read_schematic()`, builds the model, draws it in Visio, and returns the model. |
| `export_model_to_visio` | `(model: VisioSchematic, *, output_path: str \| Path \| None = None, stencil_path: str \| Path \| None = None, visible: bool = True) -> None` | Requires Windows/pywin32 and a valid stencil; draws masters/lines and optionally saves. |
| `minimum_spanning_segments` | `(points: Sequence[Point]) -> list[Segment]` | Manhattan-distance MST edges; empty for fewer than two points. |

References: `src_bak/virtuoso_bridge/virtuoso/visio.py:30-115`, `:230-321`, `:324-420`, `:423-452`. Public constants are `UNKNOWN_DEVICE` and `DEFAULT_DEVICE_LIBRARY` (`:118-227`).

### 2.6 Example entrypoints and CLI contracts

| File | Public functions | CLI/input contract |
|---|---|---|
| `add_power_labels.py` | `main() -> int` (`:112`) | `--target-lib`, `--cell` required; defaults `VDD`, `VSS`, `M1/pin`, `roman`, height `1.0`, fallback lib `tcbn28hpcplusbwp12t30p140`, label x `0.0`. |
| `digital_import.py` | `run(name: str, argv: list[str]) -> None`, `sram_exists(client, lib, cell) -> bool`, `detect_sram_cells(client, verilog_path) -> list[str]`, `main() -> int` | `--top`, `--target-lib` required; optional `--sram-cell`, `--gds`, `--verilog`; lab roots come from `VB_DIG_SYN_ROOT`/`VB_SRAM_ROOT` or hardcoded defaults. |
| `import_gds.py` | `main() -> int` | Positional `gds`; required `--target-lib`; optional `--tech-lib` (default `tsmcN28`), mutually exclusive `--ref-libs`/`--use-cds-lib`, `--cell`. |
| `import_verilog.py` | `main() -> int` | Positional `verilog`; required `--target-lib`; options for ref libs, schematic/symbol names, power/ground nets, structural-view mode, leaf-cell import, and cell override. |
| `restyle_labels.py` | `parse_floorplan_pin_sides(fp_tcl_path: str) -> dict[str, str]`, `main() -> int` | Required `--target-lib`, `--cell`; height/font/justify, edge orientation controls, and optional `--floorplan-tcl`. |
| `01_create_layout.py` ... `15_export_gds.py` | Each has `main() -> int`. | All are scripts; `15_export_gds.py` has the stable JSON result contract. |
| `flower.py` | `ellipse_pts(cx, cy, a, b, angle, n=28) -> list[tuple[float, float]]`, `main() -> int` | Requires one library argument, then creates polygon/path/label geometry. |
| `examples/test_visio_export.py` | `main() -> int` | Smoke-check only; never launches Visio. |

References: `examples/01_virtuoso/digital_import/add_power_labels.py:112-160`, `digital_import.py:67-229`, `import_gds.py:42-279`, `import_verilog.py:81-253`, `restyle_labels.py:53-249`; `examples/01_virtuoso/layout/flower.py:68-156`; `examples/test_visio_export.py:15-83`.

### 2.7 Standalone SKILL asset contract

`examples/01_virtuoso/assets/layout_ops.il` exposes these legacy procedures: `_LayoutGetEditCV()`, `LayoutReadLayout(libName cellName)`, `LayoutListShapes()`, `LayoutSave()`, `LayoutDeleteShapesOnLayer(layer purpose)`, `LayoutClearRouting()`, and `LayoutDeleteCell(libName cellName)` (`examples/01_virtuoso/assets/layout_ops.il:16-101`). They are the older standalone equivalent of the Python builders in `ops.py` and must be treated as a compatibility contract if existing users load the asset directly.

## 3. Capability decomposition

The middle-interface names below are the five architectural interfaces: Skill, command, file (upload/download), GUI command, and Spectre command. “Command” means `run_command`, not a legacy `csh()`/`system()` call hidden in SKILL.

### 3.1 Create or replace a layout cellview

- Business inputs: library, cell, view (default `layout`), optional timeout; then a list of shape/instance operations.
- Business outputs: a saved `LayoutEditor`-managed cellview; the context manager itself returns no domain object.
- Sub-steps: create editor with mode `w` (`__init__.py:63-71`), enter context and append `open_cell_view(..., mode="w")` (`editor.py:51-60`), append SKILL operations, append save on clean exit (`editor.py:71-74`), execute the batch (`editor.py:74-75`).
- Middle interfaces: Skill only. In the new layer this should be one or more `execute_skill` calls; the old `client.execute_operations()` convenience method should not be carried upward.
- Important behavior: mode `w` deliberately avoids silently reusing an already-open cellview (`editor.py:52-54`).

### 3.2 Modify an existing layout or append shapes

- Business inputs: library, cell, view, timeout, and a batch of geometry/instance commands.
- Business outputs: modified saved cellview.
- Sub-steps: construct `LayoutEditor(mode="a")` (`__init__.py:73-81`), bind the matching active edit cellview or open it append-mode (`editor.py:55-60`), append operations, save on clean exit.
- Middle interfaces: Skill only.
- Risks: “current active cellview” is process-global Virtuoso state. New upper-layer packages should pass explicit target identity and avoid relying on an ambient CIW selection unless the middle exposes that as an explicit business precondition.

### 3.3 Add polygons, rectangles, paths, labels, parameterized instances, and mosaics

- Business inputs: layer/purpose, coordinate points or rectangle corners, path width/style, label text/font/justification/height, master lib/cell/view, instance name/orientation, mosaic dimensions/pitches.
- Business outputs: SKILL execution results; geometry remains remote in Virtuoso and is not returned as a Python object.
- Sub-steps: build a SKILL expression (`ops.py:76-242`), attach it to a `LayoutEditor` or execute it against an explicit `cv_expr`, save the cellview when modifying persistent data.
- Middle interfaces: Skill only.
- Planning examples: `flower.py:68-149` is pure Python ellipse-to-polygon geometry; `01_create_layout.py:111-122` composes rectangle/path/label/instance builders; `05_bus_routing.py:67-83` composes repeated paths and labels.
- Re-development contract: keep coordinate planning pure Python, but treat every `dbCreate*` call as a Skill round trip. Do not move file/geometry math into the middle layer.

### 3.4 Via definition and via creation

- Business inputs: via name or via-def expression, x/y, orientation, optional via-parameter expression.
- Business outputs: via object or `nil` from the SKILL `dbCreateVia` call.
- Sub-steps: resolve a via definition through `techGetTechFile`/`techFindViaDefByName` (`ops.py:199-207`); then call `dbCreateVia` (`ops.py:184-197`, `:209-224`); alternatively reuse a previously resolved expression (`ops.py:226-228`).
- Middle interfaces: Skill only.
- Re-development risk: via-name resolution depends on the current cellview’s techfile and therefore on `cv_expr`/target-cell state.

### 3.5 Multilayer routing and bus routing

- Business inputs: layers, path coordinates, widths, spacing/pitch, bit count, label layer/font/height.
- Business outputs: one path per layer/bit plus optional labels; no high-level router abstraction exists in the legacy package.
- Sub-steps: Python loops calculate coordinates (`04_multilayer_routing.py:51-55`, `05_bus_routing.py:67-83`), then each path/label is emitted as a SKILL operation and saved through the editor.
- Middle interfaces: Skill only.
- Re-development opportunity: model “route”, “bus route”, and “bit label” as upper-layer planning objects, but preserve the primitive `dbCreatePath`/`dbCreateLabel` contracts.

### 3.6 Read, list, and summarize layout geometry

- Business inputs: lib/cell/view, or an explicit target layout for the “current window” variants.
- Business outputs:
  - formatted summary string (`layout_read_summary`, `ops.py:350-377`);
  - tab-separated geometry dump (`layout_read_geometry`, `ops.py:379-407`);
  - `list[dict[str, Any]]` from `parse_layout_geometry_output` (`reader.py:32-53`);
  - one `objType [layer purpose]` line per shape (`layout_list_shapes`, `ops.py:409-425`).
- Sub-steps: Skill opens the read-only cellview or finds the active layout, traverses `cv~>shapes` and `cv~>instances`, and returns a string; Python parses line-oriented output.
- Middle interfaces: Skill; the parser remains pure Python.
- Important behavior: `06_read_layout.py:41-52` first uses `result.metadata["geometry"]` when present and otherwise reparses `result.output`. That metadata dependency is not part of the normative middle contract and must be replaced or made optional.

### 3.7 Layer visibility, active LPP, and viewport control

- Business inputs: iterable of `(layer, purpose)` pairs, layer/purpose for active LPP, or no input for fit-view.
- Business outputs: updated GUI palette/window state, not layout data.
- Sub-steps: hide all then show requested LPPs (`ops.py:256-262`); show or hide selected LPPs (`:264-277`); set active LPP (`:252-254`); fit current window (`:244-250`).
- Middle interfaces: Skill in the legacy implementation. These functions call `pteSet*`/`hiZoomAbsoluteScale`, so they mutate the GUI session. A new design must decide whether they remain Skill (because they are SKILL CUI/editor APIs) or move to `run_gui_command`; the normative role table assigns X11/window commands to `gui` (`spec/design-concepts/中层/3-路由设计.md:42-48`), but these are currently invoked through the daemon.
- Re-development risk: palette state is not tied to the target lib/cell and can affect the user’s active window.

### 3.8 Select and delete shapes, clear routing, or delete a cell

- Business inputs: bbox and selection mode; target layer/purpose; or lib/cell for deletion.
- Business outputs: status strings with counts, or a cell deletion result.
- Sub-steps:
  - `layout_select_box`: normalize mode to replace/add/subtract, call `geDeselectAllFig`, `geSelectArea`, `geAddSelectBox`, or `geDeselectArea` (`ops.py:305-331`).
  - `layout_delete_selected`: count selection and call `leHiDelete()` (`:333-348`).
  - `layout_delete_shapes_on_layer`: iterate and `dbDeleteObject` matching LPP (`:427-449`).
  - `layout_clear_routing`: delete all shapes while preserving instances, then `dbSave` (`:451-467`).
  - `layout_delete_cell`: save/close matching windows and `ddDeleteObj` (`:469-484`).
  - `clear_current_layout`: make all layers visible, select all visible figures, delete, redraw (`src_bak/virtuoso_bridge/virtuoso/ops.py:111-120`).
- Middle interfaces: Skill only.
- Test/example evidence: `07_delete_shapes_on_layer.py:37-53`, `08_clear_routing.py:25-30`, `09_clear_current_layout.py:26-35`, `10_delete_cell.py:26-37`, `13_select_and_delete.py:53-74`.

### 3.9 Export GDS with XStream Out

- Business inputs: `library`, `cell`, `output_path`, required local `stream_map`, `view`, optional `log_path`, timeout controls, cleanup policy, recovery hook.
- Business outputs: `GdsExportResult` with status/reason/timing, local GDS/log paths when published, parsed `XStreamLogResult`, diagnostics, remote/local run directory, and retention flag.
- Sub-steps:
  1. Validate names, paths, numeric controls, reserve < timeout, and cleanup policy (`streamout.py:519-586`).
  2. Build a time budget with separate prefinalization/finalization deadlines (`:615-654`).
  3. Choose remote versus local implementation solely from `client.ssh_runner` (`:761-776`).
  4. Remote: resolve username, choose an owned scratch directory, create a private UUID run directory, upload the stream map, launch XStream via Skill, poll artifacts/digests, download and stabilize the log before GDS, publish log then GDS with atomic replacement, discard unvalidated GDS, optionally clean remote staging (`:779-1010`, `:1312-1865`).
  5. Local: create `.<output>.xstream-<uuid>` beside the output, execute XStream using absolute local paths, poll the local log/GDS, publish a stable log before a stable GDS, and apply local cleanup policy (`:1971-2108`, `:2325-2746`).
- Middle interfaces: Skill (XStream API), command (remote sentinel/staging/cleanup commands), file (stream-map upload and log/GDS download). No GUI or Spectre command is used.
- Important distinction: the file is named `streamout.py`, but there is no direct shell invocation of `strmout`. The implementation calls `xstOutDoTranslate()` through SKILL (`xstream.py:122-195`).

### 3.10 Import GDS with strmin and layer/reference mapping

- Business inputs: GDS path visible to or uploadable to Virtuoso’s working directory; target library already defined in `cds.lib`; tech library; explicit reference-library file (`--ref-libs`) or unsafe `XST_CDS_LIB`; optional cell override.
- Business outputs: a `layout` view in the target OA library, plus a verification string containing instance count, shape count, and bbox.
- Sub-steps: verify the target library through `ddGetObj`, get `getWorkingDir()`, stage local GDS/ref-lib files to that workdir, compose the strmin command, invoke it through legacy `system()`, then poll `strmIn.log` and the target cellview (`import_gds.py:99-279`).
- Middle interfaces: Skill (workdir/cds.lib checks and verification), command (`strmin`), file (upload when the input exists locally).
- Critical polling rule: do not read the imported bbox until `XSTRM-234`/`Translation completed` appears, because a re-import can expose a stale old layout immediately (`import_gds.py:205-218`, `:246-267`). Fail fast on `XSTRM-273` plus `Translation failed` instead of waiting the full 600 s (`:238-259`).
- Reference mapping: the command passes either a file to `-refLibList` or `XST_CDS_LIB`; the README warns that broad cds.lib reference sets can silently bind to the wrong same-name cell and produce zero translated objects (`examples/01_virtuoso/digital_import/README.md:47-89`).

### 3.11 Import structural Verilog/digital flow with ihdl

- Business inputs: structural Verilog path, target library, reference libraries, schematic/symbol view names, power/ground nets, structural-view mode, optional leaf-cell import, optional verification cell.
- Business outputs: schematic/symbol/functional views and a final verification line with instance/net/terminal counts.
- Sub-steps: verify target library, discover workdir, stage local Verilog there, generate `ihdl_parameter` and `-f` response files via SKILL `outfile`, run `ihdl` through `system()`, refresh library state, verify requested schematic or fallback `functional` view (`import_verilog.py:134-252`).
- Middle interfaces: Skill (`.il` file writing, cds.lib checks, verification), command (`ihdl`), file (Verilog upload).
- Critical gap: unlike the GDS path, the Verilog path trusts the `system()` integer result and does not poll or tail `verilogIn.batch.log` (`import_verilog.py:200-219`). This is directly inconsistent with the documented false-failure behavior in `examples/01_virtuoso/digital_import/README.md:94-113`.

### 3.12 Add power/ground labels after GDS import

- Business inputs: target lib/cell, power and ground terminal names, label texts, label LPP, font/height, fallback library, optional forced X coordinate.
- Business outputs: two labels at transformed power/ground rail centers, saved into the layout.
- Sub-steps: open the layout for edit; select the first instance whose master has both terminals, optionally falling back to a library when the imported master lacks terminals; read terminal pin bboxes; transform point centers through `ref~>xy`/`ref~>orient`; choose x as explicit override or layout bbox midpoint; create labels; save (`add_power_labels.py:40-108`).
- Middle interfaces: Skill only, plus a redraw Skill call (`:150-159`).
- Re-development risk: the fallback-library default is lab-specific and the “first instance with both pins” convention is not explicit semantic matching.

### 3.13 Restyle labels and orient edge pins

- Business inputs: target lib/cell, text-label height/layer, pin-label height/font/justification, edge heuristic controls, optional Innovus floorplan Tcl.
- Business outputs: saved label height/font/justification/orientation and a summary count string.
- Sub-steps: pure-Python parse of `editPin -side` blocks and Tcl brace nesting (`restyle_labels.py:53-104`); build a SKILL makeTable mapping pin names to orientations (`:107-115`); one SKILL traversal classifies labels by `layerName/purpose`, applies formatting, gives map-driven orientation priority, then applies bbox-distance orientation fallback (`:180-243`); save and return summary (`:235-248`).
- Middle interfaces: Skill only. The floorplan parser is pure upper-layer Python.
- Important behavior: bus bracket conversion from `name[i]` to `name<i>` matches strmin’s `-replaceBusBitChar` behavior (`:95-103`).

### 3.14 Export a schematic to Visio/VSDX

- Business inputs: schematic lib/cell or pre-read schematic data, scale, excluded nets/pins, output path, stencil path, visibility.
- Business outputs: `VisioSchematic` model and optionally a saved Visio document.
- Sub-steps: `read_schematic()` through legacy client (`visio.py:338-340`), pure model build (`:341-346`), Visio COM application/stencil/masters/instance/line drawing (`:370-420`), optional `SaveAs`.
- Middle interfaces: Skill for `read_schematic`; GUI/command for launching or controlling a local Windows Visio helper if the new architecture supports it. The current code uses in-process `win32com`, not the five interfaces, so this is not directly portable.

### 3.15 One-shot digital import pipeline

- Business inputs: top cell, target library, optional GDS/Verilog/SRAM overrides; roots come from environment or hardcoded lab paths.
- Business outputs: a sequence of imported/modified cellviews and a final success line.
- Sub-steps: optionally probe Verilog path via Skill `isFileReadable` (`digital_import.py:151-163`), detect SRAM names with local regex or remote grep (`:83-121`), pre-import SRAM, run `import_gds.py`, run `import_verilog.py`, run power-label and restyle scripts (`:182-226`).
- Middle interfaces in the target design: Skill, command, and file; the legacy implementation additionally uses local `subprocess.run()` (`:67-75`) and environment variables (`:45`, `:63-64`), both of which are forbidden in the new upper layer.

## 4. External tool orchestration

### 4.1 Orchestration matrix

| Tool/flow | Exact command or invocation shape | Required staging | Expected artifacts | Logs | Terminal failure / completion markers | Timeout and polling |
|---|---|---|---|---|---|---|
| XStream Out GDS export | SKILL `xstGetField`/`xstSetField` + `xstOutDoTranslate()`; remote path selection then remote shell sentinel commands | Local `stream_map` must exist and is uploaded as `stream.map` in remote mode | `output.gds`, `xstream.log`, `stream.map` under UUID run dir | run-dir `xstream.log`; local published log path | failure: `XSTRM-273`, `Translation failed`, `OPEN_FAILED`; completion: `XSTRM-234` + `Translation completed` with error/warning counts | budget-based: total `timeout=300`, prefinal reserve `30`, `skill_timeout=30`, poll `0.5`; remote poll tail up to 128 KiB; local reads whole log snapshots |
| `strmin` GDS import | `strmin -library <target_lib> -strmFile <gds> -attachTechFileOfLib <tech_lib> -logFile strmIn.log [-refLibList XST_CDS_LIB\|<file>] -replaceBusBitChar` via legacy `system()` | Local GDS and ref-lib file are uploaded to `getWorkingDir()/<basename>` and rewritten to basenames when they exist locally | target `<lib>/<cell>/layout` OA cellview | `<virtuoso_workdir>/strmIn.log` | failure: `XSTRM-273` + `Translation failed`, ideally an `ERROR ... XSTRM` line; completion: `XSTRM-234` + `Translation completed` | 600 s total, 3 s poll, log scanned every iteration; bbox verified only after completion |
| `ihdl` Verilog import | `cd <virtuoso_workdir> && ihdl -cdslib <workdir>/cds.lib -f </tmp/vb_ihdl_files_<id>> <verilog>` via legacy `system()` | Local Verilog uploaded to workdir/basename; parameter and files files written on remote host via SKILL `outfile` | target schematic/symbol/functional views; `verilogIn.batch.map.table` | `<virtuoso_workdir>/verilogIn.batch.log` | `OPEN_FAILED` in the SKILL verifier; raw log can also contain file-open failures | no polling and no explicit timeout; trusts `system()` integer return. Documented false `''` result is not handled |
| SRAM detection in `digital_import.py` | `grep -hoE 'TS1N28[A-Z0-9]+' <verilog> \| sort -u > /tmp/vb_sram_detect_<pid>.out` via legacy `system()` | None if reading a local file; remote Verilog path otherwise | `/tmp/vb_sram_detect_<pid>.out`, read back via SKILL `infile`/`gets` | none | no dedicated sentinel | no polling; one system call then one file-read Skill call |
| Local pipeline driver | `python <subprocess argv>` for `import_gds.py`, `import_verilog.py`, `add_power_labels.py`, `restyle_labels.py` | Creates local temp files `_digital_import_reflibs.txt`, `_digital_import_empty_ref.txt` in `tempfile.gettempdir()` | child-process outputs; no artifact collection in the driver | child stdout/stderr is inherited | nonzero child return code | no `subprocess` timeout |
| Visio COM export | `win32com.client.Dispatch("Visio.Application")`; `Documents.Add("")`; `Documents.OpenEx(stencil, 64)`; `page.Drop`; `page.DrawLine`; `ActiveDocument.SaveAs` | `circuit.vss` must exist locally; model/stencil must contain all required masters | `.vsdx`/Visio document if `output_path` is supplied | none | `RuntimeError` for missing pywin32, missing stencil, or missing masters | no timeout or polling |
| X11 GUI tools | None directly in the scoped layout code. Window enumeration is performed through SKILL `hiGetWindowList()` inside `layout_delete_cell`, `layout_fit_view`, `clear_current_layout`, and the power-label redraw | None | window state/redraw | none | no shell-level sentinel | synchronous Skill calls |

### 4.2 XStream details

The XStream renderer is pure Python (`xstream.py:122-195`) but the execution is a Skill call. It sets seven fields plus `showCompletionMsgBox=false`, captures all old values first, calls `xstOutDoTranslate()`, and restores fields in an `unwindProtect` cleanup block. The wire response is one of:

```text
("xstreamRequest" "started" nil <cleanup-failures>)
("xstreamRequest" "failed" <body-error> <cleanup-failures>)
```

The remote implementation creates a private root/run directory with `umask 077`, `mkdir -m 700`, and ownership/mode checks (`streamout.py:194-267`). It uploads the stream map (`:878-910`), launches the Skill request (`:912-934`), and polls artifacts with a random `VBXSTREAM_<hex>` frame (`:295-379`, `:1150-1178`). Each poll probes:

- `wc -c` log size and, during finalization, an optional `sha256sum`/`shasum`/`openssl` log digest;
- `tail -c 131073`, then `tail -n 200`, then at most 128 KiB of tail text;
- `wc -c` GDS size and optional GDS SHA-256 when present.

The shell parser rejects malformed/oversized frames, requires both log status and GDS status, and enforces digests during finalization (`streamout.py:382-516`). The log parser detects terminal failures independently of completion (`xstream.py:198-269`). The test suite pins the exact sentinel protocol, digest fallbacks, frame bounds, missing-artifact exit-zero behavior, and malformed-output failures (`test_bak/test_layout_streamout.py:559-884`).

Remote publication order is explicitly log-before-GDS, with revalidation and atomic replacement (`streamout.py:1312-1520`, `:1523-1865`). A stable log is downloaded, parsed, and published first; a stable GDS is downloaded/hashed, the remote log and GDS fingerprints are checked again, and only then is the GDS published (`:1593-1781`). If GDS is present but not publishable, the remote GDS is deleted or retained according to safety checks (`:1833-1848`, `:1881-1968`). `cleanup_policy` controls whether remote staging is retained (`:1836-1848`).

Local mode uses the direct filesystem rather than the file-transfer interface: it creates a sibling staging directory (`output_path.parent / ".<name>.xstream-<uuid>"`), writes `output.gds`/`xstream.log` there, polls the filesystem, publishes the stable log first, and then publishes the GDS (`streamout.py:1971-2108`, `:2325-2746`). This is exactly the part that must be re-expressed over `upload_file`/`download_file`/`run_command` without inspecting `ssh_runner`.

### 4.3 strmin details

`import_gds.py` has the strongest example of the known fork-and-write-to-log race:

- It explicitly says the `system()` return is unreliable and that a prior sequential strmin can still be running (`import_gds.py:167-173`).
- It stages local GDS/ref-lib inputs to Virtuoso’s working directory (`:112-145`), because strmin resolves relative paths from Virtuoso’s cwd (`:112-117`).
- It runs `strmin` through `system()` rather than a command-role shell (`:173`).
- It reads `strmIn.log` through SKILL `infile`/`gets` on every loop because `run_shell_command` does not expose stdout (`:219-244`).
- It treats `XSTRM-273` plus `Translation failed` as a fast terminal failure and prints the first `ERROR ... XSTRM` line (`:238-242`).
- It waits for `XSTRM-234` plus `Translation completed` before opening the cellview, specifically to avoid stale-import bbox reads (`:205-218`, `:260-267`).
- It refreshes the library list and polls every 3 s for up to 600 s (`:246-279`).
- The exact verification shape is `instances=%d shapes=%d bbox=%L` (`:182-193`).

This is the required model for new upper-layer polling: do not trust command return codes for strmin, poll for the artifact/cellview, and tail/read the tool log for `XSTRM-273`/`Translation failed` on every poll.

### 4.4 ihdl details

`import_verilog.py` writes two remote temporary files with SKILL output:

- `/tmp/vb_ihdl_param_<8-hex>` contains the parameter template (`import_verilog.py:43-59`, `:177-193`).
- `/tmp/vb_ihdl_files_<8-hex>` contains `-param /tmp/vb_ihdl_param_<id>` (`:190-198`).

The command is:

```text
cd <virtuoso_workdir> && ihdl -cdslib <virtuoso_workdir>/cds.lib \
  -f /tmp/vb_ihdl_files_<id> <verilog>
```

The code parses `system()` output as an integer and exits on nonzero (`:200-219`). It then verifies the requested schematic view and falls back to `functional` (`:224-252`). It does not read `verilogIn.batch.log`, despite the README documenting that the bridge can return an empty/false `system()` result while `ihdl` continues running (`examples/01_virtuoso/digital_import/README.md:94-113`). A new wrapper should add the same artifact-plus-log dual-defense used by the GDS importer.

### 4.5 Local pipeline and environment assumptions

`digital_import.py` is a local Python orchestrator, not a middle-layer command:

- It sets `MSYS_NO_PATHCONV=1` in the process environment (`digital_import.py:42-45`).
- It uses `subprocess.run([sys.executable, *argv], cwd=SCRIPT_DIR)` with no timeout (`:67-75`).
- It writes local staging files into `tempfile.gettempdir()` (`:51-52`, `:187-201`).
- It reads `VB_DIG_SYN_ROOT` and `VB_SRAM_ROOT`, with hardcoded `/home/zhangz/...` fallbacks (`:58-64`).
- It uses local `Path.exists()`/`read_text()` for SRAM detection when the Verilog exists locally, otherwise uses remote `grep` through Skill (`:83-121`).
- It probes remote Verilog candidates with SKILL `isFileReadable()` (`:146-163`).

In the new architecture, subprocess spawning, environment mutation, and knowledge of whether a path is local versus remote are all upper-layer boundary violations. These must become explicit parameters plus `run_command`/file-interface steps, with environment setup owned by the middle role configuration.

### 4.6 Visio details

`export_model_to_visio` imports `win32com.client`, dispatches `Visio.Application`, opens the stencil with `Documents.OpenEx(..., 64)`, drops masters by name, sets width/height/orientation, draws orthogonal line segments, and optionally saves (`visio.py:370-420`). Missing masters are fatal (`:390-402`). The stencil is resolved by `default_stencil_path()` from the current directory, `./examples`, or the repository root (`:34-45`). The exporter is intentionally split so the model builder remains testable without Visio (`:6-21`, `:356-368`). There is no shell command, timeout, polling, or log parsing in this path.

## 5. Pure-Python vs SKILL vs external-tool split

| Artifact | Pure Python | SKILL round trip | External command/application |
|---|---|---|---|
| `layout/ops.py` | All argument formatting, validation of selection mode, and SKILL string construction. | Every returned string is a `db*`, `ge*`, `hi*`, `le*`, or `pte*` call executed in Virtuoso. | None. |
| `layout/editor.py` | Batch list and context-manager control flow. | `open_cell_view`, `layout_bind_current_or_open_cell_view`, `save_current_cellview`, and `close_current_cellview` all become Skill calls through `execute_operations`. | None. |
| `layout/reader.py` | Entire parser and numeric/string coercion. | None. | None. |
| `layout/xstream.py` | Request validation/escaping, SKILL renderer, newest-run selection, log parsing, marker/count parsing. | The rendered `xst*` code is Skill. | None. |
| `layout/streamout.py` | Validation, budget math, local/remote path planning, result classification, polling loop, digest checks, log parsing, publication planning. | XStream is launched through `xst*` Skill and success is derived from the XStream log. | Remote polling/staging/cleanup shell commands; local OS file operations; legacy `subprocess.TimeoutExpired` exception handling. |
| `visio.py` | Device classification, pin geometry, Manhattan MST, orthogonal splitting, stencil discovery. | `read_schematic()` is a Skill round trip in `export_schematic_to_visio`. | In-process Windows Visio COM/pywin32 drawing and save. |
| `import_gds.py` | Argument validation, path-mangling warning, ref-lib staging decisions, command construction, log parsing. | `ddGetObj`, `getWorkingDir`, `ddUpdateLibList`, file reads, and verification. | `strmin` via `system()`. |
| `import_verilog.py` | CLI/defaults, parameter content, command construction, view verification. | cds.lib checks, workdir discovery, `outfile` writes, verification. | `ihdl` via `system()`. |
| `digital_import.py` | SRAM regex, local path probing, pipeline sequencing. | `isFileReadable`, existence checks, remote grep/read fallback. | Local `subprocess.run()` calls and hardcoded environment/root assumptions. |
| `restyle_labels.py` | Innovus floorplan side parser, brace/token handling, orientation map construction. | Label classification, label mutation, orientation, save. | None. |
| `flower.py` | Ellipse sampling and polygon planning. | Polygon/path/label creation and fit-view. | None. |
| `examples/circuit.vss` | None. | None. | Visio stencil consumed by COM. |

There is no Spectre dependency in the scoped layout/GDS/Visio flow. `run_spectre_command` should not be used for these capabilities unless a future business package adds simulation.

## 6. State/files/IPC dependencies and re-development risks

| Dependency | Where it appears | Why it is not valid in the new upper layer | Re-development direction |
|---|---|---|---|
| `VirtuosoClient` / attached `client.layout` | `layout/__init__.py:57-130`, `editor.py:34-75` | Upper code must depend on the middle protocol, not a concrete client object. | Inject `Middle` (or a small typed adapter) and call `execute_skill`. |
| `client.execute_operations` | `editor.py:74-75` | This is a legacy client convenience and composes commands inside the client, bypassing the five-interface seam. | Compose SKILL text in the upper package or use one `execute_skill` per logical action. |
| `client.ssh_runner` and runner object | `streamout.py:761-776`, `:785-830`, `:850-854` | The new upper layer cannot inspect SSH/tunnel state or choose local/remote based on it. | Require explicit local/server paths or role-aware path values in the business API; let middle roles handle delivery. |
| Direct remote command strings | `streamout.py:248-379`, `:850-854`, `:1881-1968` | Building shell commands with `shlex.quote`, `mkdir`, `tail`, `sha256sum`, `rm`, and POSIX privacy checks is lower-layer transport/orchestration detail. | Call `run_command` with a business-level command contract; keep shell constructs inside middle or a deliberately owned adapter. |
| `client.upload_file` / `client.download_file` | `streamout.py:878-883`, `:1230-1235`; examples | Legacy methods return the old response model, not the new `CommandResult(kind=...)` contract. | Check `returncode`, `kind`, stdout/stderr, and implement staged transfers explicitly. |
| Legacy response normalization | `streamout.py:21-34`, `:1013-1024`, `:2111-2131` | The code accepts objects or dicts and reaches into `.status`, `.errors`, `.warnings`, `.output`; new `VirtuosoResult`/`CommandResult` have a fixed contract. | Normalize once in an upper helper and forbid dict/legacy-object fallbacks. |
| Legacy `ExecutionStatus` | `streamout.py:21`, `:77-100`; tests | New `VirtuosoResult` has its own `ExecutionStatus`, but middle error/timeout semantics are normative and must not be inferred from legacy transport text. | Map middle result status/kind into business reason enums without relying on SSH details. |
| `system()` / `csh()` hidden in SKILL | `import_gds.py:173`, `:225-232`; `import_verilog.py:74`, `:209`; `digital_import.py:101` | The specification explicitly forbids upper code from disguising command-line invocation as Skill (`spec/.../1-四层整体架构与接口.md:136`). | Use `run_command` for strmin/ihdl/grep/tool calls; reserve Skill for actual Virtuoso/SKILL APIs. |
| Local `subprocess.run` | `digital_import.py:35-40`, `:67-75` | Upper layer cannot own process launching. | Model the pipeline as a sequence of middle command/file/skill calls, or expose one business package with explicit stages. |
| `win32com.client` dispatch | `visio.py:370-385` | In-process COM is neither a command-role nor a Skill call; it requires local Windows state. | Define an explicit GUI command helper or a separate adapter with a documented port, or defer Visio support. |
| Hardcoded environment variables and roots | `digital_import.py:42-45`, `:58-64`; Visio paths `visio.py:36-40` | Upper layer must not read/write registry, environment, SSH, or transport configuration. | Accept roots/paths/options as parameters or pass them through an explicitly configured business context. |
| Local path existence checks used to decide upload | `import_gds.py:124-145`; `import_verilog.py:166-175`; `digital_import.py:92-121` | This conflates caller filesystem and server filesystem; the new middle uses `LocalPath` versus `ServerPath`. | Require the caller to state whether each input is local or server-side; call `upload_file` only for local inputs. |
| Assumption that `getWorkingDir()` is the tool cwd | `import_gds.py:112-118`, `import_verilog.py:146-159` | The command, file, daemon, and GUI roles may be split and need not share cwd/filesystem (`spec/.../3-路由设计.md:30-38`, `:93-100`). | Make the tool working directory an explicit business parameter or verify it through the command role. |
| Assumption that daemon, file role, and command role share `/tmp` or workdir | `streamout.py` remote paths; `import_gds.py` local staging; `import_verilog.py` temp params | The spec explicitly does not guarantee cross-role file visibility. | Use file interface for transfers and make all paths role-qualified; fail closed if the topology is not configured. |
| Local/remote filesystem branch based on `ssh_runner is None` | `streamout.py:761-776` | Upper layer cannot know or depend on transport mode; localhost tunnel configurations are especially ambiguous. | Separate business implementations or require a path/role descriptor rather than detecting SSH. |
| Direct local OS publication operations | `streamout.py:1276-1309`, `:2813-2927`, `:2717-2725` | `os.replace`, `os.fchmod`, `shutil.copyfileobj`, temp siblings, and `shutil.rmtree` are filesystem/IPC details. | Use file-interface checks/transfers plus a clearly defined local publication helper, or move publication into the middle/file role. |
| Direct socket/port/tunnel behavior | Legitimately inside the legacy client (`src_bak/virtuoso_bridge/virtuoso/basic/bridge.py:1440-1455`), reached indirectly by layout code | Upper layout code must not import or manipulate sockets, ports, tunnels, profiles, or registry state. | Keep all transport state behind `Middle`; upper passes only token, paths, and command/skill text. |
| GUI palette/window state | `ops.py:244-277`; `clear_current_layout()` in `virtuoso/ops.py:111-120` | It mutates the global CIW/window rather than a supplied cellview and may be executed on the wrong role. | Decide whether these are daemon Skill operations or `run_gui_command` operations and make the target/window explicit. |
| `result.metadata["geometry"]` | `examples/01_virtuoso/layout/06_read_layout.py:47-52` | `metadata` is legacy implementation detail and is not a stable middle contract. | Always parse `output` through `parse_layout_geometry_output`, or define a new explicit result model. |
| `read_schematic()` legacy import | `visio.py:338-340` | It is outside the layout package and returns an ad-hoc mapping; upper layer should use a named schematic business package if this capability is retained. | Define a middle-backed schematic-read package and a typed model boundary. |
| Hidden time assumptions | `streamout.py:615-654`, `:1075-1147`, `:2150-2209`; `import_gds.py:246-279` | Timeouts and sleeps are business-visible behavior and must be preserved, but sleeping while holding the wrong channel can deadlock or starve a token. | Use short middle calls and sleep between polls at the upper layer; respect the middle’s timeout/`unknown-effect` semantics. |
| XStream command-vs-Skill ambiguity | `xstream.py:122-195`; `streamout.py:925-933` | XStream Out is a Virtuoso SKILL API, not a standalone shell tool in this code. Moving it to `run_command("strmout ...")` would invent behavior. | Keep `xstOutDoTranslate()` on the Skill interface unless a separately documented command implementation is added. |
| No OASIS support | No `oasis`/`strmout` invocation exists in the scoped files. | A caller looking for GDS/OASIS export may incorrectly assume `streamout.py` means a CLI `strmout` and that OASIS is supported. | State GDS-only scope or add a separate OASIS business capability with its own vendor-command contract. |
| Visio local dependency | `visio.py:370-383`, `examples/circuit.vss` | `circuit.vss` is a 4,955-line local asset and requires specific master names. | Package the asset with the business implementation or make stencil location and compatibility an explicit input/check. |

## 7. Test/example evidence

### 7.1 GDS export behavior pinned by tests

| Test family | Concrete assertions that a new implementation must preserve |
|---|---|
| Public API/export surface | `LayoutOps.export_gds()` forwards owner, lib/cell/output, every keyword, and the recovery hook unchanged (`test_bak/test_layout_streamout.py:477-525`); the XStream/streamout names are exported through the layout facade (`:471-474`). |
| Result model | `GdsExportReason` has exactly thirteen string values (`:2444-2465`); `GdsExportResult` has the exact field order and is frozen (`:2468-2496`); errors/warnings are tuple-normalized (`:2499-2517`); `.ok` is true only for `ExecutionStatus.SUCCESS` (`:2520-2542`). |
| Input validation | default log is `<output stem>.xstream.log` (`:2545-2583`); `stream_map` must be an existing regular file (`:2601-2615`); output/log/stream-map aliases and hardlinks are rejected (`:2619-2658`); non-empty name strings and positive finite controls are required (`:2667-2799`); `finalization_reserve < timeout` (`:2748-2762`). |
| Reason priority | `_classify_export()` applies the published matrix in order: cleanup failure, terminal failure, malformed counts, nonzero XStream errors, non-timeout Skill error, missing/empty GDS, incomplete log, indeterminate launch, success (`streamout.py:666-723`; test `:3085-3102`). |
| Remote staging | private remote chain created with `umask 077` and mode 700; POSIX run path and UUID are generated; stream map is uploaded; library/topCell/view/strmFile/layerMap/logFile/runDir are all supplied to XStream Skill (`test_bak/test_layout_streamout.py:887-931`). |
| Remote sentinel protocol | missing artifacts return exit 0 with explicit markers (`:559-581`); SHA-256 fallback order is `sha256sum`, `shasum`, `openssl` (`:585-661`); malformed, oversized, colliding, and partially read frames fail closed (`:692-884`). |
| Publication ordering | log is downloaded/parsed before GDS and is published first (`streamout.py:1593-1781`; test `:1189-1230` and `:4289-4324`); GDS must remain stable and match remote size/digest; old GDS must not be replaced on a mismatch or publication failure (`:1279-1330`, `:2079-2133`, `:4472-4971`). |
| Local staging | creates a unique sibling run directory, uses `output.gds`, `xstream.log`, and a `bridge-diagnostic.log` recovery path; direct local files are used rather than transfers (`streamout.py:1971-2108`; test `:3124-3172`). |
| Cleanup | `success`, `always`, and `never` have exact retention behavior; cleanup failures become warnings where specified and do not erase a successful result (`streamout.py:2704-2746`; tests `:4985-5015`, `:5133-5165`, `:5223-5322`). |
| Timeout/unknown-effect | exact deadlines, prefinal reserve, post-progress recovery, and no further calls after exhaustion are pinned (`streamout.py:615-654`, `:1059-1147`; tests `:1451-1516`, `:3380-3660`, `:5374-5493`). A Skill timeout is treated as indeterminate and triggers artifact observation, not a blind retry (`streamout.py:657-663`, `:945-971`). |
| Zero-count diagnostic behavior | A completion with zero errors plus a diagnostic `ERROR:` line still publishes valid GDS while carrying the log errors (`test_bak/test_layout_streamout.py:4827-4852`). This is intentionally different from nonzero completion counts. |

### 7.2 XStream parser behavior pinned by tests

| Test family | Assertions to preserve |
|---|---|
| Request model | exact seven frozen fields (`test_bak/test_xstream_helpers.py:172-177`); public export list (`:180-187`); empty/non-string values raise `ValueError` (`:190-199`). |
| Renderer ordering | all seven request values are escaped; every field is captured before the first `xstSetField`; completion dialog is suppressed and restored; all three APIs are required; nil setter/launch returns still count as success (`:202-310`). |
| Request-response parser | accepts started/failed cleanup-only wire forms and rejects invalid schema (`:329-395`). |
| Log selection and markers | parses newest product/started run (`:656-760`), recognizes bounded `XSTRM-273`/`Translation failed`/`OPEN_FAILED` markers (`:498-556`, `:813-857`), ignores adjacent codes such as `XSTRM-2730`, and retains translated-structure order/duplicates (`:848-857`). |
| Completion counts | accepts quoted/unquoted counts; reports malformed/oversized counts as `parse_errors`; keeps the last valid completion line; a completion with missing counts is still completed but malformed (`:559-653`, `:788-810`). |
| Frozen result collections | translated structures, warnings, errors, terminal failures, and parse errors are tuples; model instances are frozen (`:882-902`). |

### 7.3 Import-wrapper evidence

| Source | Behavior to preserve |
|---|---|
| `import_gds.py:99-110` | Refuse to run when the target library is not visible through `ddGetObj()`/`cds.lib`. |
| `import_gds.py:112-145` | Stage local GDS and ref-lib inputs into Virtuoso’s working directory, rewrite local paths to basenames, and leave already-remote paths untouched. |
| `import_gds.py:147-173` | Build the exact strmin option set and invoke it through the legacy tool route. |
| `import_gds.py:195-244` | Treat `strmIn.log` as the source of truth; fail fast on `XSTRM-273` plus `Translation failed`; only mark complete on `XSTRM-234` plus `Translation completed`. |
| `import_gds.py:246-279` | Refresh `ddUpdateLibList()`, poll at 3 s, verify the `layout` cellview only after completion, and time out at 600 s with the log path in the error. |
| `import_verilog.py:177-198` | Write the parameter and `-f` files on the execution host using SKILL `outfile`, not by uploading locally generated temp files. |
| `import_verilog.py:200-219` | Run ihdl in the Virtuoso working directory with the explicit `-cdslib` path and the remote/staged Verilog basename. |
| `import_verilog.py:224-252` | Verify requested `schematic` view and fall back to `functional`; report instance/net/term counts. |
| `examples/01_virtuoso/digital_import/README.md:94-113` | Preserve the documented false-`system()` behavior: do not kill a still-running strmin/ihdl process; recover by observing the eventual artifact/log. |
| `examples/01_virtuoso/digital_import/README.md:47-89` | Preserve the warning against `XST_CDS_LIB`; explicit ref-lib files are the safer business contract. |

### 7.4 Layout authoring/read examples

| Example/asset | Observable behavior to preserve |
|---|---|
| `01_create_layout.py:111-122` | `create()` opens a writable layout context; rectangle, path, label, and parameterized instance builders can be batched and saved together. |
| `02_add_polygon.py:50-53` | `modify()` appends a polygon to an existing active layout. |
| `03_add_via.py:57-70` | Both raw via-def and by-name via creation are valid business operations. |
| `04_multilayer_routing.py:51-55` | Multilayer routing is a Python planning loop over primitive path builders. |
| `05_bus_routing.py:67-83` | Bus routing is a Python planning loop with per-bit path/label operations. |
| `06_read_layout.py:41-52` | Geometry read returns a parseable line-oriented output; parser must handle records without a key-value suffix. |
| `07_delete_shapes_on_layer.py:37-53` | Layer deletion is separate from save and must be followed by an explicit save when called directly. |
| `08_clear_routing.py:25-30` | Clearing routing preserves instances. |
| `09_clear_current_layout.py:26-35` | Clear-current-layout operates on the active editor and returns a status string. |
| `10_delete_cell.py:26-37` | Cell deletion is a two-stage business action: close the current cellview, then delete the cell across windows. |
| `11_read_summary.py:31-40` | Summary output is human-readable and must detect its own error prefix. |
| `12_layer_visibility.py:62-89` | Hide/show/show-only/fit-view are separate observable GUI operations. |
| `13_select_and_delete.py:53-74` | Selection box result must be checked for `ERROR` before deleting selected figures. |
| `14_mosaic_and_nets.py:75-119` | Mosaic, net highlight, active LPP, and fit-view are separate calls with independent error reporting. |
| `layout_ops.il:28-101` | Standalone `LayoutReadLayout`, `LayoutListShapes`, `LayoutSave`, `LayoutDeleteShapesOnLayer`, `LayoutClearRouting`, and `LayoutDeleteCell` remain a compatibility contract. |

### 7.5 Visio and example-result evidence

| Source | Assertions to preserve |
|---|---|
| `examples/test_visio_export.py:16-17` | `pch_mac` classifies as PMOS; classification is cell-keyword-first. |
| `examples/test_visio_export.py:64-73` | Five instances are placed; NMOS/RES/IND/VSRC/ISRC map to `NMOS`, `R`, `L`, `DC-V`, `DC-I`; bulk pin `B` is excluded by default; each multi-pin net gets `len(pins)-1` MST segments. |
| `examples/test_visio_export.py:75-80` | Net exclusion is case-insensitive; MST always returns `n-1` segments for the tested planar point set. |
| `test_bak/test_export_gds_example.py:35-93` | Bridge preflight uses `execute_skill("1+1", timeout=10.0)`; invalid stream-map arguments produce `status=error`, `reason=invalid_arguments`, no stderr, and exit code 2. |
| `examples/01_virtuoso/layout/15_export_gds.py:92-131` | JSON result exposes status/reason/timed_out/execution_time, GDS/log paths, error/warning counts, translated structures, run directories, and retention; non-success exits 2. |

### 7.6 Minimum acceptance checklist for the re-development

1. Preserve input validation and default log naming, including regular-file and alias checks (`streamout.py:519-586`).
2. Preserve the exact reason priority matrix and distinguish `SUCCESS` from `PARTIAL`, `FAILURE`, and `ERROR` (`streamout.py:666-723`).
3. Keep XStream as a Skill API and preserve all seven request fields and the completion-dialog suppression/restoration contract (`xstream.py:122-195`).
4. Poll for both log and GDS, read the newest log run, detect terminal markers on every iteration, and never publish an unvalidated GDS (`streamout.py:1059-1178`, `:1523-1865`).
5. Publish the stable log before the stable GDS and retain the old destination on failure (`streamout.py:1312-1520`, `:2325-2746`; tests `:4289-4324`, `:4927-4971`).
6. Preserve cleanup-policy semantics and `remote_files_retained`/`local_run_dir` reporting (`streamout.py:1836-1865`, `:2704-2746`).
7. For strmin, always wait for `XSTRM-234`/`Translation completed` before reading the cellview; always fast-fail on the terminal translation marker (`import_gds.py:205-267`).
8. For ihdl, add the missing log polling and terminal-sentinel behavior rather than copying the current trusted-return-code path (`import_verilog.py:200-219`).
9. Keep label authoring/restyling as explicit Skill steps, with floorplan side parsing and bus bracket conversion in upper-layer pure Python (`add_power_labels.py:40-108`, `restyle_labels.py:53-243`).
10. Keep Visio model generation pure and isolate COM/pywin32/asset requirements behind an explicit local adapter or GUI-command contract (`visio.py:356-420`).

## 8. Open questions / ambiguities

1. **Path-domain model is unresolved.** The legacy code treats a path as local if `Path.exists()` returns true and remote otherwise (`import_gds.py:124-145`; `import_verilog.py:166-175`), while `streamout.py` uses its own local/remote branch based on `client.ssh_runner` (`streamout.py:761-776`). The new business API should require callers to identify local versus server paths, or state a rule for resolving them. Otherwise upload/staging decisions are not reproducible across roles.

2. **Where do strmin and ihdl run in the new topology?** They are documented as inheriting the running Virtuoso process’s PATH, license environment, and working directory because they are launched through `system()` (`import_gds.py:4-6`; `import_verilog.py:4-7`). The command role is independent and may not share that environment. The new design needs either a configured Cadence shell setup for `run_command`, a dedicated GUI-side helper, or an explicit requirement that these tools run through a Virtuoso-owned launcher.

3. **Should XStream remain on Skill?** The only implementation observed is `xstGetField`/`xstSetField`/`xstOutDoTranslate` through the daemon (`xstream.py:122-195`). There is no scoped `strmout` shell invocation. Treating `streamout.py` as a CLI-command wrapper would invent an interface. If the new architecture wants command-role XStream, a separate vendor-command contract and its environment requirements must be supplied.

4. **Cross-role file visibility is a business precondition.** Remote XStream puts the stream map in a run directory and assumes the daemon can read it, then assumes the file role can download the log/GDS from the same path (`streamout.py:822-920`, `:1189-1235`). The spec explicitly does not guarantee that roles share a filesystem (`spec/design-concepts/中层/3-路由设计.md:93-100`). The upper package needs a precondition/check policy and a documented topology contract.

5. **How should the middle represent temporary/staging directories?** Legacy code invents UUID directories, permissions, ownership, and cleanup commands (`streamout.py:194-292`, `:1971-1986`). The new upper layer can plan names, but it cannot implement POSIX privacy/cleanup semantics if it is limited to the five interfaces. Decide whether staging directories are business-visible or middle-owned.

6. **Which interface handles palette/window state?** The legacy functions use daemon-executed SKILL functions such as `pteSetVisible`, `hiZoomAbsoluteScale`, `hiGetWindowList`, and `leHiDelete` (`ops.py:244-348`). Those are UI/editor APIs but currently run through the daemon, while the new role table assigns X11/window commands to `gui`. The package must define a rule; “Skill” and “GUI command” are not interchangeable under the new architecture.

7. **How should polling sleep interact with token channels?** Legacy poll loops sleep at the upper level while keeping a notional operation alive (`streamout.py:1137-1147`, `:2192-2209`; `import_gds.py:246-279`). In the new middle, a long `execute_skill` or `run_command` call occupies a token channel/thread. A new implementation should use bounded calls with sleeps between iterations and must not expect a session to remain attached.

8. **What is the replacement for `metadata["geometry"]`?** The example trusts a legacy result metadata key before reparsing output (`examples/01_virtuoso/layout/06_read_layout.py:47-52`). If the new middle does not guarantee that metadata key, either remove the shortcut or define a typed geometry-return contract.

9. **What is the intended handling of command false-negatives?** The digital-import README documents that `system()` may return an empty/false result while strmin/ihdl continues in the background (`examples/01_virtuoso/digital_import/README.md:94-113`). GDS import polls and log-scans; Verilog import does not. The new implementation needs one shared polling contract for both tools and an explicit rule for “unknown effect” versus “still running.”

10. **How should Visio be routed?** `export_model_to_visio` requires an in-process Windows COM object and a local `circuit.vss` (`visio.py:356-420`). `run_gui_command` executes one-shot commands on a remote/local GUI role; it does not provide a Python COM object. Either Visio export becomes a separate local adapter outside the five-interface upper-layer contract, or a helper CLI must be defined and invoked through the appropriate command interface.

11. **Can upper-layer packages create local temporary files?** `digital_import.py` writes `_digital_import_reflibs.txt` and `_digital_import_empty_ref.txt` locally (`digital_import.py:187-201`). The new rules forbid environment/subprocess/transport dependencies but are less explicit about planning-only local files. The answer determines whether ref-lib lists are generated by the caller, passed as bytes, or staged through the file interface.

12. **Do input names intentionally preserve whitespace?** `_require_nonempty_string()` accepts `" demo"` and `"layout "` because it only rejects strings whose `strip()` is empty (`streamout.py:589-592`); tests explicitly preserve whitespace (`test_bak/test_layout_streamout.py:2691-2707`). New validation must decide whether this is an intentional compatibility contract or should be tightened.

13. **Should the new result model preserve the exact reason string values?** The enum values are pinned by tests and may be consumed by JSON callers (`test_bak/test_layout_streamout.py:2444-2465`; example `15_export_gds.py:92-131`). If a new typed `BusinessResult` replaces `GdsExportResult`, mapping compatibility matters.

14. **How should multi-SRAM or mixed-reference designs be represented?** The legacy pipeline detects all `TS1N28*` names, accepts exactly one automatically, and otherwise requires `--sram-cell` (`digital_import.py:165-180`). That is a lab-specific detection heuristic, not a general business rule; new packages likely need an explicit list or ordered SRAM contract.

15. **Is OASIS in scope?** No OASIS implementation or `strmout` invocation was found in the inspected scope. The new inventory should not claim OASIS support based only on the filename `streamout.py`. If OASIS is required, it needs a separate capability and vendor-command contract.

16. **What is the source of truth for library registration?** `import_gds.py` and `import_verilog.py` require an existing `cds.lib` entry and only refresh the library list (`import_gds.py:101-110`; `import_verilog.py:136-144`, `:221-222`). A new upper layer should not silently create or edit library definitions unless that is an explicit business capability.

17. **How should remote cleanup safety be exposed?** Legacy code refuses to delete paths unless they match a strict owned UUID layout and checks ownership/mode with shell commands (`streamout.py:1868-1908`, `:1922-1968`). A new business API must either expose a retention policy only and let the middle enforce safety, or make cleanup a clearly privileged operation with its own contract.

18. **What is the compatibility target for `LayoutOps.edit()`?** It remains in the facade, emits a deprecation warning, and defaults to safe append mode (`layout/__init__.py:83-97`). If legacy callers exist, the re-developed package needs either a compatibility shim or an explicit migration note.

## Appendix: key source anchors

- Public layout facade and exports: `src_bak/virtuoso_bridge/virtuoso/layout/__init__.py:57-172`
- Editor batching/save behavior: `src_bak/virtuoso_bridge/virtuoso/layout/editor.py:31-75`
- SKILL geometry builders: `src_bak/virtuoso_bridge/virtuoso/layout/ops.py:47-484`
- Geometry parser: `src_bak/virtuoso_bridge/virtuoso/layout/reader.py:9-53`
- XStream renderer/parser: `src_bak/virtuoso_bridge/virtuoso/layout/xstream.py:17-368`
- GDS export orchestration: `src_bak/virtuoso_bridge/virtuoso/layout/streamout.py:55-2955`
- Remote staging/sentinel/polling: `src_bak/virtuoso_bridge/virtuoso/layout/streamout.py:194-516`, `:1059-1178`
- Remote log/GDS stabilization and publication: `src_bak/virtuoso_bridge/virtuoso/layout/streamout.py:1312-1865`
- Local staging/polling/publication: `src_bak/virtuoso_bridge/virtuoso/layout/streamout.py:1971-2746`
- Visio model/COM split: `src_bak/virtuoso_bridge/virtuoso/visio.py:34-452`
- strmin wrapper/polling: `examples/01_virtuoso/digital_import/import_gds.py:99-279`
- ihdl wrapper: `examples/01_virtuoso/digital_import/import_verilog.py:134-252`
- one-shot pipeline: `examples/01_virtuoso/digital_import/digital_import.py:67-229`
- power labels: `examples/01_virtuoso/digital_import/add_power_labels.py:40-160`
- label restyle/floorplan parse: `examples/01_virtuoso/digital_import/restyle_labels.py:53-249`
- standalone SKILL compatibility asset: `examples/01_virtuoso/assets/layout_ops.il:16-101`
- normative middle interfaces: `spec/design-concepts/总览/1-四层整体架构与接口.md:178-212`
- role definitions: `spec/design-concepts/中层/3-路由设计.md:40-100`
