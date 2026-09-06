# Paper-1 实现完整性审计 — 2026-08-23

## 判定规则

本文件只记录当前 `agent-research-platform-system` 工作树的事实，不继承
`memory-evolving/v034_work` 的完成声明，也不把目录、接口、单元测试或
scripted smoke 当成真实论文结果。

每项能力按四层判定：Contract（接口存在）、Test（合成/单测闭合）、
Production（当前生产调用链使用）、Evidence（真实模型/环境/长时运行证据）。
只有四层都闭合，才可称为“论文实验已实现”。

## 当前结论

当前不是“所有方法、baseline 和实验都实现”。准确状态是：

- 平台通用 run parent、workload、Study Matrix、artifact、diagnostics、资源解析和
  qualified-model closure 的接口/部分生产调用链已经存在；
- SEM 的证据隔离、架构 IR、Deluxe read-side、candidate materializer、MC
  分支比较和非 MC workload seam 有较完整的 contract/test 基础；
- 真实 self-evolution stage factory 没有在生产入口构造，candidate 不能
  被当作论文的 SelfEvolve；
- 当前实验仍是 `control + candidate`、`repetitions=1` 的开发矩阵，不是
  设计文档冻结的 Core-6、RuleBased、ablation、DEV/TEST 和统计预算矩阵；
- MC 有环境适配器和 world-cut 分支机制，但没有绑定可恢复的 authoritative
  world checkpoint/resume；
- 非 MC 只有通用协议/适配器/测试，没有具体环境 provider 和可执行生产入口；
- 当前 checkout 没有 qualified deployment closure artifact 或 T2B live
  world evidence，因此没有 model-backed 或 Minecraft scientific claim。

本批 run-parent 改动前的机器审计结果：

```text
scripts/sem_paper_architecture_audit.py
blocking_open = 13
ARCHITECTURE_GATE_PASS
```

本批改动后的本地静态审计为 `blocking_open = 12`，其中
`PAPER_GENERIC_EXPERIMENT_RUNTIME_BYPASS=closed`；仍需由服务器重新运行审计、
架构门禁和回归验证后才把该销项提升为已验证状态。

## A. 平台与架构

| 能力 | 当前证据 | 状态 |
|---|---|---|
| 通用 `ExperimentRunSpec` + run parent | `experimentation/run/api` 与 `run/runtime/ExperimentRunApplication`；Paper MC/non-MC root 只接收 `ExperimentRunExecutionPort` | 已接线，服务器验证待做 |
| 通用 workload/failure boundary | `experimentation/workload` + MC/non-MC adapters | 部分完成 |
| Study Matrix executor | `experimentation/run` 的 run parent 委托 `study/runtime/matrix.py`，MC/non-MC root 不再各自发布 | 已接线，服务器验证待做 |
| Artifact/diagnostics | `RunArtifactStorePort`、`RunDiagnosticsPort` 与 Paper publisher | 部分完成 |
| Qualified model closure | reader、strict binding、runtime store factory 已接线 | 无 closure artifact，未完成证据 |
| Workload checkpoint | generic coordinator 有；MC 没有 authoritative world provider/resume | 未完成 |
| 运行入口解耦 | `scripts/run_sem_minecraft_experiment.py` 仍约 1,000 行，混合解析、provider、lifecycle、manifest；run 编排已下沉但 operator 仍过宽 | 部分完成 |
| MC/non-MC 统一生产入口 | 有 non-MC protocol/root 测试；无具体 provider/entrypoint | 未完成 |
| 拓扑唯一权威 | `topology.py` 与 `catalog.json` 都有声明面 | 未完成 |
| 叶节点所有权迁移 | 182 个 catalog 节点中 81 个 declaration-only，coarse roots 仍持有真实代码 | 未完成 |
| API payload 类型化 | 选定 API 面仍有 54 个 `object` contract occurrences | 未完成 |

## B. SEM 方法本体

| 方法面 | 当前事实 | 当前能否称为生产方法 |
|---|---|---|
| `J_mem` / `J_audit` / `J_eval` | stores、grounding audit、MC evidence ingestor 和边界测试存在 | 仅 adapter/测试闭合，无长时证据 |
| Seed-C / Seed-X | architecture preset、typed serialization/validation/compiler、candidate contract 存在 | 可合成验证，不能替代完整生命周期实验 |
| Core/Hybrid/Deluxe serving | Deluxe API/runtime、capability、working-set、fault、lineage、grounding 已迁移 | fixed Seed-C 已接线；live candidate adoption 未闭合 |
| Candidate materialization | `SemPaperCandidateMethodMaterializer`、typed snapshot factory 存在 | 需要真实 evolution factory；`build_seed_x_candidate()` 不是 SelfEvolve 结果 |
| Evolution 七阶段 | contracts、`EvolutionPipeline`、stage-composition test 存在 | **否**：生产入口没有构造 `PipelineSessionEvolutionFactory` |
| Session adoption/reconciliation | session runtime、adoption records、reconciliation ports 有测试 | 只有显式注入 factory 时可运行 |
| MC grounding/action/evidence | bridge isolation、evidence firewall、branch receipts 有测试 | 结构接线存在，需 live T2B |
| 非 MC reuse | `SemPaperNonMinecraftWorkload*` 与 generic batch 接口存在 | **否**：无 concrete environment/planner/evidence provider 和入口 |

## C. Baseline、方法和实验矩阵

设计文档冻结的正式比较至少包含 Seed-C/Seed-X、FixedSeed/RuleBasedEvolver/
SelfEvolve、paired Core-6、DEV-calibrated/TEST-frozen repetitions、机制消融、
matched multi-granularity control、预算层 external baseline，以及 lifetime、
edit/adoption、cost、provenance、attribution、held-out audit 统计。

当前入口实际只有：

```text
variants = control + candidate
repetitions = 1
candidate = build_seed_x_candidate()
metrics = success_rate, utility_mean, steps_total, duration_s_total,
          memory_queries_total, task_failed_total, task_blocked_total
```

所以当前状态为：

| 项目 | 状态 |
|---|---|
| Fixed memory control | 有 explicit control binding；不是完整 FixedSeed 统计实验 |
| Candidate treatment | 有 materializer seam；无真实 SelfEvolve stage binding |
| RuleBasedEvolver | 未实现/未接入当前 Paper production code |
| Core-6 | 未实现；只有一个 control 和一个 treatment |
| Ablations / external baselines | 未实现/未接入 |
| Repetition/statistical power/budget/run-order | 未实现为 executable matrix |
| Full scientific metric registry | 未实现；当前是 workload smoke metrics |
| Scientific claim gate | 已 fail-closed，明确记录 live endpoint/Core-6/repetition 缺失 |

## D. MC 与非 MC 边界

MC 的 bridge、generic task/failure/batch/Study Matrix、source cut、control/
candidate branch 和 evidence adapter 已有结构调用链。checkpoint wrapper 会
调用 `MinecraftEnvironmentSession.checkpoint()`，但当前环境组合没有绑定
`MinecraftCheckpointPort`，因此实际恢复会 fail closed。

非 MC 已定义 environment/planner/state/evidence/completion ports，并复用 generic
batch 与 Study Matrix；但没有 concrete environment 语义、生产 planner/evidence
provider 或 `run_sem_non_minecraft_experiment.py` 等生产入口。因此目前只能证明
“接口可复用”，不能证明“论文已在非 MC 基座上实现”。

## E. 本轮修复与销项顺序

本轮已完成：

1. 纠正误迁移后的 owner/document 事实；
2. 将 Paper audit 扩展为 12 个 blocking findings；
3. 新增并实际使用 `ExperimentRunSpec`，写入 run manifest；
4. 将 production `build_runtime` 的 evolution factory 改为强制参数，防止重新引入 disabled/default candidate；
5. 将同一 `ExperimentRunSpec` 绑定到 MC 与非 MC production root，校验 run/study/task/repetition 一致性。
6. 将 Study Matrix 的分配、执行和发布收束到平台 `experimentation/run` 的
   `ExperimentRunApplication`；MC 与非 MC root 不再分别持有 Study Matrix
   和 artifact publication authority，而只接收 `ExperimentRunExecutionPort`。

后续严格按以下顺序：

1. 抽取外层脚本的 typed application/run lifecycle interfaces，具体 provider 仍只在 application composition root；
2. 补真实 evolution stage composition，不能用测试 fake 关闭 finding；
3. 绑定 MC authoritative world checkpoint/resume；
4. 提供真实、可复现的非 MC adapter 和 production entrypoint；
5. 将 Core-6、RuleBased、ablations、repetitions、budget、full metrics 变成 executable protocol；
6. 最后才进入 T2B/live model evidence 和正式实验。

本审计期间没有运行 Minecraft、模型、服务器、非 MC 环境或科学实验。
