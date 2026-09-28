#!/usr/bin/env python3
"""把真机实例的 run 目录补成"启动即完整"的用户环境（在被测主机上执行，如 wsl-gent）。

背景：run 目录只有 `.cdsinit` 是不够的 —— 真实用户的启动目录一定有 `cds.lib`，
里面定义了他能用的全部库（含 PDK）。少了它，`verilog.import` 这类依赖
`<cwd>/cds.lib` 的流程会因为"找不到库映射"而失败，看起来像产品缺陷。

做法：为每个实例生成**真实文件** `cds.lib` =
    场景 cds.lib（优先，含该场景自己的库）
  + 参考环境 `/home/Gent/project/test/cds.lib` 里尚未定义的库（含 TEST_* 标准库）
  − 厂商库重复项（analogLib/basic 等由 SOFTINCLUDE 的 Cadence setup 提供，重复 DEFINE 会报 OAVLG-10024）
同时把 `INCLUDE`/`SOFTINCLUDE` 按目标文件去重（同一个 setup 被两种写法各引一次也会报错）。
已存在的 `cds.lib`（含软链）先备份为 `cds.lib.backup-<时间戳>`。

用法（在 wsl-gent 上）::

    python3 make_run_env_complete.py            # 处理脚本内 TARGETS 列出的实例

自检（任一 CIW）::

    ddGetObj("schemtest") ddGetObj("maestro_tb") ddGetObj("tsmcN65") ddGetObj("TEST_BRIDGE")
    # 全部回 dd:0x… 才算"启动即完整"
"""
import pathlib
import time

REF = pathlib.Path("/home/Gent/project/test/cds.lib")
TARGETS = {
    "vblog": pathlib.Path("/home/Gent/project/vblog/cds.lib"),
    "vbs11": pathlib.Path("/home/Gent/project/vbs11/cds.lib"),
    "vbmu2": pathlib.Path("/home/Gent/project/vbmu2/cds.lib"),
    "vbmu3": pathlib.Path("/home/Gent/project/vbmu3/cds.lib"),
}
DIRECTIVES = ("DEFINE", "SOFTINCLUDE", "INCLUDE", "UNDEFINE", "ASSIGN")
#: Cadence 自带 setup（SOFTINCLUDE cdsDotLibs/...）已提供的厂商库，重复 DEFINE 会让
#: OpenAccess 在 batch 里报 OAVLG-10024，因此参考环境里的同名条目要跳过。
VENDOR_LIB_PATHS = ("/tools.lnx86/dfII/etc/cdslib/", "/tools/dfII/etc/cdslib/")


def entries(path):
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(("#", ";")) and stripped.split()[0] in DIRECTIVES:
            out.append(stripped)
    return out


def lib_name(entry):
    parts = entry.split()
    if parts[0] == "DEFINE" and len(parts) >= 3:
        return parts[1]
    return None


def include_key(entry):
    parts = entry.split()
    if parts[0] in ("INCLUDE", "SOFTINCLUDE") and len(parts) >= 2:
        return f"{parts[0]}:{parts[1]}"
    return None


def is_vendor_define(entry):
    return entry.startswith("DEFINE ") and any(p in entry for p in VENDOR_LIB_PATHS)


def main():
    stamp = time.strftime("%Y%m%d-%H%M%S")
    ref = entries(REF)
    for name, scenario in TARGETS.items():
        run = pathlib.Path(f"/home/Gent/.virtuoso-bridge/{name}/run")
        if not run.is_dir():
            print(f"{name}: run 目录不存在，跳过")
            continue
        current = run / "cds.lib"
        if current.is_symlink():
            (run / f"cds.lib.backup-{stamp}").write_text(
                f"symlink -> {current.resolve()}\n", encoding="utf-8")
            current.unlink()
        elif current.exists():
            current.rename(run / f"cds.lib.backup-{stamp}")
        scen = entries(scenario)
        have = {lib_name(e) for e in scen if lib_name(e)}
        have_includes = {include_key(e) for e in scen if include_key(e)}
        merged = list(scen)
        for entry in ref:
            lname = lib_name(entry)
            ikey = include_key(entry)
            if is_vendor_define(entry):
                continue
            if lname is not None:
                if lname in have:
                    continue
                have.add(lname)
            elif ikey is not None:
                target = ikey.split(":", 1)[1]
                if ikey in have_includes or any(
                        (include_key(e) or "").endswith(target) for e in merged):
                    continue
                have_includes.add(ikey)
            merged.append(entry)
        header = (f"# 由 make_run_env_complete.py 生成（{stamp}）：\n"
                  f"# 场景库来自 {scenario}\n# 参考环境来自 {REF}\n")
        (run / "cds.lib").write_text(header + "\n".join(merged) + "\n", encoding="utf-8")
        defines = [lib_name(e) for e in merged if lib_name(e)]
        print(f"{name}: cds.lib 写好，DEFINE={len(defines)} 个：{', '.join(defines[:8])}"
              + (" ..." if len(defines) > 8 else ""))


if __name__ == "__main__":
    main()
