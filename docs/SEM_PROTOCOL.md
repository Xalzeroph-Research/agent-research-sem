# SEM 实验协议（Minecraft 主实验 v2）

## 1. 研究对象与比较原则

SEM 研究的是长期交互中的记忆表示与语义责任组织：智能体是否能把
环境经历转化为可复用、可校验、可演化的记忆结构。实验只改变长期记忆
处理方式；Minecraft 版本、世界初始化、Noetrium 环境 provider、动作
接口、模型 planner、任务清单、预算、成功判定和日志格式全部冻结。

主实验的四个条件为：

| 条件 | 记忆行为 | 是否允许拓扑演化 |
|---|---|---|
| no_memory | 不保留可供后续任务查询的长期记忆 | 否 |
| flat_episodic | 以单一 episodic 容器保存经历 | 否 |
| fixed_typed | context → episode → outcome 的固定类型图 | 否 |
| sem | 同一初始 typed 图，依据失败反馈提出并应用语义拓扑编辑 | 是 |

fixed_typed 是主因果参照；SEM 与它共享初始化、信息、planner 和
执行预算，因此差异可归因于语义拓扑自进化，而不是系统规模或模型差异。
## 2. Benchmark 与任务来源

主 benchmark 的可执行定义位于
projects/sem_paper/experiments/manifests/sem_minecraft_tasks_v2.json，
benchmark id 为 sem_minecraft_memory_evolution，revision 为 v2。
任务尽量复用 MC-MineEvolve 的 70-task suite，保留其 wooden、stone、
iron、open-world、combat、construction、armor 等任务族；当前主矩阵
使用其中 12 个 executor-compatible 任务，因 MineEvolve 的原始执行器
与 Noetrium Mineflayer provider 不同，做了最小的动作接口归一化和 grounded
success spec 转换。

12 个任务在同一 assignment 内按固定顺序运行并共享世界状态；不同
assignment 需要 fresh vanilla world。每个任务有 task id、来源引用、
目标、family、最大动作数、时间预算、success spec 和动作白名单。
manifest 中的 action_plan 只用于 scripted smoke，真实 model run 不会
把它发送给 planner，避免答案泄漏。
## 3. Baseline 矩阵

主论文报告同一 Noetrium/Minecraft 接口下的四条件结果。它们是严格的
matched-stack baseline，而非手工编造的“能力分数”：

- no_memory：无长期记忆下界，检验任务是否仅靠当前观察即可完成。
- flat_episodic：有记忆但没有类型/关系组织，检验“存储经历”本身的收益。
- fixed_typed：固定 context/episode/outcome 图，检验结构化但不演化的记忆。
- sem：本文方法，检验语义责任拓扑能否在失败后产生可复用结构。

此外，catalog 中记录 MineEvolve、Voyager、JARVIS-1、MemoryAgentBench、
MemoryArena、LongMemEval 和 BEAM。它们用于外部定位、任务复用和结果
讨论；若未在相同 Minecraft 版本、同一动作 API、同一 planner 和同一
success spec 下重跑，不把其公开数字伪装成 paired baseline。
## 4. 运行与随机化

protocol builder 为 build_sem_paper_confirmatory_protocol，默认
3 repetitions；每个 repetition 由确定性 hash 生成 seed。Noetrium
ExperimentPlan 固化 assignment、variant binding、protocol digest、
task manifest digest 和 metric names。独立统计单位是 assignment，而
不是把所有 task 行展平后当独立样本。

真实运行必须设置：

    SEM_PLANNER_MODE=model
    SEM_MODEL_QUALIFIED_CLOSURE=<Noetrium-published-qualified-model-closure.json>
    SEM_MODEL_REQUEST_ROOT=<durable-model-request-evidence-directory>
    MC_HOST=127.0.0.1
    MC_PORT=25565
    MC_VERSION=1.21.1
    MC_REQUIRE_WORLD_RESET=1
    MC_ASSIGNMENT_RESET_COMMAND=<fresh-world supervisor command>
    SEM_RESULTS_DIR=<raw-result-directory>

模型 endpoint、deployment generation、model identity 与 transport timeout 必须来自
Noetrium qualified closure；SEM 不接受 `SEM_MODEL_BASE_URL` / `SEM_MODEL_NAME`
作为真实实验的模型权威，也不提供 raw HTTP fallback。动态 task、snapshot 与 memory
只进入 compiled prompt/request body，固定 planner prompt identity 独立冻结并进入请求证据。

入口：

    python -m projects.sem_paper.cli doctor
    python -m projects.sem_paper.cli protocol
    python -m projects.sem_paper.cli real-pilot
    python -m projects.sem_paper.cli real --repetitions 3
## 5. 记录指标与分析

每个 assignment 输出一份不可覆盖的 raw JSON，包含 assignment identity、
variant binding、diagnostics、task result、action outcome code、verified
effects 和 evidence digest。主指标为：

- success_rate：任务成功比例；
- utility_mean、steps_total、duration_s_total：任务效用与成本；
- memory_queries_total、memory_entries_total、active_node_count；
- architecture_generation、candidate_count、adopted_count、rejected_count；
- historical_backfill_count、verified_actions_total、evidence_closed_total。

统计时先按 assignment 聚合，再计算 treatment 的均值和 paired
sem - fixed_typed 差值；报告 bootstrap 或 paired permutation 的
95% 区间，并同时报告每个任务族的结果。结构指标不能替代成功率，只用于
解释 SEM 是否确实改变了表示结构。

## 6. 有效性边界

scripted fixture、EvoBench diagnostic stream 和 real-pilot 只验证接口、
确定性和日志闭环，不支持论文结论。只有真实 vanilla server、真实
model planner、每 assignment world reset、verified action receipt、
evidence closure 和完整 repetition 矩阵都通过，结果才可进入 claim-ready
表格。若 world reset 未配置，CLI 必须标记 exploratory，不能称为严格
confirmatory。


## Implementation alignment

The implementation decisions in
SEM_IMPLEMENTATION_ALIGNMENT.md are normative for the current SEM branch:

- fixed_typed is persistent but non-evolving; no_memory is the
  non-persistent condition.
- Runtime adoption is proposal-blind and does not require an immediate
  positive task utility delta.
- Minecraft action planning belongs to the agent/environment adapter.
- SEM imports generic graph contracts through the generated Noetrium facade.
- EvoBench is diagnostic only; Minecraft claims require the real protocol.


### 6.1 Evidence-channel and monitor closure

The implementation maintains separate J_mem and J_audit channels. Audit
records are checkpointed for reproducibility but are never returned by
recall, attached to Typed Memory DAG nodes, or used as candidate backfill
evidence. The architecture-independent monitor records structural symptoms
and query outcomes only; it does not select an edit or enforce utility-based
online adoption.
