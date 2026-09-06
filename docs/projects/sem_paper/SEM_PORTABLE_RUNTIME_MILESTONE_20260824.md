# SEM Portable Runtime Milestone — 2026-08-24

本记录是
[`PAPER_IMPLEMENTATION_COMPLETENESS_AUDIT_20260823.md`](PAPER_IMPLEMENTATION_COMPLETENESS_AUDIT_20260823.md)
之后的实现增量，不替代论文设计冻结，也不把可运行性等同于科学结论。

## 本轮完成

1. 平台新增通用、确定性、可检查点恢复的 state-machine environment：领域仅注入
   dynamics，平台统一拥有 session、action identity、effect receipt、reconcile、
   validate-before-mutate restore 与生命周期。
2. SEM 新增真实非 Minecraft 执行入口和 reference closed world provider。它复用
   `ExperimentRunSpec`、`StudyProtocol`、`StudyUnitExecutionPort`、generic workload、
   `MethodSession` 和同一 grounded evidence schema，不在项目中复制执行器。
3. recall 返回的真实 record/node/score/source-ref 与最终 task outcome 进入一个共享的
   session telemetry authority；telemetry 和 task idempotency 状态一同进入 schema-v9
   SEM snapshot，恢复前先完整校验。
4. Minecraft production graph 绑定 branch-local authoritative world checkpoint provider、
   平台 `WorkloadCheckpointCoordinator` 和类型化 checkpoint publication port。每个
   repetition 的 source cut 与每个 branch 的最新 task-boundary checkpoint 通过原子
   `resume_index.json` 联结；恢复会校验 run、protocol、task、candidate、source cut、
   environment/method generation 和 task prefix。
5. 可复用结果上升到平台 API：`MethodTaskOutcome`、`WorkloadBatchResult`、
   `CheckpointedWorkloadBatchResult`、checkpoint publication port 和 state-machine
   contracts 均不依赖 SEM 或 Minecraft 实现。
6. MC environment checkpoint 现在同时封装 world provider payload、state projection、
   observation sequence 和 action verification ledger；恢复会先校验完整 envelope，再
   停 bridge、恢复 world、重连 bridge，失败后的 session 会 fail closed。
7. session cell 新增 prepared-adoption 单一提交入口：durable adoption、live generation
   publication 与 lineage record 受 serving 同一把锁保护；并发 reader 不再能观察到提交与
   发布之间的进程内分叉窗口。
8. 平台 run-manifest authority 新增不可变 evidence-bundle contract。raw stream 与可重建
   projection 分离，成员具有 schema/count/artifact-ref/SHA-256；严格 codec 拒绝未知字段、
   空 required stream 和悬空 derivation。
9. generic workload 对每次 action 统一发布 started/finished evidence，携带同一个 request
   digest、cycle/action identity、environment generation、observation/effect refs 与 duration；
   Minecraft 与非 Minecraft 无需复制 recorder。
10. 平台新增 `runtime/toolchain` 子系统与通用安全归档物化接口。官方 Eclipse
    Adoptium Temurin provider 仅通过 artifact API 获取内容，校验元数据中的 SHA-256、
    size、OS、architecture、JDK image 与 HotSpot identity；tar provider 对路径穿越、
    单根逃逸 symlink、重复成员、设备文件、解压规模和缺失 `bin/java` 全部 fail closed。
11. MC 入口新增显式 `--acquire-java-runtime` 路由。Node、Mineflayer exact package 与
    protocol compatibility 先于下载验证；之后验证 exact `java -version`，并把 archive、
    materialized tree、Java executable 与 receipt digest 纳入 run/source environment identity。
    已验证 cache 复用不访问 metadata，任何 archive/tree/executable/version drift 均拒绝。
12. 在当前托管容器完成了真实官方资产预检：Temurin `21.0.12.1+1` 通过 API 元数据、
    SHA-256、tar 物化和 Java 21 探针；Mojang `1.21.8` server.jar 通过官方 manifest
    SHA-1/SHA-256 校验；Node/Mineflayer/pathfinder/pvp 与 1.21.8 protocol 全部通过。
    修复了 Adoptium v3 `version` 响应形状适配，以及 Temurin 首次 `java -version` 的
    一次性 `.src.zip.*` 初始化导致的错误 tree drift。第二次 preflight 复用 Java 收据
    且未重新访问 metadata。该验证仍未接受 EULA、未启动服务器。
13. 在隔离临时目录用已验证 Temurin 21 直接执行官方 `server.jar` bootstrap，确认
    Mojang bundled libraries 可解包，随后只生成 `eula=false` 并在其 EULA 门禁退出；
    没有开放端口或持久进程。由此把 Java/官方 jar 兼容性与真正 live server 启动分开，
    不把不支持的 `--version` 参数误报为成功。

## 明确未完成

- production 仍未组合真实 stage providers。单一 session adoption/serving commit boundary
  已建立，但现有 atomic adoption backend、typed generation artifact serving 与 pipeline
  provider 尚未全部接到该入口，因此不能宣称 live self-evolution 已完成。
- Core-6、RuleBased、必要 ablation、冻结 repetition/seed/order/budget 尚未执行。
- LTE-SR、LPI、TDP、ELCE、HPEF、GAG 等完整 estimand/attribution/cost registry 尚未发布。
- 当前 checkout 没有 qualified live deployment closure、真实 Minecraft T2B PASS bundle
  或正式实验结果。托管容器中现有系统 Java 仍是 17；显式 Java 21 供应路径已经通过
  真实官方元数据、官方资产下载、tar 物化和执行探针预检，但本轮没有接受 EULA、启动
  Minecraft 或把该可运行性提升为 scientific claim。
- topology declaration-only leaves 与既有 opaque API debt 仍由专项架构迁移处理。

## 验证边界

- deterministic non-MC reference study 已执行端到端，结果固定标记
  `scientific_claim=false`。
- Python compile、global architecture gate、silent-failure audit、no-degradation audit 与
  SEM architecture audit 均在当前源码上执行。
- 完整 pytest 集合在当前托管容器中需剔除两个依赖 `/proc/<Popen pid>` 的 Linux
  process tests：容器返回的 child PID 不存在于其挂载的 `/proc`，即使 child 仍在运行。
  该宿主限制不应通过弱化 production procfs identity 校验来规避；目标 Linux 主机仍需
  执行这两个测试。本轮未过滤全量结果为
  `1083 passed, 2 failed, 1 warning, 4 subtests passed`；两个失败均为相同的
  `/proc/<Popen pid>/stat` 不可见问题，不属于本轮 Java/MC runtime 变更。加入最终
  symlink 单根逃逸用例后，精确排除上述两项宿主测试的完整集合为
  `1084 passed, 2 deselected, 1 warning, 4 subtests passed`；Node bridge 为 `8 passed`。

## 下一优先级

下一里程碑应把现有 atomic adoption backend、typed generation artifact serving 与真实
stage provider 全部绑定到新的 session authority，然后冻结完整 comparator / ablation
matrix 与 metric registry；只有通过 qualified model、真实 MC T2B、完整 evidence
和统计门禁后，才允许把运行产物提升为论文科学证据。
