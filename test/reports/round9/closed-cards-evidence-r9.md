# 已关闭卡片：依据在本轮是否仍成立（机器结论）

- 卡片 83 张；状态分布 {'EVIDENCE-NOT-RERUN-TONIGHT': 35, 'NO-PATH-IN-EVIDENCE': 28, 'R9-OFFLINE-GREEN': 17, 'R9-IN-TONIGHT-LOGS': 1, 'PATH-NOT-FOUND': 2}

| ID | 事项 | 状态 | 引用路径 |
|---|---|---|---|
| P-105 | `symbol/layout.screenshot` 的 `view_type` | EVIDENCE-NOT-RERUN-TONIGHT | test/artifacts/evidence/verify-fix-r9/shot-layout-p105.txt; test/artifacts/evidence/verify-fix-r9/shot-symbol-p105b.txt |
| P-070 | 蒙特卡洛能力缺失：只能读回 MC 结果，不能驱动 MC 仿真 | EVIDENCE-NOT-RERUN-TONIGHT | test/artifacts/evidence/verify-fix-r9/maestro-mc-p070-5.json; test/live/packages/maestro_mc_e2e_tests.py |
| P-092 | `calibre.drc/lvs/pex` 的 `power`/`ground` | NO-PATH-IN-EVIDENCE | — |
| P-093 | `calibre.drc(hier=False)` 拼非法 `-turbo` → | R9-OFFLINE-GREEN | test/artifacts/evidence/p093-p094-quickfail-green.json; test/offline/unit/test_calibre_argv_contracts.py |
| P-094 | calibre 工具秒退不报失败（`status` 只有 `unknown`，` | R9-OFFLINE-GREEN | test/offline/unit/test_calibre_job_state.py |
| P-098 | `blocking=true` 超时后对外 `status` 不是 `timeo | EVIDENCE-NOT-RERUN-TONIGHT | test/artifacts/evidence/p098-timeout-green.json |
| C4 | `CommandResult` NamedTuple 被序列化成位置数组，命令/ | NO-PATH-IN-EVIDENCE | — |
| C3 | C1 落地后测试侧消费方未适配：仍按旧 `data` 壳解析响应 | EVIDENCE-NOT-RERUN-TONIGHT | test/artifacts/evidence/verify-fix-r9/offline-after-c3-3.txt |
| C1 | `basic.skill.execute` 响应 JSON 冗余（同一结果两处序 | NO-PATH-IN-EVIDENCE | — |
| C2 | 所有 Skill 调用缺少 `log_level` / `log_max_byt | R9-OFFLINE-GREEN | test/live/packages/skill_log_options_e2e_tests.py; test/offline/unit/test_skill_log_options.py |
| P-095 | `maestro.run` 的 Overwrite History 目标悬空 → | EVIDENCE-NOT-RERUN-TONIGHT | test/semi/probes/maestro_p095_overwrite_wedge_probe.py |
| P-102 | `calibre.pex` 第三阶段 argv 非法（`-xrc -fmt sp | EVIDENCE-NOT-RERUN-TONIGHT | test/live/packages/calibre_export_pex_e2e_tests.py |
| P-103 | `calibre.pex` 报 `completed` 但 stage3 失败（ | EVIDENCE-NOT-RERUN-TONIGHT | test/live/packages/calibre_export_pex_e2e_tests.py |
| P-097 | `verilog.import` 覆盖写后 `_read_views` 瞬时 c | EVIDENCE-NOT-RERUN-TONIGHT | test/artifacts/evidence/verify-fix-r9/gate-verilog-rerun2.txt |
| P-091 | 截图远端暂存口径三包不一致（schematic 保留 / symbol·layo | NO-PATH-IN-EVIDENCE | — |
| P-080 | `view_type` 在 read 路径不校验（空串/整数/bogus 静默接 | R9-OFFLINE-GREEN | test/offline/unit/test_view_type_param_contract.py; test/live/packages/veriloga_e2e_tests.py |
| P-081 | Windows 客户端把远端 POSIX 路径改写成 `\` 形式 | R9-OFFLINE-GREEN | test/offline/unit/test_remote_posix_path_contract.py |
| P-082 | region 四元组与两点口径冲突（read/depth/screenshot  | R9-IN-TONIGHT-LOGS | test/live/packages/layout_e2e_tests.py |
| P-083 | `spectre.export.precision` 语义未定义（有效数字 vs | EVIDENCE-NOT-RERUN-TONIGHT | test/live/packages/spectre_params_e2e_tests.py |
| P-090 | 上传 stage 在安装前消失（安装非幂等 → sha256 mismatch  | EVIDENCE-NOT-RERUN-TONIGHT | test/semi/transport/install_stage_idempotent_tb.py |
| P-078 | `place_wire` 样式参数拼接重复：width 静默建 path / c | NO-PATH-IN-EVIDENCE | — |
| P-079 | local 模式显式 daemon_port≠local_port 被静默归一化 | R9-OFFLINE-GREEN | test/offline/unit/test_norm_gap_round8.py |
| P-084 | `maestro.export.include_results` 死参数（声明但 | NO-PATH-IN-EVIDENCE | — |
| P-085 | `layout.read(depth>0)` + region 不可用（deep | R9-OFFLINE-GREEN | test/offline/unit/test_layout_depth_contract.py |
| P-087 | `maestro.write(save=False)` 的改动被后续无关 sav | NO-PATH-IN-EVIDENCE | — |
| P-088 | `maestro.write(delete_var, scope=all)` 确 | NO-PATH-IN-EVIDENCE | — |
| P-089 | `maestro.open_waveform_gui.result` 死参数（忽 | NO-PATH-IN-EVIDENCE | — |
| P-096 | 陈旧 OA 写锁 → `axlOpenInRead0` 模态挂死 CIW | NO-PATH-IN-EVIDENCE | — |
| P-099 | `verilog.import` 返回值 `views` 恒空（与真机视图不一致 | EVIDENCE-NOT-RERUN-TONIGHT | test/live/packages/verilog_import_params_e2e_tests.py |
| P-100 | `verilog.import` 的 `cell` 参数不被落地（改名无效果/事 | NO-PATH-IN-EVIDENCE | — |
| P-101 | `import(overwrite=False)` 命中已存在 cell：静默  | NO-PATH-IN-EVIDENCE | — |
| P-104 | 读路径 `maeOpenSetup` 默认 `mode="a"` 凭空建 vie | EVIDENCE-NOT-RERUN-TONIGHT | test/live/packages/maestro_view_param_e2e_tests.py |
| P-043 | py2.7 daemon 缺 coding cookie | EVIDENCE-NOT-RERUN-TONIGHT | test/artifacts/evidence/py27-daemon-probe-green.json |
| P-044 | layout 写锁误判 + 句柄不关 | NO-PATH-IN-EVIDENCE | — |
| P-045 | 「并发压测打挂 CIW」 | NO-PATH-IN-EVIDENCE | — |
| P-047 | `verilog.import` 依赖 cwd 的 `cds.lib` | EVIDENCE-NOT-RERUN-TONIGHT | test/artifacts/evidence/round5-main/run-all-http-results.json |
| P-050 | daemon 模块在伪 stdin 下不可导入 | NO-PATH-IN-EVIDENCE | — |
| P-051 | `layout.gds` 远端发布不建目录 | NO-PATH-IN-EVIDENCE | — |
| P-058 | 4 条 Windows-only 用例缺 Linux 守卫 | NO-PATH-IN-EVIDENCE | — |
| P-063 | 注册类离线用例受机器端口区间影响 | EVIDENCE-NOT-RERUN-TONIGHT | test/artifacts/evidence/round5-main/p063-d4-fullunit-pressure.xml |
| P-064 | 并发 pytest 会话互删临时目录 | PATH-NOT-FOUND | — |
| P-065 | `subprocess.Popen` 全局打桩跨用例串扰 | R9-OFFLINE-GREEN | test/offline/unit/test_ssh_edges.py |
| P-057 | 深嵌套 JSON 行为随解释器变化 | NO-PATH-IN-EVIDENCE | — |
| P-068 | 共享 PDK 库里第二个真实 OS 用户画不了版图 | EVIDENCE-NOT-RERUN-TONIGHT | test/artifacts/evidence/round6-fixcheck/s16-handoff-reverify2.json |
| P-052 | `set_instance_params` 污染共享库 cell CDF | EVIDENCE-NOT-RERUN-TONIGHT | test/artifacts/evidence/round4-probes/round4-shared-cdf-pollution.json |
| P-053 | Spectre AC 结果链路两处断 | EVIDENCE-NOT-RERUN-TONIGHT | test/artifacts/evidence/round4-probes/round4-spectre-ac-pipeline.json |
| P-054 | 层次化 `symbol.generate` 残留子单元视图 | EVIDENCE-NOT-RERUN-TONIGHT | test/artifacts/evidence/round4-probes/round4-symbol-hierarchy-handle.json; test/reports/round6-修复验证报告.md; test/live/pack |
| P-055 | 业务面 404 而非 405 + Allow | EVIDENCE-NOT-RERUN-TONIGHT | test/artifacts/evidence/round6-verify/offline-mine.xml |
| P-056 | POSIX 强杀进程组失效 | EVIDENCE-NOT-RERUN-TONIGHT | test/artifacts/evidence/round5-linux-client/py314.log; test/artifacts/evidence/round5-linux-client/py39.log |
| P-059 | `read_results` 解不了 Calibre 2025 `DRC.rep | EVIDENCE-NOT-RERUN-TONIGHT | test/artifacts/evidence/round5-main/calibre-drc.json |
| P-061 | calibre 阻塞轮询不快失败 | EVIDENCE-NOT-RERUN-TONIGHT | test/artifacts/env/s11/s11-lvs.json |
| P-062 | LVS 结论截成半个词 + counts 恒空 | EVIDENCE-NOT-RERUN-TONIGHT | test/artifacts/evidence/round5-main/calibre-lvs.json |
| P-066 | `skill_value()` 抛内部 `AttributeError` | EVIDENCE-NOT-RERUN-TONIGHT | test/artifacts/evidence/round6-verify/offline-mine.xml |
| P-067 | 未加引号 `Parameters:` 静默丢参数 | NO-PATH-IN-EVIDENCE | — |
| P-071 | LVS 结论归一化两条路径不一致（P-062 残留） | R9-OFFLINE-GREEN | test/artifacts/evidence/round6-verify/calibre-drc-final2.json; test/offline/unit/test_calibre_verdict_consistency.py |
| P-048 | 「业务面不热重载 registry」 | NO-PATH-IN-EVIDENCE | — |
| P-060 | calibre 包缺常驻真机入口（覆盖缺口） | EVIDENCE-NOT-RERUN-TONIGHT | test/artifacts/evidence/round6b-verify/run-all-http-final.log; test/shared/runners/run_all_http.py; test/live/packages/c |
| P-072 | `init_work_dir` 一次性化 + 删除测试钩子 → 518 条离线用 | R9-OFFLINE-GREEN | test/artifacts/env/env-e1/registry.json; test/artifacts/evidence/round6b-verify/offline-sharedroot4.xml; test/conftest.p |
| P-049 | 缺样本 trace 的 NaN 被放行到对外出参（spec :307 与 :30 | R9-OFFLINE-GREEN | test/offline/unit/test_output_json_safety.py |
| P-013 | 客户端文件泄露（`err_dir` 兜底 / 隧道 stderr 日志成功路径不 | NO-PATH-IN-EVIDENCE | — |
| P-019 | 孤立代理项（`"\ud800"`）请求 → HTTP 面断连而非 4xx | NO-PATH-IN-EVIDENCE | — |
| P-020 | `spectre.measure` 零幅度 AC 点输出 `-Infinity` | R9-OFFLINE-GREEN | test/offline/unit/test_spectre_metrics.py |
| P-025 | Windows 多进程共享 work-dir 时 `log/commands.l | PATH-NOT-FOUND | — |
| P-034 | `calibre.pex` 第三阶段 argv 错误且失败被静默（`-xrc - | NO-PATH-IN-EVIDENCE | — |
| P-037 | paramiko 后端把 `ssh -G` 的 `true/false` 当非法 | NO-PATH-IN-EVIDENCE | — |
| P-039 | py2.7 daemon 对 `_read_frame` ValueError  | EVIDENCE-NOT-RERUN-TONIGHT | test/artifacts/evidence/round2-py27-handler-real.json |
| P-041 | `verilog._read_views` 守卫长度与取值下标不匹配（`>=3` | R9-OFFLINE-GREEN | test/offline/unit/test_verilog_contracts.py |
| P-042 | `layout.gds` 遇版图锁时误报 "layout view not fo | NO-PATH-IN-EVIDENCE | — |
| P-046 | S10 e2e 引导源未固定 → `RBStop()+load()` 会覆盖别人 | EVIDENCE-NOT-RERUN-TONIGHT | test/live/e2e/test_e2e_live.py |
| P-069 | Calibre LVS 全链跑不通：auCdl 对含 PDK 器件的 cell  | EVIDENCE-NOT-RERUN-TONIGHT | test/artifacts/evidence/round7/design-iterate/iterate-lvs.json |
| P-026 | maestro 会话匹配用子串（view=maestro 误命中库名 maest | EVIDENCE-NOT-RERUN-TONIGHT | test/artifacts/evidence/round7/live-run-all-http.log |
| P-027 | `virtuoso.netlist.import` 假成功（对不存在的库也返回  | EVIDENCE-NOT-RERUN-TONIGHT | test/artifacts/tmp/upd-red-202ef8ab/src/pyapi/packages/netlist_import.py; test/shared/runners/ops_matrix.py |
| P-029 | `layout.gds` 导出忽略 `file_is_local=False`（ | R9-OFFLINE-GREEN | test/offline/unit/test_layout_contracts.py; test/offline/unit/test_layout_publish_contracts.py |
| P-030 | `set_term_nets` 默认 `stub_length=0.5` 对 6 | R9-OFFLINE-GREEN | test/offline/unit/test_schematic_contracts.py |
| P-031 | schematic `check_and_save`/`write` 忽略 `s | R9-OFFLINE-GREEN | test/offline/unit/test_schematic_contracts.py |
| P-032 | `verilog._imported_cells` 去重顺序错误（未清洗 tok | R9-OFFLINE-GREEN | test/offline/unit/test_verilog_contracts.py |
| P-074 | pin 坐标口径三处不一致（read `xy` / write `x`,`y`  | EVIDENCE-NOT-RERUN-TONIGHT | test/artifacts/evidence/round7/pin-ops.json |
| C0 | 测试规范缺失（六步/状态还原）＋ 原子级覆盖系统性缺口 | EVIDENCE-NOT-RERUN-TONIGHT | test/artifacts/evidence/atom-coverage-2026-09-28.json; test/shared/runners/audit_atom_coverage.py; test/docs/写TB规范.md; t |
| P-038 | py3.9 裸装缺 `eval-type-backport` 声明 | NO-PATH-IN-EVIDENCE | — |
| P-073 | pin 原子操作与「pin 有效名」不一致（rename 静默无效 / set  | NO-PATH-IN-EVIDENCE | — |
| P-075 | `layout.gds` 导出后残留模态框 → 同会话 SKILL 挂死（P1） | EVIDENCE-NOT-RERUN-TONIGHT | test/artifacts/evidence/round7/adc-sar.json |
| P-077 | 注册探测拒绝裸 python 名（`test -x python3`） | NO-PATH-IN-EVIDENCE | — |
| P-076 | `spectre.run` 间歇永不返回（in_flight 不释放，需重启业务 | EVIDENCE-NOT-RERUN-TONIGHT | test/semi/probes/p076_fix_verify_probe.py; test/artifacts/tmp/repro_p076_rounds.py; test/shared/runners/run_all_http.py |
