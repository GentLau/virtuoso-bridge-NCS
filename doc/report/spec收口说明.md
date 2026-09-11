# Spec 收口说明（对照最新复审 P0/P1）

> 代码基线：`e6722e2`
> 用途：供 Spec 短复审快速定位每项整改位置。

| 复审项 | 整改结论 | 位置 |
|---|---|---|
| P0-01 参数/配置双层 | token/timeout/parallel/recursive=调用字段；cdslog.*=持久化配置由中层填充 | 配置一览 §1、§2 |
| P0-02 token↔多 CIW | 一 token=一活动 daemon=一 CIW；多 CIW 用多 user/token | 三层架构 §5.4；多用户设计 §10、§6 |
| P0-03 split-host 合同 | 每 role user/jump/proxy、endpoint key、逐 endpoint 指纹、scratch 可见性条件 | 三层架构 §5.2；配置一览 §2/§5/§6.5 |
| P1-01 Spectre 非阻断 | 显式→校验、缺省→探测，失败仅 warning 不阻断 | 本版范围 §2；配置一览 §2.3/§4 |
| P1-02 检查矩阵 | 三时机 × 检查项 × 失败级别 × deadline/重试 唯一矩阵 | 多用户设计 §3.3 |
| P1-03/04 deadline/重试/错误 | 默认 timeout/connect、≤3 次重试、124/255、CommandResult.kind | 三层架构 §4.4、§5.8 |
| P1-05 registry 生命周期 | 文件锁、碰撞、update 缓存失效、remove=本机解绑、吊销步骤 | 多用户设计 §11 |
| P1-06 host-key 输入 | expected.ssh_endpoints 显式 per-endpoint 指纹 schema | 配置一览 §4.2、§6.1 |
| P1-07 日志内部帧 | 第二帧字节格式、UTF-8、限长边界、非法配置拒绝、\\e/\\w 字符 | 日志标准 §4、§6.3、§7 |
| P1-08 canonical schema/API | 注册字段、registry JSON、mode×route 矩阵、端口 TOCTOU、Windows 路径 | 配置一览 §6 |
| P1-09 版本治理 | owner 列表补本版范围、冻结 Manifest、版本号、Supersedes | README §0、Manifest |
| 索引/重复标题/旧路径 | research 02 重复标题、04 显示路径、demo TB 索引、research 07 入库 | research/demo 目录 |
