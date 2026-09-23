# 操作速查（照抄改参）

所有请求都要加 `"token":"<你的token>"`。列出的字段是**最小可用形态**，
更多可选字段看 `spec/design-concepts/上层/`。

## basic / demo / gui

| operation | 最小 payload（除 token） |
|---|---|
| basic.skill.execute | `{"skill_code":"1+1"}` |
| basic.command.run | `{"cmd":"ls"}` |
| basic.file.upload | `{"local_path":"C:/x.txt","remote_path":"/home/u/x.txt"}` |
| basic.file.download | `{"remote_path":"/home/u/x.txt","local_path":"C:/x.txt"}` |
| basic.gui.run | `{"cmd":"echo ok"}` |
| basic.spectre.run | `{"cmd":"spectre -W"}` |
| demo.paths.facts | `{}` |
| demo.pipeline.run | `{"local_path":"C:/in.txt","remote_path":"/home/u/in.txt"}` |
| demo.parallel.probe | `{}` |
| virtuoso.netlist.import | 参考桩，会失败，不建视图 |
| virtuoso.gui.list_windows | `{}` |
| virtuoso.gui.send_key | `{"window_id":"0x...","key":"enter"}` |
| virtuoso.gui.auto_dismiss | `{}` |
| virtuoso.gui.screenshot | `{"target":"display","output_path":"C:/s.ppm"}` |

## cellview

| operation | 最小 payload |
|---|---|
| lib.list | `{}` |
| lib.get | `{"library":"L"}` |
| lib.create | `{"library":"L","path":"/home/u/.virtuoso-bridge/vblog/L"}` |
| lib.copy | `{"library":"L","new_library":"L2","new_path":"/.../L2"}` |
| lib.delete | `{"library":"L"}` |
| lib.rename | `{"library":"L","new_name":"L2"}` |
| lib.bind | `{"library":"L","technology_library":"cdsDefTechLib"}` |
| cell.list | `{"library":"L"}`（可选 `category`） |
| cell.copy | `{"library":"L","cell":"C","new_library":"L","new_cell":"C2"}` |
| cell.delete | `{"library":"L","cell":"C"}` |
| cell.rename | `{"library":"L","cell":"C","new_name":"C2"}` |
| view.list | `{"library":"L","cell":"C"}` |
| view.create | `{"library":"L","cell":"C","view":"schematic","view_type":"schematic"}` |
| view.copy | `{"library":"L","cell":"C","view":"schematic","new_library":"L","new_cell":"C2","new_view":"schematic"}` |
| view.delete | `{"library":"L","cell":"C","view":"schematic"}` |
| view.rename | `{"library":"L","cell":"C","view":"schematic","new_name":"symbol"}` |
| cat.list | `{"library":"L"}` |
| cat.create | `{"library":"L","category":"cat1"}` |
| cat.delete | `{"library":"L","category":"cat1"}` |
| cat.rename | `{"library":"L","category":"cat1","new_name":"cat2"}` |
| cat.add_cell | `{"library":"L","category":"cat1","cell":"C"}` |
| cat.remove_cell | `{"library":"L","category":"cat1","cell":"C"}` |

## schematic / symbol / layout

| operation | 最小 payload |
|---|---|
| schematic.read | `{"library":"L","cell":"C","view":"schematic"}` |
| schematic.write | `{"library":"L","cell":"C","view":"schematic","commands":[...]}` |
| schematic.check_and_save | `{"library":"L","cell":"C","view":"schematic"}` |
| schematic.screenshot | `{"library":"L","cell":"C","view":"schematic"}` |
| symbol.read | `{"library":"L","cell":"C","view":"symbol"}` |
| symbol.write | `{"library":"L","cell":"C","view":"symbol","commands":[...]}` |
| symbol.generate | `{"library":"L","cell":"C","view":"schematic"}` |
| symbol.check_and_save | `{"library":"L","cell":"C","view":"symbol"}` |
| symbol.screenshot | `{"library":"L","cell":"C","view":"symbol"}` |
| layout.read | `{"library":"L","cell":"C","view":"layout"}` |
| layout.write | `{"library":"L","cell":"C","view":"layout","commands":[...]}` |
| layout.gds | `{"action":"export|import","library":"L","cell":"C","view":"layout","file_path":"..."}` |
| layout.display | `{"library":"L","cell":"C","view":"layout","commands":[{"op":"set_layers_visible","layers":[["M1","drawing"]],"visible":true}]}` |
| layout.screenshot | `{"library":"L","cell":"C","view":"layout"}` |

写操作原子（`commands[]` 里）：

- schematic：`place_instance / delete_instance / rename_instance / set_instance_params / set_term_nets / place_wire / delete_wire / set_wire_properties / place_label / delete_label / rename_label / set_label_properties / place_pin / delete_pin / rename_pin / set_pin_properties / place_note / delete_note / rename_note / set_note_properties`
- layout：`place_rect / place_polygon / place_path / place_line / place_label / delete_shape / set_shape_properties / rename_label / place_instance / place_mosaic / rename_instance / set_instance_properties / place_via / delete_via`
- symbol：`place_line / place_rect / place_polygon / place_ellipse / delete_shape / set_shape_properties / place_label / delete_label / rename_label / set_label_properties / place_pin / delete_pin / rename_pin / set_pin_properties`

## maestro

| operation | 最小 payload |
|---|---|
| read_config | `{"library":"L","cell":"C","view":"maestro"}` |
| write | `{"library":"L","cell":"C","view":"maestro","commands":[...]}` |
| read_results | `{"library":"L","cell":"C","view":"maestro"}`（可加 `history`） |
| export | `{"library":"L","cell":"C","view":"maestro","kind":"netlist|script|outputs_csv|snapshot|screenshot"}` |
| read_history | `{"library":"L","cell":"C","view":"maestro"}` |
| write_history | `{"library":"L","cell":"C","view":"maestro","commands":[{"op":"rename|lock|unlock|delete|delete_results","history":"h1"}]}` |
| open_gui / close_gui | `{"library":"L","cell":"C","view":"maestro"}` |
| run | `{"library":"L","cell":"C","view":"maestro","blocking":false}` |
| open_waveform_gui | `{"library":"L","cell":"C","view":"maestro","history":"h1","signals":["VOUT"]}` |
| close_waveform_gui | `{"session":"s1"}` |

write 原子：`set_var / delete_var / set_parameter / delete_parameter / set_test / delete_test /
set_analysis / delete_analysis / add_output / delete_output / set_spec / delete_spec /
set_corner / delete_corner / put_model / set_model_file / set_model_section / load_corners /
set_run_mode / set_job_control_mode / set_job_policy / set_simulator_mode`。

## verilog / veriloga

| operation | 最小 payload |
|---|---|
| verilog.read | `{"library":"L","cell":"C","view":"verilog"}` 或 `{"file_path":"C:/x.v"}` |
| verilog.write | `{"library":"L","cell":"C","view":"verilog","commands":[{"op":"set_source","text":"..."}]}` |
| verilog.import | `{"library":"L","cell":"C","file_path":"C:/x.v","file_is_local":true}` |
| verilog.export | `{"library":"L","cell":"C","view":"schematic","output_path":"C:/x.v"}` |
| veriloga.read | `{"library":"L","cell":"C","view":"veriloga"}` 或 `{"file_path":"C:/x.va"}` |
| veriloga.write | `{"library":"L","cell":"C","view":"veriloga","commands":[...]}` |
| veriloga.check_and_save | `{"library":"L","cell":"C","view":"veriloga"}` |

verilog/veriloga write 原子：`ensure_view / delete_view / set_source / patch_source`。

## calibre / spectre

| operation | 最小 payload |
|---|---|
| calibre.check_env | `{"deck":"/pdks/calibre.drc"}` |
| calibre.drc | `{"gds":"/data/x.gds","top":"x","deck":"/pdks/calibre.drc","blocking":false}` |
| calibre.lvs | 同上 + `{"cdl":"/data/x.cdl"}` |
| calibre.pex | 同上 + `{"cdl":"...","lvs_run_dir":"...","fmt":"spice"}` |
| calibre.status | `{"job_id":"drc_x","kind":"drc"}` |
| calibre.read_results | `{"job_id":"drc_x","kind":"drc"}` |
| calibre.export | `{"job_id":"drc_x","kind":"drc","items":["summary"],"local_dir":"C:/out"}` |
| spectre.check_license | `{}` |
| spectre.run | `{"tasks":[{"job":"x","netlist":"C:/x.scs","parse":"auto"}]}` |
| spectre.read_results | `{"source":"/data/x/tb.raw","analysis":"all"}` |
| spectre.measure | `{"data":{...},"metrics":[{"type":"max","signal":"vout"}]}` |
| spectre.export | `{"format":"csv|json","output_path":"C:/x.csv","data":{...}}` |

## skillref

| operation | 最小 payload |
|---|---|
| skillref.search | `{"query":"hiWindowSaveImage"}` |
| skillref.info | `{"name":"hiWindowSaveImage"}` |
