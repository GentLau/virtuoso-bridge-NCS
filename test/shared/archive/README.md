# `test/shared/archive/` —— 历史脚本（非准出）

历史脚本，保留用于调查、复现和迁移参考。它们可能仍引用旧 schema、旧端口、
旧靶机目录或已废弃的接口，**不进入准出集合**。

若某个 legacy 脚本重新纳入准出，必须先：

1. 按当前 spec 重写接口与路由假设；
2. 把远端 scratch 改到注册表 root 或显式 `--root`；
3. 在 `test/shared/runners/run_coverage.ps1` 或新的准出 runner 中登记；
4. 重新生成红/绿证据并更新测试报告。
