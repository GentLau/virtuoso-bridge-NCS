# D — Legacy library, SKILL tooling, GUI/desktop, and basic-client inventory

Scope inspected read-only: the library, SKILL Finder, documentation search, basic client, X11/snapshot/ops/response/skill-output/editor files, the X11 helper, legacy tests, the scoped examples/diagnostics, and the normative four-layer/5-role specs. The only file written by this exploration is this report.

The new upper layer may call only the frozen middle interfaces: `execute_skill`, `run_command`, `upload_file`/`download_file` (one File interface), `run_gui_command`, and `run_spectre_command`, all with `token` (`spec/design-concepts/总览/1-四层整体架构与接口.md:178-212`; `spec/design-concepts/中层/3-路由设计.md:40-75`). The `gui` role owns one-shot X11/window/CIW work (`spec/design-concepts/中层/3-路由设计.md:40-45,59-75`).

## 1. Module inventory

| Path | Lines | One-line purpose |
|---|---:|---|
| `src_bak/virtuoso_bridge/virtuoso/library/__init__.py` | 187 | `LibraryOps` facade attached to `VirtuosoClient`, delegating library and flat-category operations. |
| `src_bak/virtuoso_bridge/virtuoso/library/category.py` | 564 | Builds and validates `ddCat*` SKILL records for list/create/delete/list-cells/add/remove/rename category operations. |
| `src_bak/virtuoso_bridge/virtuoso/library/management.py` | 348 | Builds and validates supported `dd*`/`ccpRename`/technology SKILL records for library identity and lifecycle. |
| `src_bak/virtuoso_bridge/virtuoso/skill_finder/__init__.py` | 292 | Discovers/loads Cadence `.fnd` trees and implements exact/prefix/suffix/fuzzy/regex search. |
| `src_bak/virtuoso_bridge/virtuoso/skill_finder/more_info.py` | 210 | Parses `api_more_info.tgf`, extracts modern or legacy HTML topics, and converts HTML to Markdown/plain text. |
| `src_bak/virtuoso_bridge/virtuoso/skill_finder/parser.py` | 118 | Parses three-line `.fnd` records into `SkillEntry` objects with first-name deduplication. |
| `src_bak/virtuoso_bridge/virtuoso/docs_search.py` | 1410 | Resolves/search local or remote Cadence doc trees, parses `.tgf`/HTML/text, and builds/reuses a SQLite index. |
| `src_bak/virtuoso_bridge/virtuoso/basic/bridge.py` | 1512 | Legacy `VirtuosoClient`: TCP SKILL execution plus facades for library/layout/schematic/symbol/Maestro, windows, screenshots, files, docs and GUI recovery. |
| `src_bak/virtuoso_bridge/virtuoso/basic/composition.py` | 19 | Composes atomic SKILL strings into one script, optionally wrapped in `progn(...)`. |
| `src_bak/virtuoso_bridge/virtuoso/basic/resources/ramic_bridge.il` | 639 | CIW-side RAMIC daemon launcher/control UI and IPC glue; not part of the new upper layer. |
| `src_bak/virtuoso_bridge/virtuoso/x11.py` | 245 | Legacy wrapper that deploys/runs the X11 helper locally or through SSH and parses its JSON-lines output. |
| `src_bak/virtuoso_bridge/virtuoso/snapshot.py` | 122 | Classifies the focused Virtuoso title and dispatches a polymorphic snapshot; only Maestro is implemented. |
| `src_bak/virtuoso_bridge/virtuoso/ops.py` | 120 | Pure string builders for cellview open/window/save/close/clear and SKILL escaping. |
| `src_bak/virtuoso_bridge/virtuoso/response.py` | 47 | Normalizes object or dict transport responses into `(errors, status, output)` triples. |
| `src_bak/virtuoso_bridge/virtuoso/skill_output.py` | 194 | Tokenizes/parses SKILL s-expressions and decodes `%L` string-list output. |
| `src_bak/virtuoso_bridge/virtuoso/editor.py` | 24 | Shared batch-edit response validator used by layout/schematic/symbol editor context managers. |
| `src_bak/virtuoso_bridge/resources/x11_dismiss_dialog.py` | 881 | Python 2/3-compatible remote helper for X11 environment discovery, window enumeration, dialog dismissal, and CIW bootstrap. |

Supporting files deliberately read for editor semantics are `src_bak/virtuoso_bridge/virtuoso/layout/editor.py` (75 lines), `schematic/editor.py` (77), `symbol/editor.py` (58), and their `LayoutOps`/`SchematicOps`/`SymbolOps` facades. They are not separate upper packages; they pin the create/modify/append contract.

The legacy `VirtuosoResult` surface is `status`, `output`, `errors`, `warnings`, `execution_time`, `metadata`, plus `ok` and `is_nil` (`src_bak/virtuoso_bridge/models.py:12-57`). The new middle result adds `log` and uses `CommandResult` for everything except Skill (`src/pyapi/models.py:27-75`; `spec/design-concepts/总览/1-四层整体架构与接口.md:259-279`).

## 2. Public API surface

Signature notation below is exact except for shortened type spellings such as `str | Path` where the source uses `str | Path`. Defaults are copied from code. Return shapes are the actual legacy return objects/dicts, not proposed new wrappers.

### 2.1 Library management and categories

`LibraryOps` is attached by `VirtuosoClient.__init__` as `client.library` (`src_bak/virtuoso_bridge/virtuoso/basic/bridge.py:91-94`; tests pin it at `test_bak/test_library_management.py:43-46`).

| Public entry point | Exact signature | Return / behavior |
|---|---|---|
| `LibraryOps.__init__` | `(self, owner: VirtuosoClient) -> None` | Stores owner; no I/O. |
| `LibraryOps.list` | `(self, *, timeout: int = 30) -> list[str]` | Library names visible in the current Virtuoso session. |
| `LibraryOps.get` | `(self, name: str, *, timeout: int = 30) -> LibraryInfo` | Verified name/path/technology object. |
| `LibraryOps.create` | `(self, name: str, path: str, *, technology_library: str | None = None, timeout: int = 60) -> LibraryInfo` | Creates library; optional technology binding; partial binding raises. |
| `LibraryOps.delete` | `(self, name: str, *, timeout: int = 60) -> None` | Verified `ddDeleteObj` deletion. |
| `LibraryOps.rename` | `(self, name: str, new_name: str, *, timeout: int = 120) -> LibraryInfo` | `ccpRename` with overwrite disabled and destination verification. |
| `LibraryOps.get_technology_library` | `(self, name: str, *, timeout: int = 30) -> str | None` | Convenience read of `LibraryInfo.technology_library`. |
| `LibraryOps.set_technology_library` | `(self, name: str, technology_library: str, *, timeout: int = 60) -> str` | Binds unbound or sets existing technology; returns verified name. |
| `LibraryOps.list_categories` | `(self, library: str, *, timeout: int = 30) -> list[str]` | Persistent top-level category names after stale-name filtering. |
| `LibraryOps.create_category` | `(self, library: str, category: str, *, timeout: int = 30) -> str` | Verified category name. |
| `LibraryOps.rename_category` | `(self, library: str, category: str, new_name: str, *, timeout: int = 60) -> str` | Copy-members then remove-source rename; returns destination. |
| `LibraryOps.delete_category` | `(self, library: str, category: str, *, timeout: int = 30) -> None` | Deletes category/membership data, never cells. |
| `LibraryOps.list_category_cells` | `(self, library: str, category: str, *, timeout: int = 30) -> list[str]` | Only members whose `ddCat` type is `"cell"`. |
| `LibraryOps.add_cell_to_category` | `(self, library: str, category: str, cell: str, *, timeout: int = 30) -> None` | Add, save, close, reopen and verify; duplicate is an error. |
| `LibraryOps.remove_cell_from_category` | `(self, library: str, category: str, cell: str, *, timeout: int = 30) -> None` | Remove, save, close, reopen and verify; absent membership is an error. |

Library data/error helpers:

| Public entry point | Exact signature | Return / behavior |
|---|---|---|
| `LibraryInfo` | `@dataclass(frozen=True) LibraryInfo(name: str, path: str, technology_library: str | None)` | Immutable verified library identity. |
| `LibraryPartialSuccessError` | `(message: str, library: LibraryInfo)` | `RuntimeError` subclass with `.library`; raised when the library was created but technology binding failed. |
| `library_list_skill` | `() -> str` | Returns `list("ok" mapcar(lambda((vbLib) vbLib~>name) ddGetLibList()))`. |
| `library_get_skill` | `(name: str) -> str` | Returns `("ok" ("library" name readPath tech-or-nil))` or `("error" ...)`. |
| `library_create_skill` | `(name: str, path: str, *, technology_library: str | None = None) -> str` | Uses `ddCreateLib`; optional `techBindTechFile` plus read-back. |
| `library_delete_skill` | `(name: str) -> str` | Uses `ddDeleteObj`; verifies `!ddGetObj(name)`. |
| `library_rename_skill` | `(name: str, new_name: str) -> str` | Uses `gdmCreateSpec` + `ccpRename(..., nil)`; refuses destination existence. |
| `library_set_technology_skill` | `(name: str, technology_library: str) -> str` | Uses `techSetTechLibName` when bound, otherwise `techBindTechFile`; verifies read-back. |
| `list_libraries` | `(client: Any, *, timeout: int = 30) -> list[str]` | Calls `client.execute_skill` and rejects malformed/non-list output. |
| `get_library` | `(client: Any, name: str, *, timeout: int = 30) -> LibraryInfo` | Parses `("ok" ("library" ...))`. |
| `create_library` | `(client: Any, name: str, path: str, *, technology_library: str | None = None, timeout: int = 60) -> LibraryInfo` | Parses `("partial" ... info)` into `LibraryPartialSuccessError`. |
| `delete_library` | `(client: Any, name: str, *, timeout: int = 60) -> None` | Requires `("ok")`. |
| `rename_library` | `(client: Any, name: str, new_name: str, *, timeout: int = 120) -> LibraryInfo` | Returns destination info after verification. |
| `set_technology_library` | `(client: Any, name: str, technology_library: str, *, timeout: int = 60) -> str` | Returns verified technology name; rejects no binding. |

Category protocol/error helpers:

| Public entry point | Exact signature | Return / behavior |
|---|---|---|
| `CategoryPartialSuccessError` | `(message: str, *, library: str, category: str)` | `RuntimeError` with `.library` and `.category`; raised for `("partial" ...)` records. |
| `category_list_skill` | `(library: str) -> str` | `ddCatGetLibCats`; opens each name to filter stale entries. |
| `category_create_skill` | `(library: str, category: str) -> str` | `ddCatOpenEx(..., "w", 1)`, save/close/read-back verification; no member insertion. |
| `category_delete_skill` | `(library: str, category: str) -> str` | `ddCatRemove`; verifies category is gone; never deletes cells. |
| `category_list_cells_skill` | `(library: str, category: str) -> str` | `ddCatGetCatMembers`; filters `cadr(member) == "cell"`. |
| `category_add_cell_skill` | `(library: str, category: str, cell: str) -> str` | Uses `member(cell vbLib~>cells~>name)`, then `ddCatAddItem`, save/close/reopen verify. |
| `category_remove_cell_skill` | `(library: str, category: str, cell: str) -> str` | Uses `ddCatSubItem`, save/close/reopen verify. |
| `category_rename_skill` | `(library: str, category: str, new_name: str) -> str` | Rejects subcategories/destination, copies all member pairs, verifies, then removes source. |
| `list_categories`, `create_category`, `delete_category`, `list_category_cells`, `add_cell_to_category`, `remove_cell_from_category`, `rename_category` | The same `(client: Any, ... , *, timeout=...)` shapes as `LibraryOps` above | Implement the `client.library.*` record parser and raise `RuntimeError`/`CategoryPartialSuccessError`. |

There is no legacy “attach/detach library” or “open/close library” API. The closest concepts are technology bind/change (`techBindTechFile`/`techSetTechLibName`) and cellview open/window/close (`dbOpenCellViewByType`, `geOpen`, `dbClose`, `dbSave`). There is no technology-unbind operation and no direct `cds.lib`/`.TopCat` edit API in this scope (`skills/virtuoso/references/library-python-api.md:20-103`).

### 2.2 Cellview/window/edit context-manager API

`ops.py` builders:

| Entry point | Exact signature | Return / behavior |
|---|---|---|
| `escape_skill_string` | `(value: str) -> str` | Backslash-escapes `\` and `"` only. |
| `q` | `(value: str) -> str` | `"` + escaped value + `"`. |
| `default_view_type_for` | `(view: str) -> str` | `layout* -> maskLayout`, `schematic -> schematic`, `symbol -> schematicSymbol`, `maestro -> maestro`, else unchanged. |
| `skill_point` | `(x: float, y: float) -> str` | SKILL point literal with three decimals. |
| `skill_point_list` | `(points: Iterable[tuple[float, float]]) -> str` | Quoted SKILL point list. |
| `open_cell_view` | `(lib: str, cell: str, *, view: str = "layout", view_type: str | None = None, mode: str = "a") -> str` | `cv = dbOpenCellViewByType(...)`; safe append is the default. |
| `open_window` | `(lib: str, cell: str, *, view: str = "layout", view_type: str | None = None, mode: str = "a") -> str` | Reuses/focuses an existing matching window; otherwise `geOpen(...)`. |
| `save_current_cellview` | `() -> str` | Saves bound `cv` if present, else `geGetEditCellView()`. |
| `close_current_cellview` | `() -> str` | Closes bound `cv` if present, else current edit cellview. |
| `clear_current_layout` | `() -> str` | Selects all visible figures and deletes them; returns `"Deleted all shapes"` in SKILL. |

Editor facades and context managers:

| Entry point | Exact signature | Return / behavior |
|---|---|---|
| `LayoutOps.create` | `(self, lib: str, cell: str, view: str = "layout", timeout: int = 60) -> LayoutEditor` | `mode="w"`; deliberately replaces/recreates the target view. |
| `LayoutOps.modify` | `(self, lib: str, cell: str, view: str = "layout", timeout: int = 60) -> LayoutEditor` | `mode="a"`; binds current matching layout or opens append. |
| `LayoutOps.edit` | `(self, lib: str, cell: str, view: str = "layout", mode: Literal["a", "w"] = "a", timeout: int = 60) -> LayoutEditor` | Deprecated warning; legacy default is safe append. |
| `LayoutEditor.__init__` | `(client, lib, cell, view="layout", mode="a", timeout=60)` | Accumulates commands, then `execute_operations`. |
| `LayoutEditor.__enter__` | `() -> LayoutEditor` | For `w`, appends `open_cell_view(..., mode="w")`; otherwise appends `layout_bind_current_or_open_cell_view(...)`. |
| `LayoutEditor.add` / `close` | `(skill_cmd: str) -> None` / `() -> None` | Queue arbitrary SKILL or a close operation. |
| `LayoutEditor.__exit__` | `(exc_type, exc_val, exc_tb) -> None` | Only on clean exit: append `save_current_cellview()`, execute batch, validate response. |
| `SchematicOps.create/modify/edit` | same shapes as LayoutOps but defaults `view="schematic"`; `edit(mode="a")` | `w` replaces, `a` appends; deprecated edit warns. |
| `SchematicEditor.__enter__` | `() -> SchematicEditor` | Appends `dbOpenCellViewByType(... mode=mode)`. |
| `SchematicEditor.add` | `(skill_cmd: str) -> None` | Queue command. |
| `SchematicEditor.add_net_label_to_transistor` | `(self, instance_name: str, drain_net: str | None = None, gate_net: str | None = None, source_net: str | None = None, body_net: str | None = None) -> None` | Queues labels for non-`None` D/G/S/B nets. |
| `SchematicEditor.__exit__` | `(exc_type, exc_val, exc_tb) -> None` | Clean exit appends `schematic_check()`, `save_current_cellview()`, executes and validates. |
| `SymbolOps.create/modify/edit` | `view="symbol"`, `view_type="schematicSymbol"` | Same explicit overwrite/append/deprecated semantics. |
| `SymbolEditor.__enter__` | `() -> SymbolEditor` | Opens symbol view with mode. |
| `SymbolEditor.__exit__` | `(exc_type, exc_val, exc_tb) -> None` | Clean exit appends `symbol_check()`, save, executes and validates. |
| `ensure_operation_response` | `(response: Any, *, context: str) -> None` | Accepts `VirtuosoResult` or dict envelope; raises `RuntimeError` on non-success. |
| `compose_skill_script` | `(commands: Iterable[str], *, wrap_in_progn: bool = True) -> str` | Drops blank commands, raises on none, preserves one already-`progn(...)` command, otherwise joins and optionally wraps. |

### 2.3 SKILL Finder / More Info API

| Entry point | Exact signature | Return / behavior |
|---|---|---|
| `SearchMode` | enum: `FUZZY="fuzzy"`, `PREFIX`, `SUFFIX`, `EXACT`, `REGEX` | Search mode labels. |
| `SearchOptions` | dataclass fields `mode: SearchMode = SearchMode.FUZZY`, `limit: int = 50`, `case_sensitive: bool = False` | Note: the current `SKILLFinder.search` implementation does not consult `case_sensitive`. |
| `SkillEntry` | dataclass `name: str`, `syntax: str`, `description: str`, `source_file: str | None = None` | `to_dict() -> {"name", "syntax", "description", "source_file"}`. |
| `SKILLFinder.discover` | `(self, remote_runner=None, profile: str | None = None) -> Path | None` | Local: `which virtuoso` then walk parents to `doc/finder/SKILL`. Remote: cshrc-sourced command + `which virtuoso`, then a bash parent walk. |
| `SKILLFinder.load` | `(self, source_dir: Path | str | None = None) -> None` | Parses all `.fnd` files; raises if no source is known. |
| `SKILLFinder.search` | `(self, query: str, *, mode: SearchMode | str = SearchMode.FUZZY, limit: int = 50, include_desc: bool = False) -> list[SkillEntry]` | Case-insensitive matching except exact; `include_desc` adds descriptions to non-exact modes. Results are sorted by name, not by score, then limited. |
| `SKILLFinder.format_result` / `format_results` | `(entry) -> str` / `(results, query) -> str` | Human-readable CLI text. |
| `parse_fnd_file` | `(path: Path) -> list[SkillEntry]` | Regex over three-line `("name" "syntax" "description")` records; unreadable files return `[]`. |
| `parse_fnd_directory` | `(root: Path) -> list[SkillEntry]` | Recursive `.fnd` scan; first occurrence per function name wins; missing root returns `[]`. |
| `MoreInfoEntry` | dataclass `func_name: str`, `file_path: str`, `topic: str | None`, `format: str` | One index record. |
| `MoreInfoResult` | dataclass `func_name`, `file_path`, `topic`, `raw_html`, `plain_text` | Legacy helper data shape; `VirtuosoClient.get_skill_more_info` returns the equivalent dict on the wire. |
| `parse_tgf_index` | `(tgf_path: Path) -> dict[str, MoreInfoEntry]` | Lower-cased function key; first duplicate wins; `NULL` topic becomes `None`. |
| `resolve_doc_path` | `(tgf_path: Path, relative_path: str) -> Path` | Strips leading `$` and resolves relative to `tgf_path.parent.parent`. |
| `extract_topic_from_html` | `(html_content: str, topic_name: str) -> str | None` | Modern `TOPIC_START_OPEN`/`TOPIC_END` marker extraction. |
| `extract_topic_from_html_legacy` | `(html_content: str, topic_name: str) -> str | None` | Anchor or heading-text extraction for pre-More-Info HTML. |
| `extract_doc_section` | `(html_content: str, topic_name: str, *, fallback_whole_file: bool = False) -> str | None` | Modern then legacy then optional whole-file fallback. |
| `html_to_plain_text` | `(html: str) -> str` | Removes empty `<code>` tags, then converts via `markdownify` to ATX Markdown. |
| `get_all_indexed_files` | `(tgf_entries: dict[str, MoreInfoEntry]) -> set[str]` | Distinct indexed file paths. |

Client-level wrappers:

| Entry point | Exact signature | Return / behavior |
|---|---|---|
| `VirtuosoClient.find_skill` | `(self, query: str, *, mode: str = "fuzzy", limit: int = 50, include_desc: bool = False, source_dir: str | Path | None = None, cache_dir: str | Path | None = None) -> list[dict]` | Local/remote `.fnd` discovery, recursive cache, then parser/search; each dict has `name`, `syntax`, `description`, `source_file`. |
| `VirtuosoClient.get_skill_more_info` | `(self, func_name: str, *, source_dir: str | Path | None = None, cache_dir: str | Path | None = None) -> dict | None` | Downloads `.tgf` and one referenced HTML file on demand; accepts `_ocean` and `_viva_skill` suffixes; returns dict with `func_name`, `file_path`, `topic`, `raw_html`, `plain_text`. |

### 2.4 Cadence documentation search API

| Entry point | Exact signature | Return / behavior |
|---|---|---|
| `TgfEntry` | frozen dataclass `topic_id: str`, `target_path: Path`, `anchor: str`, `source_path: Path`, `line: int | None = None` | One `.tgf` topic record. |
| `RemoteDocMatch` | frozen dataclass `doc_root: str`, `path: str` | One remote candidate from lightweight search. |
| `resolve_doc_roots` | `(explicit_roots: Sequence[str | Path] | None = None, *, env: Mapping[str, str] | None = None) -> list[Path]` | Explicit roots win; otherwise `CADENCE_DOC_ROOT`, `CADENCE_DOC_ROOTS`, then install roots plus `/doc`; only existing dirs, stable de-duplication. |
| `iter_doc_files` | `(doc_roots: Sequence[Path]) -> Iterable[tuple[Path, Path]]` | Yields `(root, file)` for `.html`, `.htm`, `.txt`, `.xml`, `.json`, `.tgf`. |
| `parse_tgf_line` | `(line: str, *, tgf_path: Path, doc_root: Path, line_no: int | None = None) -> TgfEntry | None` | `shlex.split`; requires at least four fields and final `HTML`; resolves `$docSet/...`. |
| `search_docs` | `(query: str, doc_roots: Sequence[str | Path], *, limit: int = 10, cache_root: str | Path | None = None, rebuild: bool = False) -> list[dict[str, object]]` | Direct identifier short-circuit, filename/content scan, `.tgf` topics, scoring/dedup. |
| `discover_remote_doc_roots` | `(runner, *, profile: str | None = None) -> list[str]` | Uses SKILL Finder anchor plus remote Cadence doc/install env vars. |
| `find_remote_doc_matches` | `(runner, query: str, doc_roots: Sequence[str], *, limit: int = 10, candidate_limit: int | None = None) -> list[RemoteDocMatch]` | Runs remote `find`+`grep` candidate search and parses tab-separated root/path. |
| `cache_remote_doc_matches` | `(runner, matches: Sequence[RemoteDocMatch], cache_root: str | Path, *, timeout: int = 30) -> tuple[list[Path], dict[Path, str]]` | Downloads candidate files into a local cache; returns local roots and local-root→remote-root map. |
| `remap_results_to_remote` | `(results: Sequence[dict[str, object]], root_map: Mapping[Path, str]) -> list[dict[str, object]]` | Rewrites `path` and `target_path` from cache paths back to remote paths. |
| `search_remote_docs` | `(runner, query: str, doc_roots: Sequence[str], *, cache_root: str | Path, limit: int = 10, rebuild: bool = False) -> list[dict[str, object]]` | Builds/reuses a local SQLite index from a remotely generated `.jsonl.gz` record stream. |
| `VirtuosoClient.search_docs` | `(self, query: str, *, limit: int = 10, doc_roots: list[str | Path] | None = None, cache_dir: str | Path | None = None, rebuild_index: bool = False) -> dict[str, object]` | Returns `{"doc_roots": [...], "results": [...]}`; remote index first, candidate-download fallback on index failure, local mode otherwise. |

The result dict for a document hit is `{"kind":"document", "path", "relative_path", "title", "line":None, "snippet"}`; a topic hit is `{"kind":"topic", "path", "relative_path", "line", "topic_id", "anchor", "target_path", "target_relative_path", "title", "snippet"}` (`src_bak/virtuoso_bridge/virtuoso/docs_search.py:488-553,1142-1168`).

### 2.5 Legacy basic client API

`VirtuosoClient` subclasses `VirtuosoInterface`; construction attaches `layout`, `library`, `schematic`, `symbol`, and `maestro` facades (`src_bak/virtuoso_bridge/virtuoso/basic/bridge.py:71-106`).

| Concern | Entry point | Exact signature | Return / behavior |
|---|---|---|---|
| Construction | `VirtuosoClient.__init__` | `(host: str = "127.0.0.1", port: int = 65432, timeout: int = 30, tunnel: Any = None, log_to_ciw: bool = True) -> None` | Stores TCP endpoint/tunnel, creates facade objects and IL upload cache. |
| Construction | `VirtuosoClient.from_env` | `(cls, *, timeout: int = 30, log_to_ciw: bool = True, profile: str | None = None) -> VirtuosoClient` | Resolves profile/env, reuses a running tunnel or creates `SSHClient`, then cross-user daemon guard. Legacy only. |
| Construction | `VirtuosoClient.local` | `(cls, host: str = "127.0.0.1", port: int = 65432, timeout: int = 30) -> VirtuosoClient` | No tunnel object. |
| Construction | `VirtuosoClient.from_tunnel` | `(cls, tunnel: Any, timeout: int = 30, log_to_ciw: bool = True) -> VirtuosoClient` | Wraps an existing tunnel. |
| Lifecycle | `__enter__` / `__exit__` | `() -> VirtuosoClient` / `(*_: Any) -> None` | Context manager closes the tunnel. |
| Properties | `host`, `port`, `remote_host`, `is_remote`, `is_tunnel_alive`, `ssh_runner`, `log_to_ciw` | getter signatures as shown; `log_to_ciw` also has setter `(value: bool) -> None` | Network/tunnel/session state. `ssh_runner` returns `None` locally. |
| Readiness | `ensure_ready` | `(self, timeout: int = 10) -> VirtuosoResult` | Warms tunnel, probes TCP/daemon, returns structured errors and diagnostics. |
| Readiness | `warm_remote_session` | `(self, timeout: int = 10) -> VirtuosoResult` | Warms transport without requiring daemon response. |
| Readiness | `test_connection` | `(self, timeout: int = 10) -> bool` | Executes `1+1`; true only on success. |
| Readiness | `verify_tunnel` | `(self, timeout: int = 5) -> dict[str, Any]` | Keys: `tunnel_process_alive`, `tcp_reachable`, `daemon_responsive`, `daemon_output`, `summary`. |
| Skill | `execute_skill` | `(self, skill_code: str, timeout: Optional[float] = None) -> VirtuosoResult` | One JSON request over TCP; response markers `\x02` success, `\x15` error; retry only connection-refused/reset/no-connection before deadline. |
| Skill | `ciw_print` | `(self, message: str, timeout: int | None = None) -> VirtuosoResult` | Executes `printf("...\n")`; return value is still transport result, not captured CIW text. |
| Skill | `ciw_log` | `(self, skill_code: str, timeout: int | None = None) -> VirtuosoResult` | Alias-like execution; no separate logging behavior. |
| Structured fetch | `fetch` | `(self, expr: str, fields: list[str], *, timeout: int | None = None) -> list[dict]` | Wraps expression in `mapcar(lambda((o) list(o~>field...)) ...)`, parses s-expression, zips field names. |
| Structured fetch | `fetch_one` | `(self, expr: str, fields: list[str], *, timeout: int | None = None) -> dict` | Calls `fetch("list(expr)", fields)` and returns first row or `{}`. |
| Generic command | `run_shell_command` | `(self, cmd: str, timeout: int | None = None) -> VirtuosoResult` | Runs `csh("...")`; `nil` is converted to an error. It cannot return command stdout and must not be used as the new command interface. |
| Cellview | `open_cell_view` | `(self, lib: str, cell: str, *, view: str | None = None, view_type: str | None = None, mode: str = "a", timeout: int | None = None) -> VirtuosoResult` | Defaults view to layout and view type from `default_view_type_for`; binds global `cv`. |
| Cellview/window | `open_window` | `(self, lib: str, cell: str, *, view: str = "schematic", view_type: str | None = None, timeout: int | None = None) -> VirtuosoResult` | Reuses an existing matching window or opens one. |
| Cellview | `save_current_cellview` / `close_current_cellview` | `(self, timeout: int | None = None) -> VirtuosoResult` | Saves/closes bound `cv` or current edit cellview. |
| Cellview | `get_current_design` | `(self, timeout: int | None = None) -> tuple[str | None, str | None, str | None]` | Uses `ddGetObjReadPath(dbGetCellViewDdId(geGetEditCellView()))`; naïvely splits path by `/` and returns `parts[-4:-1]`. |
| Window inventory (SKILL) | `list_windows` | `(self, timeout: int | None = None) -> list[dict[str, str]]` | Returns `{"num": "<windowNum>", "name": "<hiGetWindowName>"}`; the CIW is first; nil/non-string names are skipped; octal escapes are decoded. |
| Screenshot | `screenshot` | `(self, output: str | Path | None = None, *, target: str | int = "ciw", timeout: int | None = None) -> VirtuosoResult` | Resolves target (`ciw`, `current`, int `windowNum`, or string view name), calls `hiWindowSaveImage(... ?format "png" ?toplevel t)`, then downloads the PNG. Default output is the user artifact screenshot dir. |
| File | `download_file` | `(self, remote_path: str | Path, local_path: str | Path, *, timeout: int | None = None, recursive: bool = False) -> VirtuosoResult` | Remote: tunnel download; local: `shutil.copytree`/`copy2`. Returns output destination, metadata paths. Remote implementation refuses overlapping recursive copy only in local mode. |
| File | `upload_file` | `(self, local_path: str | Path, remote_path: str | Path, *, timeout: int | None = None) -> VirtuosoResult` | Remote: tunnel upload; local: parent mkdir + `shutil.copy2`. No recursive parameter in this legacy method. |
| GUI recovery | `dismiss_dialog` | `(self, display: str | None = None) -> list[dict]` | Finds/dismisses X11 dialogs; delegates to `x11.dismiss_dialogs`. |
| SKILL Finder | `find_skill` | see §2.3 | Returns list of four-field dicts. |
| More Info | `get_skill_more_info` | see §2.3 | Returns five-field dict or `None`. |
| Docs | `search_docs` | see §2.4 | Returns `{"doc_roots", "results"}`. |
| IL | `load_il` | `(self, path: str | Path, timeout: int | None = None) -> VirtuosoResult` | If remote local file, uploads/caches by MD5 and executes `load("remote_path")`; adds `metadata["uploaded"]` and `metadata["skill_command"]`. |
| IL/workflow | `run_il_file` | `(self, path: str | Path, lib: str, cell: str, *, view: str = "layout", view_type: str | None = None, mode: str = "a", open_window: bool = True, save: bool = False, timeout: int | None = None) -> VirtuosoResult` | Open cellview, optionally window, execute `cv = geGetEditCellView()`, load IL, optionally save; save result metadata contains serialized load result. |
| Batch Skill | `execute_operations` | `(self, commands: list[str], *, timeout: int | None = None, wrap_in_progn: bool = True) -> VirtuosoResult` | Composes commands once and adds `metadata["operation_count"]`. |
| Cleanup | `close` / `__del__` | `() -> None` / `() -> None` | Closes tunnel; destructor suppresses all errors. |

### 2.6 X11 wrapper API

| Entry point | Exact signature | Return / behavior |
|---|---|---|
| `find_dialogs` | `(runner: SSHRunner | None, user: str, display: str | None = None, profile: str | None = None) -> list[dict[str, Any]]` | Legacy helper invocation without `--list-windows`; returns dialog candidates (`window_id`, title, frame/geometry, kind, action). |
| `list_windows` | `(runner: SSHRunner | None, user: str, display: str | None = None, profile: str | None = None, top_level: bool = False) -> list[dict[str, Any]]` | Adds `--list-windows --json` and optionally `--top-level`; parses JSON lines. |
| `dismiss_window` | `(runner: SSHRunner | None, user: str, window_id: str, *, action: str = "enter", display: str | None = None, profile: str | None = None) -> list[dict[str, Any]]` | Adds `--dismiss-window <id> --action <action>`; no auto action. |
| `bootstrap_ciw` | `(runner: SSHRunner | None, user: str, window_id: str, setup_path: str, *, display: str | None = None, profile: str | None = None) -> list[dict[str, Any]]` | Adds `--bootstrap-window <id> --setup-path <path>`; only generated setup load expression is accepted. |
| `dismiss_dialogs` | `(runner: SSHRunner | None, user: str, display: str | None = None, profile: str | None = None) -> list[dict[str, Any]]` | Adds policy/context env prefix and `--dismiss`; finds then dismisses candidates. |
| `_parse_result` / `_parse_output` | `(result) -> list[dict[str, Any]]` / `(stdout: str) -> list[dict[str, Any]]` | Parses JSON lines; non-JSON lines are ignored; nonzero rc produces an error dict. |

Display resolution is explicit `display` argument first, then `VB_DISPLAY`, otherwise `None` for helper auto-detection (`src_bak/virtuoso_bridge/virtuoso/x11.py:26-31`). The wrapper supports local subprocess with `sh -c` only when `runner is None` (`src_bak/virtuoso_bridge/virtuoso/x11.py:34-57`).

### 2.7 Focused-window snapshot API

| Entry point | Exact signature | Return / behavior |
|---|---|---|
| `classify_window` | `(title: str) -> str` | Regex classification: `maestro`, `schematic`, `layout`, `waveform`, `hierarchy`, `ciw`, otherwise `unknown`. |
| `snapshot` | `(client: VirtuosoClient, *, kind: str | None = None, **kwargs: Any) -> dict` | Returns `{"kind", "window_title", "supported", "data"}`; only `kind="maestro"` is wired to a real aggregator, other kinds return `supported=False`. |

### 2.8 Response / SKILL-output decoders

| Entry point | Exact signature | Return / behavior |
|---|---|---|
| `response_fields` | `(response: Any) -> tuple[list[str], Any, str]` | Accepts dict or object; sees `errors/status/output` at top level or under `result`; normalizes errors to `list[str]` and output to `str`. |
| `parse_skill_str_list` | `(raw: str) -> list[str]` | Returns `[]` for empty/`nil`; recursively collects string atoms from lists or bare quoted tokens. |
| `tokenize_top_level` | `(body: str, *, include_groups: bool = True, include_strings: bool = False, include_atoms: bool = False, max_tokens: int | None = None) -> list[str]` | Quote/paren-aware tokenizer; does not validate balanced input. |
| `scan_top_groups` | `(body: str) -> list[str]` | Top-level parenthesized groups only. |
| `parse_sexpr` | `(tok: str)` | `nil -> None`, `t -> True`, strings unescaped, lists recursive, atoms left as strings. |
| `is_single_complete_skill_list` | `(raw: str) -> bool` | Checks one balanced top-level list with quote/escape awareness. |

Important decoder rules: only `\n`, `\t`, `\r`, `\"`, and `\\` are decoded; unknown escapes remain `\x` (`skill_output.py:164-183`). `parse_sexpr` leaves numbers and symbols as strings, so callers must coerce numeric fields (`skill_output.py:69-95`).

## 3. Capability decomposition

Each capability below is a candidate upper-layer business unit. It validates inputs and orchestration only; transport, SSH, sockets, ports, tunnels, profiles, registry, and environment lookup must be delegated to middle.

### 3.1 Library inventory and metadata

- Business inputs: optional timeout; no path inputs for `list`/`get`.
- Outputs: `list[str]` or `LibraryInfo(name, path, technology_library)`.
- Sub-steps: issue `ddGetLibList()`; issue `ddGetObj(name)` + read `~>readPath` + `techGetTechLibName`; parse a single balanced SKILL list; map error codes to stable business errors.
- Middle interfaces: Skill only. No `command` or `file`.

### 3.2 Library create/delete/rename and technology binding

- Business inputs: `name`, explicit remote `path`, optional existing technology library, operation-specific timeout.
- Outputs: verified `LibraryInfo`, verified technology name, or `None`.
- Sub-steps: validate non-empty strings; preflight existing/absent objects; call supported `ddCreateLib`, `ddDeleteObj`, `ccpRename(..., nil)`, `techBindTechFile`, or `techSetTechLibName`; read the result back; surface partial create+bind failure without deleting or retrying.
- Middle interfaces: Skill only. A new package must not parse or edit `cds.lib`, `lib.defs`, or library directories as a fallback.

### 3.3 Flat category management

- Business inputs: library, category, optional destination name/new cell, timeout.
- Outputs: category name, `list[str]`, or `None`; partial mutation errors include library/category context.
- Sub-steps: validate names; open category read/append; filter stale names; filter member pairs to `"cell"`; add/subitem, save, close, reopen and verify. Rename is copy-then-remove because no direct `ddCat` rename exists.
- Middle interfaces: Skill only. Direct `.TopCat`/`.Cat` parsing or editing is out of contract.

### 3.4 Cell/view enumeration and library harvest

- Business inputs: library name, optional cell/view filters, local output directory if persisting a report.
- Outputs: libraries → cells → views, classified session/schematic/config views; Maestro setup names, analysis names and result-directory existence; normally JSON.
- Sub-steps: load `harvest_library.il`, list `ddGetObj(lib)~>cells`, list each cell's views, classify by prefixes, probe `maeGetSetupNames`/`maeGetEnabledAnalysis`, resolve `libPath -> writePath -> readPath`, normalize `nil`.
- Middle interfaces: `execute_skill` for all Virtuoso data; `upload_file` for the IL asset when needed; local Python for normalization/JSON. The IL procedures are a compatibility convention, not the new interface.

### 3.5 Cellview open/save/close and current design

- Business inputs: library, cell, view, view type, Cadence mode (`a`/`w`/`r`), timeout.
- Outputs: `VirtuosoResult`/new `VirtuosoResult`; current design tuple in legacy.
- Sub-steps: validate/derive view type; build `dbOpenCellViewByType` or `geOpen`; bind global `cv`; save/close; optionally query current edit cellview.
- Middle interfaces: Skill only. Any path parsing from `ddGetObjReadPath` is remote POSIX data and must not be treated as a local filesystem path.

### 3.6 Layout/schematic/symbol editor batches

- Business inputs: lib/cell/view, explicit create vs modify mode, queued SKILL builders or domain-specific helpers, timeout.
- Outputs: `None` on clean batch success; `RuntimeError` on batch failure; editor object exposes `commands`.
- Sub-steps: `create()` selects Cadence `"w"`; `modify()` selects `"a"`; `edit()` is deprecated and defaults to `"a"`; `__enter__` queues open; `add()` queues operations; clean `__exit__` queues check (schematic/symbol) and save, then executes one `progn`; exception exit does not flush.
- Middle interfaces: `execute_skill` only. The upper package should preserve the one-batch atomic-intent behavior even though the daemon executes a whole script.

### 3.7 Generic SKILL composition and IL loading

- Business inputs: ordered SKILL strings; IL path; optional remote path; timeout.
- Outputs: composed script result or load result with metadata.
- Sub-steps: filter blank commands; reject empty batch; preserve a single existing `progn`; join with newlines; optionally wrap in `progn(...)`; upload/cache IL when needed; execute `load("path")`.
- Middle interfaces: `upload_file` for local IL→remote path; `execute_skill` for the load. The new layer must decide remote path explicitly instead of deriving `remote_work_dir` from a tunnel.

### 3.8 SKILL Finder discovery and search

- Business inputs: query, mode, limit, include-description flag, optional finder root/cache root.
- Outputs: list of dicts `name/syntax/description/source_file`.
- Sub-steps: locate `doc/finder/SKILL` by `which virtuoso` + parent walk; recursively copy `.fnd`; parse three-line records; dedupe by name; search exact/prefix/suffix/fuzzy/regex; sort/limit and format. Local mode reads directly.
- Middle interfaces: `run_command` to locate `virtuoso`; File interface for recursive `.fnd` transfer; local Python for parsing/search. The current command uses a login shell/cshrc; the new command role must define equivalent shell/environment semantics.

### 3.9 More Info lookup

- Business inputs: function name, optional doc root/cache root.
- Outputs: dict `func_name/file_path/topic/raw_html/plain_text`.
- Sub-steps: locate Cadence doc root; download only `api_more_info/api_more_info.tgf`; parse lower-cased function key and `_ocean`/`_viva_skill` fallbacks; download one referenced HTML; extract modern topic, legacy anchor/heading, or whole file; convert to Markdown via `markdownify`.
- Middle interfaces: File interface for `.tgf`/HTML; local Python for parsing/conversion. `run_command` is needed only to discover the root if no explicit root is supplied.

### 3.10 Cadence documentation discovery/search/index

- Business inputs: query, limit, optional explicit doc roots, optional cache root, rebuild flag.
- Outputs: `{"doc_roots": [...], "results": [...]}` with document/topic result dicts.
- Sub-steps: discover roots from explicit config, doc env vars or install-root env vars; scan suffix whitelist; parse topic maps; extract HTML/text; score/dedupe; build a versioned SQLite index and manifest; remote path uses `run_command` to generate `remote_records.jsonl.gz`, then downloads it and indexes locally; fallback downloads candidate files and remaps paths.
- Middle interfaces: `run_command` for discovery, `find/grep` candidate search and remote index generation; `download_file` for record stream/files; local Python/SQLite for indexing and ranking. Normal file reads are local-cache-only.

### 3.11 SKILL-window inventory versus X11-window inventory

- Business inputs: optional timeout for SKILL `list_windows`; profile/display/top-level for X11 `list_windows`.
- Outputs: SKILL form `[{num,name}]`; X11 form `[{frame_id,window_id,dismiss_id,title,class,geometry,mapped,kind,suggested_action,display?}]`.
- Sub-steps: SKILL path calls `hiGetCIWindow()` + `hiGetWindowList()` and formats `num|name;`; X11 path runs helper and parses `xwininfo` tree records.
- Middle interfaces: SKILL inventory → `execute_skill`; X11 inventory → `run_gui_command` (one-shot GUI). The two must not be conflated in the business API.

### 3.12 Screenshot capture

- Business inputs: target (`ciw`, `current`, integer window number, or view name), local output path/directory, timeout.
- Outputs: `VirtuosoResult` whose `output` is the local destination on download success.
- Legacy sub-steps: resolve SKILL window expression; derive remote screenshot directory; `mkdir -p`; execute `hiWindowSaveImage(?target w ?path "..." ?format "png" ?toplevel t)`; download PNG.
- Middle interfaces per new spec: `run_gui_command` is the intended owner for X11 screenshot; File interface must retrieve the generated file if GUI/file roles are not path-visible. Legacy code instead uses `execute_skill` + File. This is a major migration ambiguity.

### 3.13 GUI window discovery, dialog recovery and CIW bootstrap

- Business inputs: explicit display or GUI-role display resolution; optional top-level flag; explicit window id/action; generated `virtuoso_setup.il` absolute path.
- Outputs: window/dialog records, dismissal records with `still_mapped`, or bootstrap record `{"bootstrapped","command"}`; errors are structured dicts.
- Sub-steps: discover interactive Virtuoso PID environments; enumerate mapped root frames; recursively inspect children; filter WM_CLASS; classify CIW/modal/dialog/main; select exact target; inject XTest key events; verify mapping; for bootstrap verify exactly one CIW across displays and type only `load("<setup>")` plus Return.
- Middle interfaces: `run_gui_command` only for X11/helper execution; File interface only if a predeployed helper asset must be transferred; Skill must not be used to bypass a blocking modal dialog.

### 3.14 Focused-window snapshot and title classification

- Business inputs: optional explicit kind and kind-specific kwargs.
- Outputs: envelope `kind/window_title/supported/data`.
- Sub-steps: one SKILL call for `hiGetCurrentWindow()~>name`; decode title; regex-classify; dispatch to Maestro aggregator if supported; return `supported=False` for all other kinds.
- Middle interfaces: `execute_skill` for focus/title and all current Maestro data. Future schematic/layout snapshots may add more Skill bundles, not command/file/SSH calls.

### 3.15 File upload/download and sanitization example

- Business inputs: local/remote source and destination, recursive flag, optional sanitizer policy.
- Outputs: new `CommandResult`; legacy `VirtuosoResult` with destination output.
- Sub-steps: local existence checks; remote tunnel/file copy; local `copy2` or `copytree`; recursive overlap guard in local copy; optional project-level sanitizer writes a sibling `sanitized/<name>` copy.
- Middle interfaces: File interface only for transport; local filesystem/sanitizer is pure Python business policy. The new upper layer must never reach `_tunnel`, `_ssh_runner`, or remote-path derivation helpers.

### 3.16 Diagnostic filesystem probes

- Business inputs: library name, optional view filter.
- Outputs: `.cdslck` paths, contents, owner/host/pid/start-time and age.
- Sub-steps: resolve `ddGetObj(lib)~>readPath`; run `find`, `cat`, and `stat -c %Y`; format ages. Never delete locks automatically; a human must confirm.
- Middle interfaces: `execute_skill` for the library path; `run_command` for `find`/`cat`/`stat`. The legacy example bypasses that discipline via `client.ssh_runner.run(...)` and must be redeveloped.

## 4. GUI-role command catalog

This section separates commands that are directly evidenced in legacy code from migration-only equivalents. All commands are intended for the new `gui` role via `run_gui_command`; they are one-shot and do not preserve cwd/environment.

### 4.1 Environment and interpreter discovery

| Command / environment fact | Exact legacy text or rule | Purpose and citation |
|---|---|---|
| X11 display precedence | explicit `display` argument → `VB_DISPLAY` → helper auto-detection (`None`) | Legacy wrapper resolution; no default literal display. `src_bak/virtuoso_bridge/virtuoso/x11.py:26-31`. |
| Interactive Virtuoso PID discovery | `pgrep -u <USER> -x virtuoso` | Finds processes owned by a user; `USER` defaults to process environment. `x11_dismiss_dialog.py:36-43`. |
| Batch-process exclusion | read `/proc/<pid>/cmdline`; if it contains `b"-nograph"`, skip it | Avoids ownership by non-GUI batch Virtuoso. `x11_dismiss_dialog.py:48-54`. |
| Display/auth extraction | read `/proc/<pid>/environ`; split on `\0`; capture bytes starting `DISPLAY=` and `XAUTHORITY=` | Produces candidate X11 environments; if a display is absent the candidate is discarded. `x11_dismiss_dialog.py:55-68`. |
| Environment de-duplication | key `(DISPLAY, XAUTHORITY)` | Avoids duplicate dialogs/windows from multiple Virtuoso PIDs on one display. `x11_dismiss_dialog.py:73-80`. |
| Apply one environment | set `os.environ["DISPLAY"]`; set `os.environ["XAUTHORITY"]` only when nonempty | Makes ctypes/XTest and `xwininfo` target the discovered display. `x11_dismiss_dialog.py:328-335`. |
| Python interpreter probe | `python3 --version 2>/dev/null && echo "CMD:python3" || (python --version 2>&1 | grep -q "Python" && echo "CMD:python") || (python2 --version 2>&1 | grep -q "Python" && echo "CMD:python2") || echo "CMD:NONE"` | Prefer Python 3, then generic Python, then Python 2; fallback string is `python3` after parsing. `src_bak/virtuoso_bridge/virtuoso/x11.py:60-77`. |
| Remote helper directory | `mkdir -p <default_virtuoso_bridge_dir(user, "x11", client_id)>` | Ensures helper parent exists; helper is then uploaded as `x11_dismiss_dialog.py`. `src_bak/virtuoso_bridge/virtuoso/x11.py:80-97`. |
| GUI one-shot wrapper form | `"{py} {script} [args] [display]"` | All wrapper calls append the display only when explicitly resolved; otherwise helper discovers it. `src_bak/virtuoso_bridge/virtuoso/x11.py:110-214`. |
| Local wrapper form | `sh -c <cmd>` with capture/timeout | Only used when `runner is None`; return code 124 means timeout, 127 means no shell. `src_bak/virtuoso_bridge/virtuoso/x11.py:34-57`. |
| X11 libraries | `libX11` and `libXtst` resolved through `ctypes.util.find_library` | Required for direct XTest key injection; missing libraries return structured errors. `x11_dismiss_dialog.py:563-569,468-471`. |
| `XAUTHORITY` fallback | explicit display path defaults auth to `os.environ.get("XAUTHORITY")` | The new GUI role must propagate/derive authorization explicitly; a display string alone is insufficient. `x11_dismiss_dialog.py:765-768`. |

### 4.2 Commands actually run by the helper

| Exact argv / command shape | Purpose and parsing notes | Citation |
|---|---|---|
| `["pgrep", "-u", user_or_USER_env, "-x", "virtuoso"]` | Enumerate interactive Virtuoso PIDs. | `src_bak/virtuoso_bridge/resources/x11_dismiss_dialog.py:40-43`. |
| `["xwininfo", "-root", "-children"]` | Enumerate top-level root frames. Parser starts only after a line containing `child`/`children` and `:`. | `x11_dismiss_dialog.py:158-182`. |
| `["xwininfo", "-id", "<frame_id>"]` | Read mapped state and absolute geometry for a root frame. Fields parsed: `Absolute upper-left X`, `Absolute upper-left Y`, `Width`, `Height`; `Map State` containing `IsViewable` means mapped. | `x11_dismiss_dialog.py:130-155`. |
| `["xwininfo", "-id", "<frame_id>", "-tree"]` | Recursively inspect child windows when `top_level=False`. Tree/children lines are parsed for id, quoted title, parenthesized WM_CLASS and geometry. | `x11_dismiss_dialog.py:185-199`; `_parse_window_line` at `:92-119`. |
| `["xwininfo", "-id", "<frame_id>", "-children"]` | One-level child inspection for top-level mode. | `x11_dismiss_dialog.py:185-191`. |
| `["xwininfo", "-id", "<application_child_id>", "-children"]` | Legacy auto-dismiss helper: find first named child of a WM frame for focus. | `x11_dismiss_dialog.py:348-361`. |
| `python x11_dismiss_dialog.py [DISPLAY]` | Find dialog candidates without dismissal. | `src_bak/virtuoso_bridge/virtuoso/x11.py:110-118`. |
| `python x11_dismiss_dialog.py --list-windows --json [--top-level] [DISPLAY]` | Enumerate without touching windows. | `src_bak/virtuoso_bridge/virtuoso/x11.py:121-139`. |
| `python x11_dismiss_dialog.py --dismiss-window <id> --action <action> [DISPLAY]` | Explicit dismissal; actions are `enter`, `escape`, `alt-o`, `alt-y`, `alt-n` (aliases `esc`, `ok`, `yes`, `no` exist in helper). | `src_bak/virtuoso_bridge/virtuoso/x11.py:142-163`; action mapping `x11_dismiss_dialog.py:429-444`. |
| `python x11_dismiss_dialog.py --bootstrap-window <id> --setup-path <absolute_setup_path> [DISPLAY]` | Inject exactly one generated `load(...)` expression into a verified CIW. | `src_bak/virtuoso_bridge/virtuoso/x11.py:166-187`; helper `x11_dismiss_dialog.py:525-553`. |
| `VB_SAVE_DIALOG_POLICY=<value> VB_SAVE_DIALOG_CONTEXT=<value> python x11_dismiss_dialog.py --dismiss [DISPLAY]` | Auto-dismiss candidate dialogs; policy/context are prefixed only when nonempty. | `src_bak/virtuoso_bridge/virtuoso/x11.py:190-214`. |

The helper does not use `xdotool`, `wmctrl`, `scrot`, ImageMagick, or `xwd` in this legacy implementation. If the new GUI role replaces explicit `xwininfo` parsing, equivalent migration commands are `wmctrl -lpGx` or `xdotool search --onlyvisible --class virtuoso ...`; those are new implementation choices, not legacy evidence.

### 4.3 Window-line parsing and de-duplication

The `xwininfo` child/tree line used by `_parse_window_line` is parsed as follows (`x11_dismiss_dialog.py:92-119`):

1. Strip the line; require it to start with `0x`; split once on whitespace. The first token is the window id.
2. If a double-quoted substring exists, use the first `"..."` as the title.
3. Find `: (<stuff>)` and extract all quoted class tokens with `re.findall(r'"([^"]*)"', ...)`.
4. Find `(\d+)x(\d+)([+-]\d+)([+-]\d+)` and store integer `w`, `h`, `x`, `y`; missing geometry stays `{}`.
5. A WM frame may have no title and no class; its child carries the application title/class.

`discover_windows(display, top_level=False)` then (`x11_dismiss_dialog.py:250-288`):

- sets `DISPLAY` for the process;
- ignores root frames whose `Map State` is not `IsViewable`;
- obtains children with `-tree` unless `top_level=True`, then `-children`;
- keeps children whose WM_CLASS contains case-insensitive `virtuoso` or `libManager` (`VIRTUOSO_WM_CLASSES` at `:29`);
- appends the frame itself if its own class matches;
- in top-level mode chooses exactly one child per frame: a CIW child if found, else the first titled child, else the first app child;
- de-duplicates with `frame_id` as the key in top-level mode, or `(frame_id, dismiss_id)` in normal mode;
- emits the frame geometry on every record, even when title/class came from the child;
- returns records through `classify_windows`.

### 4.4 Classification and safety guards

`classify_windows` adds `kind` and `suggested_action` (`x11_dismiss_dialog.py:214-247`):

| Rule | Result |
|---|---|
| title contains `command interpreter` or a word-boundary `ciw` | `kind="ciw"`, `suggested_action=None` |
| known modal title | `kind="known_modal"`, action from `KNOWN_MODAL_ACTIONS` |
| dialog-sized geometry | `kind="dialog_candidate"`, `suggested_action="enter"` |
| otherwise | `kind="main_window"`, `suggested_action=None` |

Known-modal actions are: `"ade explorer update and run" -> "enter"`, `"ade assembler message 1749" -> "alt-o"`, and `"save as"`/`"save a copy"` -> `"escape"` (`x11_dismiss_dialog.py:30-33,214-221`). Dialog-sized means width ≥20, height ≥20, height ≤420, and not `(width > 1000 and height > 300)` (`:202-211`). Automatic dismissal is limited to `known_modal` and `dialog_candidate` (`:291-312`). CIW/main windows are never auto-dismiss targets.

Explicit dismissal safety (`x11_dismiss_dialog.py:556-713`):

- requires `libX11` and `libXtst`;
- in legacy auto mode, resolves the first named child of a WM frame; in explicit `--action` mode, focuses the caller-provided target exactly;
- raises and focuses the target with `XRaiseWindow` + `XSetInputFocus` before injection;
- supports Enter, Escape, Alt-Y, Alt-O, Alt-N; default is Enter;
- save-as policy is `smart` by default: `discard`→Alt-N, `save`→Alt-Y, `cancel`→Escape, `dedupe` context→Alt-N, otherwise Escape;
- if the save-as path throws, sends bare `n`;
- after a dismissal, the main loop sleeps 0.3 s and re-reads the target mapping; `still_mapped=true` means failure.

Bootstrap safety is stricter (`x11_dismiss_dialog.py:450-553,796-834`):

- `setup_path` must be absolute;
- basename must be exactly `virtuoso_setup.il`;
- newline, carriage return, and NUL are rejected;
- only `load("<escaped absolute path>")` is typed; no arbitrary SKILL argument exists;
- the requested id must resolve to a top-level Virtuoso window;
- the selected window's `kind` must be `ciw`;
- if the id matches CIWs on more than one display, injection is refused and the user must set `VB_DISPLAY`;
- text is ASCII-only, mapped to keycodes with XTest, then Return is injected;
- CLI then polls the daemon rather than assuming the load succeeded (`src_bak/virtuoso_bridge/cli.py:1097-1179`).

### 4.5 Screenshot commands and the GUI-role gap

Legacy screenshot does not run `import`, `scrot`, `gnome-screenshot`, or `xwd`. Its path is (`src_bak/virtuoso_bridge/virtuoso/basic/bridge.py:541-624`):

1. Choose a SKILL window expression:
   - `ciw` → `hiGetCIWindow()`
   - `current` → `hiGetCurrentWindow()`
   - int → `foreach(w hiGetWindowList() when(w~>windowNum==<int> found=w))`
   - string → match `w~>cellView~>viewName == "<string>"`
2. Derive a remote screenshot directory under the legacy bridge scratch root.
3. Run `mkdir -p <screenshot_dir>` directly over the SSH runner (`basic/bridge.py:590-591`; example also does this at `examples/01_virtuoso/basic/06_screenshot.py:59-65`).
4. Execute SKILL:
   `hiWindowSaveImage(?target w ?path "<remote_path>" ?format "png" ?toplevel t)`.
5. Download the PNG through the legacy file path.

The bundled `assets/screenshot.il` uses a slightly different wrapper, `hiWindowSaveImage(... ?toplevel nil)`, and takes the current window from `hiGetCurrentWindow()` (`examples/01_virtuoso/assets/screenshot.il:1-16`). Any new GUI screenshot package must decide whether to preserve the `?toplevel` value and whether the capture is semantic SKILL capture or a pixel-level X11 capture. A migration-only X11 alternative is `import -window <id> <path.png>` (ImageMagick) or `scrot -u <path.png>`, but neither is legacy behavior and both require a correctly selected window and `DISPLAY`/`XAUTHORITY`.

### 4.6 GUI command return contract expected by upper layer

The legacy `x11.py` functions return JSON-derived `list[dict]`, not `CommandResult`. The new upper package should wrap each `run_gui_command` call with:

- return-code check (`CommandResult.returncode == 0`, with bridge `kind` respected);
- JSON-lines parse, ignoring non-JSON diagnostics;
- preservation of helper error objects (`{"error": ..., "returncode": ...}` or helper-specific errors);
- no retry of a dismissal/bootstrap command after a transport or timeout result (`kind=unknown-effect` semantics);
- display/uniqueness validation before any injection.

## 5. Data formats and parsers

### 5.1 Library protocol records

Library operations do not transport JSON objects. `execute_skill` returns a printed SKILL s-expression, and the upper business layer must require exactly one balanced top-level list (`skill_output.is_single_complete_skill_list`) before parsing it.

| Record | Meaning |
|---|---|
| `("ok")` | Mutation succeeded with no payload. |
| `("ok" ("analogLib" "basic"))` | Library name list. |
| `("ok" ("library" "demoLib" "/work/demoLib" "gpdk045"))` | `LibraryInfo`; fourth item may be `nil` for unbound technology. |
| `("error" "libraryNotFound")` | Stable error code mapped by management code. |
| `("partial" "technologyBindingFailed" info)` | Library exists but requested technology binding failed; raises `LibraryPartialSuccessError`. |
| `("ok" "ADC")` | Category create/rename result. |
| `("ok" ("ADC" "DAC"))` | Category name list. |
| `("ok" ("comparator" "strongarm"))` | Category cell-member list. |
| `("partial" "categoryRenameSourceRemovalFailed")` | Category mutation may have persisted partially; raises `CategoryPartialSuccessError`. |

Validation changes the record into a typed local object; malformed output, transport errors, or unrecognized status codes raise `RuntimeError`. The parser treats bare numbers/symbols as strings and only maps `nil`/`t` specially (`skill_output.py:69-95`).

### 5.2 `cds.lib` / `lib.defs` and category XML

No `lib.defs`, `cds.lib`, `.TopCat`, or `.Cat` parser exists in the scoped code. The scoped library API deliberately uses Cadence DD APIs (`ddGetObj`, `ddCreateLib`, `ddDeleteObj`, technology APIs, `ddCat*`) and the reference explicitly says “No category operation edits `.Cat` or `.TopCat` files directly” (`skills/virtuoso/references/library-python-api.md:96-103`).

Observed external semantics:

- `cds.lib` is a registration/mapping file containing `DEFINE <logical_lib> <path>` and `INCLUDE` chains; examples require the target library to already be registered before tooling writes to it (`examples/01_virtuoso/digital_import/import_gds.py:101-109`; `import_verilog.py:136-144`).
- The research data model identifies `cds.lib`/`libList` as the logical-library→filesystem mapping and recommends DD/library APIs or a controlled tool for updates (`spec/research/01-virtuoso-data-model-and-editing.md:15-19,44-47`).
- Category state belongs to Cadence’s DD layer. The legacy API does not expose XML syntax, member ordering guarantees, nesting support, locking, or atomicity. A new upper package should either continue to call `ddCat*` SKILL or make a separate, explicitly documented parser/locking contract. It must not silently treat categories as arbitrary XML.

### 5.3 SKILL Finder `.fnd` format

`parse_fnd_file` reads UTF-8 with replacement, drops lines beginning exactly with `;`, then applies this regex (`skill_finder/parser.py:40-89`):

```text
\("([^"]+)"\s*\n\s*"((?:[^"\\]|\\.)*)"\s*\n\s*"((?:[^"\\]|\\.)*)"\s*\)
```

Each accepted record becomes a `SkillEntry` with `source_file=path.name`; names/syntax/description are stripped; records without both name and syntax are ignored. `parse_fnd_directory` recursively matches `*.fnd`, and keeps the first occurrence of each exact name (`parser.py:92-118`).

### 5.4 More Info `.tgf` and HTML formats

`api_more_info/api_more_info.tgf` records are whitespace-separated and support either a quoted topic or `NULL`:

```text
<func_name> <file_path_from_$root> "topic" HTML
<func_name> <file_path_from_$root> NULL HTML
```

`parse_tgf_index` accepts quoted-topic and NULL forms, ignores blank/`;`/`#` lines, strips a CR, lower-cases keys, and keeps the first duplicate (`skill_finder/more_info.py:17-76`). `resolve_doc_path` strips a leading `$` and resolves relative to `tgf_path.parent.parent` (`:79-81`).

HTML extraction order is:

1. Modern `<!-- [TOPIC_START_OPEN]... [TOPIC_START_ATTR]text=<topic> -->` through `<!-- [TOPIC_END] -->`.
2. Legacy `<a id>`/`<a name>` anchor followed by the nearest heading, with section end at the next heading of the same or higher level.
3. Heading text equal to the topic after stripping nested tags (handles names split by anchors).
4. Optional whole-file fallback for single-function/legacy pages.

`html_to_plain_text` removes empty/self-closing `<code>` tags before `markdownify`, uses ATX headings, no code language, `**` bold, and `_` italics (`more_info.py:184-206`).

### 5.5 Cadence documentation search formats

Search suffixes are exactly `{".html", ".htm", ".txt", ".xml", ".json", ".tgf"}`; content suffixes exclude `.tgf` (`docs_search.py:20-25`). Text reads try UTF-8, UTF-16, Latin-1, then UTF-8 replacement (`:687-694`). HTML parsing removes `<script>`/`<style>` and extracts `<title>` plus body data with a permissive `HTMLParser` (`:78-114`).

A `.tgf` topic-map line is `topicId target_ref anchor HTML`; `target_ref` may be `$docSet/path` or a relative/absolute path (`docs_search.py:156-188,561-569`). The canonical indexed topic map is only `api_more_info/api_more_info.tgf` (`:1065-1066`). Search result scoring uses:

- document term score: +8 title, +5 relative path, +1 body;
- topic base score +2;
- direct filename candidate +20;
- title exact +120, stem exact +90, compact title +55, compact stem +40, identifier title +30, `/sk*/ref/` or `/mae*/ref/` +10.

Query terms are lower-cased, stopwords are removed when any meaningful term remains, and simple plurals are stemmed (`-ies`, `-ches`, `-shes`, `-sses`, `-xes`, `-zes`, trailing `s`) unless the term looks like an API identifier (`docs_search.py:584-636,1172-1238`). Duplicate results at the same logical location are collapsed, preferring a document hit over a topic hit (`:1204-1223`).

### 5.6 SQLite index / manifest / remote record stream

The cache index is schema version 3 (`docs_search.py:24`). Tables are:

| Table | Columns |
|---|---|
| `documents` | `path`, `relative_path`, `suffix`, `title`, `text`, `search_text`; primary key `path` |
| `topics` | `path`, `relative_path`, `line`, `topic_id`, `anchor`, `target_path`, `target_relative_path`, `title`, `text`, `search_text` |

Both tables have a `search_text` index; SQLite pragmas are `journal_mode=OFF` and `synchronous=OFF` for build speed (`:965-993`). `manifest.json` stores `schema_version`, `doc_root`, `built_at`, document/topic counts, and for remote builds `remote_records_path` (`:816-829,866-880`). The index is trusted only if schema version and `doc_root` match (`:779-788`).

Remote indexing generates a gzip JSONL stream named `remote_records.jsonl.gz`. Each line is a JSON object with `kind` `document` or `topic`; document records carry `path/relative_path/suffix/title/text`, while topic records carry `path/relative_path/line/topic_id/anchor/target_path/target_relative_path/title/text` (`docs_search.py:1272-1410`). The remote helper emits a final JSON summary `{"path": "...", "documents": N, "topics": M}`; the downloader parses the last JSON line and removes the remote temporary file in `finally` (`:883-913`).

The remote shell command is `_remote_doc_index_command(doc_root)`, a bash script that picks a usable Python from `$CDSHOME/tools.lnx86/python/64bit/bin/python3`, `<install-root>/tools.lnx86/python/64bit/bin/python3`, `python3`, or `python`, then runs the embedded Python 2/3-compatible indexer (`docs_search.py:1240-1410`). It is invoked with `middle.run_command`, not `run_spectre_command`; the File interface transfers the resulting gzip.

### 5.7 X11 window-list formats

Legacy helper output is JSON lines. A plain discovery record has:

```json
{"frame_id":"0xf00","window_id":"0xc10","dismiss_id":"0xc10",
 "title":"Virtuoso Command Interpreter Window",
 "class":["virtuoso","Virtuoso"],
 "geometry":{"w":1200,"h":800,"x":0,"y":0},
 "mapped":true,"kind":"ciw","suggested_action":null,"display":":7"}
```

`find_dialogs` additionally flattens geometry into `x/y/w/h` and retains `kind`/`suggested_action` (`x11_dismiss_dialog.py:295-313`). The CLI display format uses `dismiss_id` first, then `window_id`, and prints `window_id [kind] title WxH+X+Y action=...` (`src_bak/virtuoso_bridge/cli.py:1033-1064`).

`xwininfo` parsing is not a general parser: it assumes the one-line child format emitted by this helper/tool version and does not support arbitrary title escaping, multiple quoted fields, or a different geometry unit. A new package must either preserve the exact parser assumptions or replace it with a documented structured X11 backend.

### 5.8 SKILL output decoding rules to replicate

- `nil` maps to `None`; `t` maps to `True`.
- Quoted strings are unquoted and only common escapes are decoded.
- Lists are recursively parsed.
- Bare numbers and symbols remain strings.
- Tokens must be scanned quote/paren-aware; nested groups and escaped quotes must not split.
- A structured library/category response must be exactly one complete top-level list before parsing.
- `%L`-printed string lists can be bare quoted tokens or nested lists; collect recursively.

These are the rules currently used by library/category parsing and by `fetch`/`fetch_one` (`src_bak/virtuoso_bridge/virtuoso/basic/bridge.py:635-699`).

## 6. Pure-Python vs SKILL vs external-tool split

| Capability / sub-step | Pure Python | SKILL via `execute_skill` | External tool / command | File interface |
|---|---|---|---|---|
| Library list/get/create/delete/rename/technology | validation, record parsing, error mapping | all DD/technology operations and read-back | none | none |
| Category list/create/delete/add/remove/rename | validation, record parsing, partial-error classification | all `ddCat*` operations and read-back | none | none |
| Cell/view harvest | normalization, JSON, classification | `ddGetObj`, `mapcar`, `maeGetSetupNames`, result-path probes | none if IL asset is preloaded; otherwise upload | IL input transfer |
| Cellview open/save/close | view-type derivation, parameter validation | `dbOpenCellViewByType`, `geOpen`, `dbSave`, `dbClose`, `hiWindowSaveImage` | none | none |
| Editor batches | command composition and response validation | whole batch in one `progn` | none | none |
| SKILL Finder discovery | local walk-up, cache markers, parsing/search | none | `which virtuoso`, cshrc-sourced login shell, parent walk | recursive `.fnd` download |
| More Info | `.tgf` parsing, HTML extraction, Markdown conversion | none | optional root discovery command | `.tgf` and HTML download |
| Docs discovery | env/root parsing, scoring, SQLite schema | none | `find`/`grep` and remote index shell command | record-stream/candidate download |
| SKILL window inventory | list formatting and octal decoding | `hiGetWindowList`, `hiGetWindowName`, `hiGetCIWindow` | none | none |
| X11 window inventory | JSON-line parsing, classification, de-duplication | none | `pgrep`, `/proc`, `xwininfo` | helper upload only in legacy |
| Dialog dismissal | action/policy selection, result verification | none | `libX11` + `libXtst` XTest key events | helper upload only in legacy |
| CIW bootstrap | path validation, uniqueness checks, result parsing | none | XTest ASCII typing + Return | helper upload only in legacy |
| Screenshot | target validation and output naming | legacy `hiWindowSaveImage` | GUI screenshot command if redeveloped in `gui` role | remote PNG download |
| Snapshot | title classification and envelope | focused-window probe; Maestro aggregator | none | none |
| File sanitization | redaction policy and local sibling write | none | none | transport both raw and sanitized copy as business policy |

The hard boundary: “run a shell command” is never equivalent to `execute_skill("system(...)")` or `execute_skill('csh("...")')`. The former belongs to `run_command`/`run_gui_command`; the latter remains only a Skill expression and returns `t`/`nil`, not captured stdout (`skills/virtuoso/references/troubleshooting.md:9-20`).

## 7. State/files/IPC dependencies and re-development risks

| Legacy dependency | Why it will not exist in the upper layer | Required replacement / risk |
|---|---|---|
| `VirtuosoClient` object with `_host`, `_port`, `_timeout`, `_tunnel` | Upper layer may not own sockets, ports, tunnels or session objects | Route every operation through middle; do not expose client properties in business signatures. |
| `VirtuosoClient.from_env()`, profiles, `.env`, `VB_*` variables | Registry/token routing replaces environment/profile resolution | Upper package must require explicit business inputs/token; no role discovery. |
| `client._tunnel`, `client._ssh_runner`, `runner.run_command`, `runner.upload` | Private transport state and SSH are outside the 5-interface contract | Replace with `run_gui_command`, `run_command`, `upload_file`, `download_file`; remove direct runner access from examples. |
| Daemon TCP framing (`STX`/`NAK`, JSON payload, `_RECV_BUF_SIZE`) | Middle owns Skill transport and result normalization | Consume `VirtuosoResult`; do not parse frames or implement retries for Skill side effects. |
| `execute_skill("csh(...)"); run_shell_command()` | Shell return is `t`/`nil`, not stdout; upper may not subprocess/SSH | Use `run_command` and inspect `returncode/stdout/stderr/kind`; keep csh compatibility only if a legacy Skill expression requires it. |
| `system("find ...")` in diagnostics | `system()` return is unreliable and not file-level evidence | Use `run_command` for `find`, `cat`, `stat`; do not use Skill to read files. |
| `SSHRunner.download`, `runner.download`, recursive `.fnd` cache | File role/topology is explicit in new architecture | Use File interface and keep local cache paths only in the upper process. |
| `default_virtuoso_bridge_dir`, `resolve_client_id`, `remote_work_dir` | These encode legacy scratch/client/profile conventions | Upper layer needs an explicit role-relative/absolute path convention from the caller or a middle service; do not reproduce these helpers. |
| Local-vs-remote path ambiguity (`Path.as_posix`, `p.is_file()`, `destination.parent.mkdir`) | `local_path` and `remote_path` are different namespaces; upper cannot infer host filesystem | Validate which side each path belongs to; pass local paths to File interface; never call `Path.exists()` on a remote path. |
| `screenshot` remote path and `mkdir -p` through tunnel | GUI/file/daemon roles may be different hosts | Choose a role-visible path; if GUI and file roles differ, use a GUI command that writes to a file-role-visible location or returns bytes through a controlled path. |
| X11 helper deployment via upload to scratch | `run_gui_command` is one-shot and there is no upload-to-GUI interface | Predeclared helper path or self-contained command are the only observable options; topology must be explicit. This is a blocking design question. |
| `DISPLAY`/`XAUTHORITY` inherited from legacy process | GUI one-shot commands do not preserve caller env | Resolve explicit display/auth in command construction or make helper inspect `/proc`; never assume ambient env. |
| `VB_DISPLAY`, `VB_SAVE_DIALOG_POLICY`, `VB_SAVE_DIALOG_CONTEXT` | Upper layer cannot read/write env as routing state | Promote policy/context to explicit package parameters; display should be a package/GUI-role parameter. |
| `mae*` / `maestr*` SDK imports inside `snapshot` | Maestro-specific implementation is outside this inventory but relies on same session | Keep it as a Skill-only downstream package; no SSH fallback. |
| `markdownify` dependency for More Info | Pure Python dependency; no transport/session state | Preserve dependency or replace with an equivalent documented converter; test HTML edge cases. |
| Local cache directory naming by host/profile | New token/role model has no legacy host/profile key | Define a token- or explicit-cache-key naming scheme; otherwise multi-user cache collisions and stale indexes reappear. |
| `lib.defs` / `cds.lib` assumption that a library is already registered | A new upper service may be asked to make a library visible, not just create it | Decide whether registration is a supported business capability or an explicit prerequisite; do not silently edit files. |
| `.TopCat`/`.Cat` locking and format ownership | DD API abstracts locks/format and has no direct rename primitive | Continue using `ddCat*`; if direct file management is required, obtain a documented format/locking contract. |
| `hiGetCurrentWindow()`/global `cv` state | Persistent CIW state can be wrong after window churn; editor batch relies on bound `cv` | Prefer explicit window ids for multi-step operations; serialize Skill batches and verify current-state assumptions. |
| `execute_operations` retry behavior | Skill timeout can mean unknown effect | Do not auto-retry non-idempotent library/category/editor batches; inspect partial state before recovery. |

## 8. Test and example evidence to preserve

### 8.1 Library and category tests

| Evidence | Observable behavior to preserve |
|---|---|
| `test_virtuoso_client_attaches_library_ops` (`test_bak/test_library_management.py:43-46`) | `VirtuosoClient.local().library` is a `LibraryOps` facade. |
| `test_library_list_skill_uses_visible_library_database` (`:49-54`) | Library listing uses `ddGetLibList()`; must not call `ddUpdateLibList` or scan directories. |
| `test_library_get_skill_reads_path_and_technology_binding` (`:57-63`) | Library identity is `ddGetObj` + `~>readPath` + `techGetTechLibName`; missing object returns `libraryNotFound`. |
| `test_library_create_skill_requires_explicit_path_and_uses_supported_apis` (`:66-79`) | Create requires explicit path, uses `ddCreateLib`, `techBindTechFile`, read-back verification, and no `system()`/`renameFile()`. |
| `test_library_create_skill_without_technology_does_not_invent_binding` (`:82-86`) | No technology input means no `cdsDefTechLib` invention. |
| `test_library_delete_skill_uses_dd_delete_obj_without_force_fallback` (`:89-95`) | Delete uses `ddDeleteObj` and post-state verification; no `deleteDir`/`system` fallback. |
| `test_library_rename_skill_uses_ccp_rename_without_overwrite` (`:98-106`) | Rename uses `gdmCreateSpec` + `ccpRename(..., nil)` and verifies both source disappearance and destination existence. |
| `test_library_set_technology_uses_bind_for_new_and_set_for_existing` (`:109-115`) | Unbound technology uses bind; existing binding uses set; both read back. |
| `test_list_libraries_returns_names_and_forwards_timeout` (`:133-139`) | Structured list is parsed into names; caller timeout is forwarded unchanged. |
| `test_get_library_returns_structured_info` / `test_get_library_preserves_unbound_technology_as_none` (`:142-155`) | Exact `LibraryInfo` shape and `nil -> None`. |
| `test_create_library_returns_verified_info` (`:158-170`) | Successful create returns the verified object, not a boolean. |
| `test_create_library_reports_partial_technology_binding` (`:173-188`) | Partial create/bind failure includes the created library's verified state. |
| `test_delete_library_returns_none_on_verified_success` (`:191-194`) | Delete success is `None`, not a record. |
| `test_rename_library_returns_destination_info` (`:197-203`) | Rename returns destination name/path after verification. |
| `test_set_technology_library_returns_verified_name` (`:206-211`) | Technology setter returns the verified string. |
| Error/malformed/transport tests (`:214-241`) | Stable error codes map to explicit `RuntimeError` text; malformed structured output and transport errors are rejected. |
| Category builder tests (`test_bak/test_library_category.py:43-116`) | Stale category filtering, empty-category creation with `ddCatOpenEx(..., 1)`, membership filtering, no cell deletion, add/subitem/save/verify, copy-based rename, and refusal of subcategories. |
| Category return/error tests (`:119-227`) | Empty inputs reject; list/create/rename return names; delete/add/remove return `None`; partial context and transport errors are explicit. |

### 8.2 SKILL Finder / More Info tests

| Evidence | Observable behavior to preserve |
|---|---|
| CLI JSON/profile tests (`test_bak/test_skill_finder.py:56-95`) | `skill-find` and `skill-info` emit JSON when requested and pass profile through the legacy factory. |
| `test_find_skill_uses_local_discovery_when_tunnel_has_no_ssh_runner` (`:129-148`) | If a tunnel object has no SSH runner, discovery must be local and return the exact four-field entry. |
| `test_skill_more_info_uses_local_discovery...` (`:151-165`) | More Info returns a dict whose `plain_text` contains the section text. |
| Legacy section tests (`:212-261`) | Anchor-inside-heading and split heading text resolve the requested function and exclude the sibling function. |
| NULL-topic test (`:264-289`) | Precise section is preferred when locatable; whole file is fallback only as designed. |
| `test_extract_doc_section_modern_markers_first` (`:292-305`) | Modern topic markers win over legacy headings. |
| `test_extract_doc_section_whole_file_fallback` (`:321-329`) | Unknown topic returns `None` unless whole-file fallback is explicitly enabled. |

### 8.3 Documentation search tests

| Evidence | Observable behavior to preserve |
|---|---|
| Root resolution tests (`test_bak/test_docs_search.py:24-50`) | Explicit roots beat environment; direct doc-root env and install-root `/doc` are supported and de-duplicated. |
| `parse_tgf_line` test (`:53-69`) | `$docSet/path` resolves under the doc root; line number is retained. |
| Content/topic search test (`:72-96`) | Both `document` and `topic` result kinds can be produced for one query; snippets include matching body text. |
| Offline CLI test (`:99-114`) | `doc-search --doc-root ... --json` works without a Virtuoso connection; payload contains query, roots and result. |
| Remote index tests (`:252-283`) | Remote metadata index downloads exactly one `remote_records.jsonl.gz`, builds `index.sqlite`, and reuses it without re-downloading. |
| Index failure/fallback test (`:286-314`) | `vb_doc_index` failure falls back to `vb_doc_search` and candidate-file downloads, then remaps remote paths. |
| Local index test (`:317-339`) | A local index is built once and a second query does not rescan documentation files. |
| Ranking tests (`:363-470`) | Identifier-like titles rank above FAQ text for concept queries; stopwords and plural forms are handled; topic/document duplicates collapse to one location. |
| Remote shell tests (`:473-602`) | The embedded remote indexer emits deterministic document/topic records and skips a broken Cadence Python candidate. |

### 8.4 X11 tests

| Evidence | Observable behavior to preserve |
|---|---|
| `test_discover_windows_reports_child_modal_title` (`test_bak/test_x11_window_discovery.py:40-97`) | A WM frame with no title but a titled Virtuoso child yields child title/id, frame id, correct geometry, `known_modal` and Enter action; `find_dialogs` returns it as the only dialog. |
| `test_top_level_discovery_returns_one_verified_ciw_per_frame` (`:100-129`) | Three duplicate CIW children under one frame collapse to one record, preferring the CIW and preserving frame/dismiss ids. |
| `test_bootstrap_refuses_non_ciw...` (`:132-170`) | Non-CIW selection is refused; a CIW receives exactly `load("/shared/virtuoso_setup.il")`. |
| Multiple-display test (`:173-218`) | If an id matches the same CIW on two displays, the helper refuses before calling bootstrap. |
| Wrapper top-level test (`:221-228`) | `x11.list_windows(..., top_level=True)` emits `--list-windows --json --top-level`. |
| Environment/title tests (`:231-260`) | `ADE Assembler Message 1749` maps to `alt-o`; `pgrep` is called with the exact user, PID bytes decode, and `/proc/.../cmdline|environ` are read. |
| Wrapper command tests (`:284-300`) | Wrapper emits `--list-windows --json <display>` and `--dismiss-window <id> --action enter`; JSON lines parse into dicts. |
| Local-host test (`:303-315`) | `localhost` must not instantiate an SSH runner. |
| Path tests (`test_bak/test_x11_paths.py:20-45`) | Helper path is client/profile-scoped under the legacy bridge scratch root; `mkdir -p` and helper upload are observable. |
| Auto-display export test (`:343-374`) | The helper sets `DISPLAY` from the discovered environment before dismissal and emits JSON-line output. |

### 8.5 SKILL output/editor tests and examples

| Evidence | Observable behavior to preserve |
|---|---|
| `test_parse_skill_str_list_handles_escaped_string_values` (`test_bak/test_skill_output.py:14-15`) | Escaped quote/backslash sequences decode correctly. |
| Bare quoted list tests (`:18-20`) | Both one quoted token and a sequence of quoted tokens are accepted. |
| Tokenizer test (`:29-35`) | Nested groups and escaped strings remain one token; top-level tails are separate. |
| `test_parse_sexpr_decodes_common_skill_string_escapes` (`:38-42`) | `\t`, `\n`, escaped quote and backslash decode as expected. |
| `test_default_view_type_for_common_cellviews` (`test_bak/test_virtuoso_ops.py:10-18`) | Mapping includes layout prefix, schematic, symbol, maestro, and is case/whitespace tolerant. |
| Editor mode tests (`test_bak/test_editor_modes.py:24-46`) | `create()` uses `"w"`, `modify()` uses `"a"`, and deprecated `edit()` warns and defaults to `"a"` for all three editor families. |
| Library list example (`examples/01_virtuoso/basic/04_list_library_cells.py:24-54`) | Example deliberately uses raw SKILL and line-oriented parsing; useful as a migration contrast, not a canonical API. |
| Harvest example (`05_harvest_library.py:41-107`) | Cell/view classification, setup probing, `lib_root` fallback, and `"t" in output` result detection are observable business behavior. |
| Harvest IL (`assets/harvest_library.il:20-118`) | Prefix sets `maestro/adexl/normVim/topsim/spectre`, `^schematic`, `^config`, nil normalization, and path fallback chain are legacy semantics. |
| Screenshot example (`06_screenshot.py:45-83`) | Loads `takeScreenshot`, creates a remote directory through private SSH access, invokes `takeScreenshot("<remote_path>")`, and downloads the result. |
| Sanitization example (`07_sanitize_on_download.py:48-89`) | Sanitizer is policy-free, longest-key-first, writes both raw and `sanitized/<name>` sibling, and can opt out. |
| Library management example (`08_library_management.py:16-32`) | The intended façade use is `client.library.get(...)`, `list_categories(...)`, and `list_category_cells(...)`. |
| Diagnostics (`examples/01_virtuoso/diagnostics/sniff_cdslck.py:45-130`) | Lock discovery is read-only; it uses `find/cat/stat`, reports age, and never deletes. |

## 9. Open questions and ambiguities

1. **Screenshot ownership:** the normative route spec places GUI operations, including screenshots, on the `gui` role (`spec/design-concepts/中层/3-路由设计.md:40-45,69-75`), but legacy `VirtuosoClient.screenshot()` uses daemon-side SKILL `hiWindowSaveImage` (`basic/bridge.py:599-624`). Must the new upper package preserve semantic in-Virtuoso capture, or implement X11 pixel capture in `gui`? The two produce different content and have different path/topology requirements.
2. **GUI helper deployment:** the legacy wrapper uploads a Python helper to the remote scratch directory (`x11.py:80-97`). The new GUI interface is one-shot command only, and the File interface targets `file`, not necessarily `gui`. Is there an approved predeployed helper path, an allowed GUI-side upload mechanism, or must the command embed a self-contained script?
3. **`DISPLAY`/`XAUTHORITY` contract:** legacy can inherit `VB_DISPLAY`/`XAUTHORITY` or inspect `/proc`. New upper packages cannot read environment state as routing state. Should these be explicit business inputs, registration metadata, or GUI-role implementation-internal discovery? Multiple X11 displays currently make bootstrap ambiguous and are refused (`x11_dismiss_dialog.py:819-826`).
4. **Which window inventory is the public one?** `VirtuosoClient.list_windows()` returns SKILL window numbers/names; `x11.list_windows()` returns X11 ids/titles/geometry/classification. The `windows` and `list-windows` CLIs are different. A new API should name them distinctly and document which one is required for screenshots/dismissal/focus.
5. **Screenshot output transfer across roles:** if capture runs on `gui` but the generated PNG is on a different filesystem than `file`, the File interface cannot retrieve it. Is cross-role path visibility a caller responsibility, or should the GUI command stream/encode the image?
6. **`cds.lib`/`lib.defs` responsibility:** scoped library APIs never edit registration files. Is creating a library expected to make it visible in a new session, and if so who owns the `DEFINE`/`INCLUDE` mutation and restart semantics? The repository’s examples currently treat registration as a prerequisite (`digital_import/import_gds.py:101-109`).
7. **Category internals:** the API is intentionally flat and SKILL-only; rename copies members then removes the source (`category.py:196-308`). Is hierarchical category support needed later, and would it require a direct `.TopCat` format contract?
8. **Library attach/detach terminology:** no legacy API attaches or detaches a library object or technology binding. Should the new upper inventory expose only create/delete/rename/bind/change-technology, or does “attach/detach” mean something outside this legacy subsystem?
9. **Command shell semantics:** SKILL Finder discovery depends on a cshrc-sourced login environment and `which virtuoso`; docs discovery depends on remote `find`, `grep`, and a usable Python. The new `run_command` contract must state whether commands run in a login shell, what environment is inherited, and whether `parallel=True` is safe for these read-only probes.
10. **Remote index command cost:** `_remote_doc_index_command` has a hard-coded 900-second legacy timeout and may use a Cadence-bundled Python. The new middle interface has a default 30-second budget and no role-specific Python/bin parameter for `command`. Should the upper layer pass a longer explicit timeout, or should the middle expose a documented tool/root convention?
11. **Cache identity:** legacy docs/Skill Finder caches are keyed by remote host/profile and client id; the new architecture has token/role routing. A new token or explicit cache namespace must be defined to prevent stale or cross-user caches.
12. **Legacy result compatibility:** most scoped operations return `VirtuosoResult`, while new command/file/GUI operations return `CommandResult`. The upper package should decide whether to preserve legacy result fields (`status`, `errors`, `metadata`) or introduce typed domain results/dataclasses on top of the new middle contract.
13. **Failure retry discipline:** library/category rename and editor batches can have partial side effects. The new upper package must not auto-retry after timeout or unknown-effect; it should provide a read/verification path for recovery.
14. **Security of arbitrary paths and setup injection:** library create accepts a remote path; bootstrap accepts only an absolute generated setup file; file operations follow OS path semantics. The upper package must keep these distinctions explicit and avoid string concatenation across local/remote namespaces.

---

### Dense takeaway for the re-development team

The scoped legacy code is already close to a clean upper-layer split in two places: library/category management are pure “validate → build SKILL → parse structured list → verify,” and SKILL Finder/More Info/docs search are pure “discover → transfer → parse/index” concerns. The main migration work is not the algorithms; it is replacing `VirtuosoClient`/SSH/tunnel/private-runner plumbing with the five middle interfaces, defining cross-role file visibility for screenshots and helper assets, and preserving the X11 helper’s exact safety guards: mapped Virtuoso-class windows only, explicit CIW classification for bootstrap, one-shot key actions, no auto-dismiss of CIWs/main windows, and no retry after unknown-effect GUI actions.
