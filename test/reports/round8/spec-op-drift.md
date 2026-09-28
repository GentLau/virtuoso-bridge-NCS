# spec 操作 ↔ 实现 OPERATIONS 漂移核对

- 实现 OPERATIONS：79 个；spec 提到的操作标识：44 个
- **SPEC-ONLY（spec 有、实现无）**：18
- IMPL-ONLY（实现有、spec 未提）：53

## SPEC-ONLY（需判定：文档滞后 or 实现缺功能）

- `cdslog.log_level` — 中层/add-中层配置文档.md:38
- `cdslog.log_max_bytes` — 中层/add-中层配置文档.md:39
- `gui.display` — 上层/10-gui.md:17, 上层/10-gui.md:18
- `master.tag` — 上层/11-veriloga.md:73, 上层/8-verilog.md:69
- `netlist.oa` — 上层/8-verilog.md:27
- `psf.py` — 上层/7-spectre.md:326
- `role.daemon.expected_hostname` — 中层/add-中层配置文档.md:63
- `role.daemon.expected_user` — 中层/add-中层配置文档.md:64
- `role.daemon.python` — 其他/1-多用户与注册.md:71
- `role.gui.display` — 中层/add-中层配置文档.md:66
- `root.default` — 中层/add-中层配置文档.md:76, 其他/1-多用户与注册.md:93, 其他/1-多用户与注册.md:93
- `runtime.channel_budget` — 中层/2-并发设计.md:27, 中层/add-中层配置文档.md:36
- `runtime.connect_timeout` — 中层/add-中层配置文档.md:37
- `si.env` — 上层/12-calibre.md:34
- `text.v` — 上层/8-verilog.md:26, 上层/8-verilog.md:69
- `text.veriloga` — 上层/8-verilog.md:26
- `verilog.v` — 上层/8-verilog.md:26, 上层/8-verilog.md:27
- `virtuoso.cellview.cell.create` — 上层/5-cellview.md:52

## IMPL-ONLY（未文档化操作）

- `basic.command.run` — src/pyapi/packages/basic.py::run_command
- `basic.file.download` — src/pyapi/packages/basic.py::download_file
- `basic.file.upload` — src/pyapi/packages/basic.py::upload_file
- `basic.gui.run` — src/pyapi/packages/basic.py::run_gui_command
- `basic.skill.execute` — src/pyapi/packages/basic.py::execute_skill
- `virtuoso.cellview.cat.add_cell` — src/pyapi/packages/cellview.py::cat_add_cell
- `virtuoso.cellview.cat.create` — src/pyapi/packages/cellview.py::cat_create
- `virtuoso.cellview.cat.delete` — src/pyapi/packages/cellview.py::cat_delete
- `virtuoso.cellview.cat.list` — src/pyapi/packages/cellview.py::cat_list
- `virtuoso.cellview.cat.remove_cell` — src/pyapi/packages/cellview.py::cat_remove_cell
- `virtuoso.cellview.cat.rename` — src/pyapi/packages/cellview.py::cat_rename
- `virtuoso.cellview.cell.copy` — src/pyapi/packages/cellview.py::cell_copy
- `virtuoso.cellview.cell.delete` — src/pyapi/packages/cellview.py::cell_delete
- `virtuoso.cellview.cell.list` — src/pyapi/packages/cellview.py::cell_list
- `virtuoso.cellview.cell.rename` — src/pyapi/packages/cellview.py::cell_rename
- `virtuoso.cellview.lib.bind` — src/pyapi/packages/cellview.py::lib_bind
- `virtuoso.cellview.lib.copy` — src/pyapi/packages/cellview.py::lib_copy
- `virtuoso.cellview.lib.create` — src/pyapi/packages/cellview.py::lib_create
- `virtuoso.cellview.lib.delete` — src/pyapi/packages/cellview.py::lib_delete
- `virtuoso.cellview.lib.get` — src/pyapi/packages/cellview.py::lib_get
- `virtuoso.cellview.lib.rename` — src/pyapi/packages/cellview.py::lib_rename
- `virtuoso.cellview.view.copy` — src/pyapi/packages/cellview.py::view_copy
- `virtuoso.cellview.view.create` — src/pyapi/packages/cellview.py::view_create
- `virtuoso.cellview.view.delete` — src/pyapi/packages/cellview.py::view_delete
- `virtuoso.cellview.view.list` — src/pyapi/packages/cellview.py::view_list
- `virtuoso.gui.auto_dismiss` — src/pyapi/packages/gui.py::auto_dismiss
- `virtuoso.gui.list_windows` — src/pyapi/packages/gui.py::list_windows
- `virtuoso.gui.screenshot` — src/pyapi/packages/gui.py::screenshot
- `virtuoso.gui.send_key` — src/pyapi/packages/gui.py::send_key
- `virtuoso.layout.display` — src/pyapi/packages/layout.py::display
- `virtuoso.layout.gds` — src/pyapi/packages/layout.py::gds
- `virtuoso.layout.read` — src/pyapi/packages/layout.py::read
- `virtuoso.layout.screenshot` — src/pyapi/packages/layout.py::screenshot
- `virtuoso.layout.write` — src/pyapi/packages/layout.py::write
- `virtuoso.maestro.close_gui` — src/pyapi/packages/maestro.py::close_gui
- `virtuoso.maestro.close_waveform_gui` — src/pyapi/packages/maestro.py::close_waveform_gui
- `virtuoso.maestro.export` — src/pyapi/packages/maestro.py::export
- `virtuoso.maestro.open_gui` — src/pyapi/packages/maestro.py::open_gui
- `virtuoso.maestro.open_waveform_gui` — src/pyapi/packages/maestro.py::open_waveform_gui
- `virtuoso.maestro.read_config` — src/pyapi/packages/maestro.py::read_config
- `virtuoso.maestro.read_history` — src/pyapi/packages/maestro.py::read_history
- `virtuoso.maestro.read_results` — src/pyapi/packages/maestro.py::read_results
- `virtuoso.maestro.run` — src/pyapi/packages/maestro.py::run
- `virtuoso.maestro.write` — src/pyapi/packages/maestro.py::write
- `virtuoso.maestro.write_history` — src/pyapi/packages/maestro.py::write_history
- `virtuoso.schematic.check_and_save` — src/pyapi/packages/schematic.py::check_and_save
- `virtuoso.schematic.screenshot` — src/pyapi/packages/schematic.py::screenshot
- `virtuoso.schematic.write` — src/pyapi/packages/schematic.py::write
- `virtuoso.symbol.check_and_save` — src/pyapi/packages/symbol.py::check_and_save
- `virtuoso.symbol.generate` — src/pyapi/packages/symbol.py::generate
- `virtuoso.symbol.read` — src/pyapi/packages/symbol.py::read
- `virtuoso.symbol.screenshot` — src/pyapi/packages/symbol.py::screenshot
- `virtuoso.symbol.write` — src/pyapi/packages/symbol.py::write

