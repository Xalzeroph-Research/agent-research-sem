# SEM：面向长程 Minecraft Agent 的记忆语义进化方法

## 1. 研究要解决什么问题？

近年来，Agent 研究逐渐从一次性规划和即时推理转向持续交互、长期记忆和自主进化。对于 Minecraft 这类持久化开放世界，Agent 不仅需要完成当前任务，还需要将过去的观察、行动、结果、失败原因和解决方案保存下来，并在未来任务中重新利用。

现有方法通常将长期记忆表示为文本记忆、向量集合、技能库、经验摘要或固定层级结构。它们主要解决以下问题：

```text
如何记录经验
如何检索经验
如何总结经验
如何复用技能
如何调整记忆操作
```

但这些方法通常默认：长期记忆应该以什么方式组织、哪些记忆单元应该存在、各类记忆之间如何分工，已经由人工提前确定。

本文关注一个更基础也更困难的问题：

> 持久化开放世界 Agent 能否从自己的长期交互经验中，自主发现记忆组织中的结构性需求，并持续演化记忆的语义结构？

本文研究的不是简单的记忆内容增加，而是记忆语义组织的变化，包括：

- 创建新的记忆抽象；
- 拆分承担多个职责的记忆节点；
- 合并语义重复的记忆节点；
- 淘汰长期低效的记忆结构；
- 从历史证据中重建新的记忆视图；
- 根据任务和环境变化重新调整记忆之间的职责边界。

## 2. 为什么这个问题重要？

长程 Minecraft 任务通常具有明显的层级依赖。例如，获得钻石可能需要经过资源采集、工具制作、熔炉建造、铁矿冶炼、工具升级和空间导航等多个阶段。任务过程中产生的记忆并不是相互独立的文本，而是涉及实体、资源、位置、时间、动作、状态转移和失败恢复的复杂关系。

随着任务持续进行，固定记忆组织可能出现以下问题：

```text
不同语义被混合存储
同一节点承担过多职责
多个节点重复记录相似经验
新任务需求无法被当前结构表达
旧结构不能解释后来形成的经验
记忆规模不断增加但长期能力没有同步增长
```

因此，Agent 的长期能力不仅取决于“记住了多少”，还取决于“记忆是否形成了适合当前世界和任务的语义组织”。

现有自进化 Agent 已经开始演化记忆内容、技能、经验总结、检索策略和记忆操作，但仍缺少一种完整机制，使 Agent 能够直接调整长期记忆内部的语义责任边界。

本文的核心主张是：

> Long-term memory should evolve not only in what it stores, but also in how its semantic responsibilities are organized.

中文表述为：

> 长期记忆不仅应当演化其存储内容，还应当演化其内部的语义责任组织。

## 3. 本文的核心方法：Semantic Evolution of Memory

本文提出 SEM，即 Semantic Evolution of Memory。

SEM 将长期记忆看作一个能够随长期经验变化的语义结构，而不是一个固定的文本列表或向量数据库。SEM 的目标是让 Agent 逐步形成以下能力：

```text
Experience → Evidence → Memory Demand → Semantic Abstraction
→ Architecture Edit → Validation → Historical Backfill
→ Forward Activation → Future Behavior
```

SEM 的完整方法由三个相互衔接的核心部分组成：

### 3.1 Evidence-Grounded Semantic Memory

将真实 Minecraft 交互转化为带来源、带状态和可追溯的长期证据，并将证据与当前记忆架构分离，使未来出现的新记忆结构能够重新解释历史经验。

### 3.2 Autonomous Memory Architecture Evolution

将长期记忆表示为 Typed Memory DAG，由 Meta-Architect 根据架构无关的长期观测提出新的语义结构假设，并执行创建、拆分、合并和淘汰等结构编辑。

### 3.3 Trusted Validation and Forward Activation

通过类型检查、来源兼容性检查、候选架构隔离、历史重建、前瞻评估和采纳门控，防止语言模型直接修改运行时记忆结构，并保证接受的结构能够被安全地前向激活。

## 4. 论文最终问题定义

设持久化 Minecraft 环境为：

\[
\mathcal{E}=\langle S,O,A,P,\Omega,R,\gamma\rangle
\]

其中：

- (S) 表示世界状态；
- (O) 表示 Agent 能够观察到的环境信息；
- (A) 表示可执行动作；
- (P) 表示环境状态转移过程；
- \(\Omega\) 表示观测机制；
- (R) 表示任务奖励或进度函数；
- \(\gamma\) 表示长期效用折扣。

Agent 在时间 (t) 的交互历史为：

\[
h_t=(o_1,a_1,o_2,a_2,\ldots,o_t)
\]

系统从交互历史中形成持久化证据：

\[
J_t=J^{mem}_t\oplus J^{audit}_t
\]

当前逻辑记忆架构表示为：

\[
A_k=(N_k,E_k)
\]

其中 (N_k) 是记忆节点集合，(E_k) 是节点之间的来源和物化依赖关系。

SEM 的结构演化过程表示为：

\[
A_k\xrightarrow{e_k}A_{k+1}
\]

其中 (e_k) 是一次经过验证和采纳的语义架构编辑。

本文研究的最终目标是：

\[
\max_{\pi,\mathcal{G}}
\mathbb{E}[U_{task}+U_{transfer}+U_{adaptation}]
-\lambda C_{memory}
-\mu C_{evolution}
\]

其中：

- (U_{task}) 表示任务完成和任务进度；
- (U_{transfer}) 表示跨任务经验迁移；
- (U_{adaptation}) 表示对任务和环境变化的适应；
- (C_{memory}) 表示记忆查询和维护成本；
- (C_{evolution}) 表示 Meta、候选构建、验证和激活成本；
- \(\mathcal{G}\) 表示受约束的记忆结构演化策略。

## 5. Related Work 应该如何收敛？

### 5.1 Minecraft Planning Agent

这一部分介绍 Minecraft Agent 如何进行观察、任务分解、规划、行动和失败恢复。DEPS 等方法说明强规划可以支持复杂开放世界任务，但规划能力本身不能解决长期记忆结构如何持续适应的问题。

### 5.2 Memory-Augmented Minecraft Agent

这一部分介绍使用外部记忆、多模态记忆、历史轨迹和技能库的 Minecraft Agent。它们证明了经验保存和记忆复用对于长程任务的重要性，但大多数方法仍使用固定的记忆组织方式。

### 5.3 Experience-Based Self-Evolution

这一部分介绍从成功和失败轨迹中提炼技能、经验、补救策略、guardrail 和可执行知识的方法。已有研究主要研究经验如何成为知识，而 SEM 进一步研究知识如何形成和改变记忆语义结构。

### 5.4 Memory Operation and Architecture Evolution

这一部分讨论记忆抽取、总结、检索、压缩、清理、操作技能和整体记忆系统进化。SEM 与这些方法的区别在于：SEM 直接研究稳定记忆接口内部的语义责任组织，而不是只改变记忆内容、操作策略或外部 Provider 程序。

相关工作最终应收束为：

> Existing work studies how experience becomes knowledge and how knowledge is retrieved or operated; SEM studies how a persistent agent can evolve the semantic organization that determines what kinds of memory it has.

## 6. SEM 方法总览

SEM 在 Minecraft Agent 原有流程中加入记忆语义进化层：

```text
Observe
→ Interpret
→ Retrieve through MEMORY_ASK
→ Plan
→ Execute
→ Verify Environment Effect
→ Commit Grounded Evidence
→ Maintain Memory Views
→ Detect Persistent Structural Demand
→ Propose Semantic Edit
→ Compile and Validate Candidate
→ Backfill from Historical Evidence
→ Activate Forward
```

原有的环境交互、行动执行和任务评价仍然由可信环境与运行时负责。SEM 重点增加的是：

```text
architecture-independent memory demand detection
typed semantic memory representation
autonomous memory architecture synthesis
trusted structural validation
historical backfill
forward architecture activation
```

## 7. Evidence-Grounded Memory

### 7.1 Memory-Grounded Evidence 与 Audit Evidence

SEM 将证据分为两个权限通道：

\[
J=J_{mem}\oplus J_{audit}
\]

`J_mem` 只能包含 Agent 在真实交互过程中获得、并且能够用于未来记忆重建的证据。`J_audit` 用于验证、评估、统计和实验控制，不能被物化为记忆内容。

该设计保证：

```text
Evaluation evidence cannot become memory
Hidden labels cannot become memory
Acceptance decisions cannot become memory
LLM claims cannot replace verified environment state
```

### 7.2 Canonical Evidence Event

每个 EvidenceEvent 至少包括：

```text
episode_id
task_id
world_state_ref
observation_ref
action_ref
effect_receipt
outcome
timestamp
entity_refs
position_refs
source_refs
provenance
```

### 7.3 Future-Reinterpretable Evidence

证据底座不能只保存当前记忆架构已经理解的摘要。它还需要保留足够的原始事实和来源信息，使未来创建的新记忆节点能够重新解释过去经验。

因此，SEM 将证据和记忆分离：

```text
Evidence is persistent factual substrate
Memory is an evolving semantic view over evidence
```

## 8. Typed Semantic Memory Architecture

### 8.1 Memory Node

每个 Memory Node 由以下部分定义：

```text
node_id
purpose
scope
mode
schema
access
sources
transform
maintenance_contract
```

其中：

- `purpose` 描述语义责任；
- `scope` 表示世界级或 Agent 级信息；
- `mode` 表示追加、当前状态或聚合；
- `schema` 规定字段和类型；
- `access` 描述查询方式；
- `sources` 规定证据来源；
- `transform` 规定从证据到记忆视图的转换；
- `maintenance_contract` 规定在线维护方式。

### 8.2 Memory Transform

确定性转换包括：

```text
FILTER
PROJECT
GROUP_BY
DEDUP
UNION
AGGREGATE_STATS
```

受限语义转换包括：

```text
SEMANTIC_MAP
SEMANTIC_REDUCE
SEMANTIC_COMPOSE
```

系统不允许 Meta 生成任意 Python、任意外部调用或未经过验证的隐藏程序。

### 8.3 Memory Query

Planner 不依赖固定节点名称，而是通过统一记忆接口提交意图：

```text
STATE_READ
MEMORY_ASK
NODE_DISCOVERY
```

例如：

```text
查询当前任务可能涉及的历史资源经验
查询某区域的可复用路径
查询某类失败的恢复方式
查询某实体最近状态
查询过去行动的效果和前置条件
```

## 9. Autonomous Memory Architecture Evolution

### 9.1 Architecture-Independent Memory Opportunity

系统首先在记忆检索和节点发现之前识别长期记忆需求：

\[
MemoryOpportunity=HistoricalDemand\land EligiblePriorEvidence
\]

Memory Opportunity 不依赖当前 Node 名称、检索器或人工目标 ontology。

### 9.2 Neutral Architecture Observation

系统向 Meta 提供架构无关的观测，包括：

```text
schema-driven field profiles
memory usage statistics
query outcomes
incident exemplars
unresolved intent clusters
pairwise node statistics
architecture exposure
evolution ledger summary
```

观测中不得出现：

```text
recommended_edit
target_node
expected_architecture
human ontology label
hidden task family label
```

### 9.3 Semantic Proposal

Meta 只能输出：

```text
NO_EDIT
CREATE_NODE
RETIRE_NODE
SPLIT_NODE
MERGE_NODES
```

每个 proposal 必须包含：

```text
symptom_refs
hypothesis
edit
expected_effects
rationale
source_refs
```

Proposal 不允许直接携带自我批准的置信度，也不允许直接触发激活。

## 10. Four Structural Edits

### 10.1 CREATE_NODE

当现有结构无法表达某类长期语义需求时创建新的记忆节点。例如，Agent 反复遇到路径选择、失败恢复或实体状态变化，但当前节点只能保存一般经验，此时可以提出新的 RouteMemory、FailureRecoveryMemory 或 EntityStateMemory。

### 10.2 RETIRE_NODE

当某节点长期低使用、重复、过期或无法产生正向效用时，将其从当前架构中退出。其历史证据仍然保留，未来可以被新的结构重新利用。

### 10.3 SPLIT_NODE

当同一节点同时承担多个语义责任并造成检索冲突或维护混乱时，将其拆分为多个具有更清晰职责的节点。子节点继承合法来源和基础 schema，并通过受限 selector 形成可验证的分区。

### 10.4 MERGE_NODES

当两个节点具有相同范围、模式、schema、来源和转换语义，并且承担互补或重复职责时，将其合并，以降低重复维护和检索成本。

## 11. Trusted Candidate Validation

候选结构必须经过以下验证：

```text
Syntax Validation
Field and Type Validation
Transform Validation
Graph and Acyclicity Validation
Source Compatibility Validation
Edit Semantics Validation
Complexity Validation
Canonical No-Op Detection
```

候选架构从同一个历史证据切片 clean materialize，并与当前架构在相同世界状态、相同证据边界和相同任务条件下进行前瞻比较。

候选采纳可以写成：

\[
Accept(A')=1
\iff
Valid(A')
\land
\Delta U(A')\geq\epsilon
\land
\Delta C(A')\leq C_{max}
\land
NoCriticalRegression(A')
\]

其中：

- `Valid` 表示结构通过可信验证；
- \(\Delta U\) 表示任务效用变化；
- \(\Delta C\) 表示额外成本；
- `NoCriticalRegression` 表示关键任务和证据约束没有出现严重退化。

## 12. Baseline 设计

Baseline 应分为外部参考、记忆机制对照和内部控制三类。

### 12.1 Non-Evolving Planning Baseline

使用强规划器完成 Minecraft 任务，但不使用可演化的长期语义记忆。

该 baseline 回答：

> 仅依靠规划和即时上下文能够达到什么水平？

### 12.2 Fixed Memory Baseline

使用预先确定的 Typed Memory DAG，但不允许结构编辑。该 baseline 与 SEM 使用相同 Memory ABI、模型、Planner、Executor 和环境。

### 12.3 Flat Memory Baseline

使用平面经验记忆或简单向量检索，检验结构化语义组织相对于内容累积的作用。

### 12.4 Skill Library Baseline

使用持续增长的可复用技能库，检验技能资产积累与记忆语义结构进化之间的差异。

### 12.5 Rule-Based Evolution Baseline

使用与 SEM 相同的证据、监测、编辑语法、验证预算和任务条件，但通过确定性规则进行编辑选择。该 baseline 用于隔离 Meta 的语义抽象和结构推理能力。

### 12.6 SEM

使用完整的证据底座、Typed Memory DAG、架构无关监测、Meta-Architect、可信编译、候选门控、历史回填、在线维护和前向激活。

## 13. 实验流程

### 13.1 Phase A：Evidence Accumulation

所有方法使用相同的 Planner、Executor、Minecraft 环境、任务集合和行动预算完成任务。系统记录真实观察、行动、效果、失败原因和任务进度，形成统一的 `J_mem`。

这一阶段主要隔离：

```text
environment interaction
evidence collection
task outcome recording
memory demand formation
```

### 13.2 Phase B：Semantic Architecture Proposal

当系统积累足够的架构无关证据后，Fixed、Rule-Based 和 SEM 按各自 treatment 规则处理结构演化。

所有方法共享：

```text
same evidence cut
same current world state
same task history
same memory query ABI
same structural grammar
same candidate budget
```

### 13.3 Phase C：Candidate Validation and Activation

候选架构从相同的历史证据切片重新生成，并在隔离条件下完成验证。只有通过类型、来源、依赖、效用和成本检查的候选才可以前向激活。

### 13.4 Phase D：Forward Persistent Evaluation

系统在激活后的持续任务流中评估：

```text
future task success
memory usage
transfer
recovery
environment adaptation
architecture stability
maintenance cost
```

## 14. Minecraft 任务设计

### 14.1 Resource Gathering

```text
obtain_log
mine_cobblestone
obtain_coal
obtain_raw_iron
find_resource_in_region
```

### 14.2 Craft and Technology Tree

```text
craft_planks
craft_sticks
craft_crafting_table
craft_stone_pickaxe
craft_furnace
smelt_iron_ingot
craft_iron_pickaxe
```

### 14.3 Navigation and Revisit

```text
reach_target_region
return_to_known_location
find_resource_point
reuse_successful_route
recover_from_navigation_stuck
```

### 14.4 Combat and Survival

```text
fight_weak_mob
retreat_with_insufficient_equipment
recover_after_combat_failure
adjust_action_to_equipment_state
```

### 14.5 Building and Spatial Tasks

```text
place_material_at_target
continue_previous_structure
locate_required_building_material
complete_simple_building
```

### 14.6 Mixed Long-Horizon Tasks

```text
collect resources
craft tools
explore region
smelt materials
upgrade equipment
complete construction or combat goal
```

任务按照短程、中程、长程和环境变化条件组织，但任务生成器不能直接暴露预期的记忆结构或编辑答案。

## 15. 指标体系

### 15.1 Task Success Rate

\[
SR=\frac{1}{N}\sum_{i=1}^{N}\mathbf{1}[g_i\ completed]
\]

### 15.2 Long-Horizon Success Rate

只统计具有多个子目标和前置依赖的任务成功率，用于衡量长期记忆对复杂任务链的作用。

### 15.3 Knowledge and Memory Usage Success

衡量被检索和被使用的记忆是否真正改善后续任务进展。

### 15.4 Historical Backfill Coverage

衡量新记忆节点能够从历史证据重建的有效信息比例。

### 15.5 Structural Evolution Quality

包括：

```text
accepted edit rate
useful abstraction rate
architecture churn
reversal rate
evolution delay
sustained target effect
functional coverage
```

### 15.6 Reliability and Safety

包括：

```text
invalid proposal rejection rate
source compatibility failure rate
provenance completeness
audit leakage rate
candidate isolation integrity
materialization confluence
```

### 15.7 Risk-Cost-Utility

定义长期综合效用：

\[
U_{SEM}=U_{task}+U_{transfer}+U_{adaptation}
-\lambda_1C_{query}
-\lambda_2C_{maintenance}
-\lambda_3C_{evolution}
\]

## 16. 必须绘制的图表

### Figure 1：SEM 方法总览

展示：

```text
Experience
→ Evidence
→ Typed Memory DAG
→ Neutral Observation
→ Meta Proposal
→ Trusted Candidate Validation
→ Historical Backfill
→ Forward Activation
```

### Figure 2：Memory Architecture Evolution

展示初始记忆结构、结构性需求、Meta 提案、候选架构和激活后的新结构。

### Figure 3：Long-Horizon Performance

横轴为持续任务数量或演化时间，纵轴为任务成功率、任务进度或综合效用，比较 Fixed、Rule-Based 和 SEM。

### Figure 4：Architecture Evolution Timeline

展示节点数量、编辑类型、任务需求和结构收益随时间的变化。

### Figure 5：Transfer and Environment Drift

展示任务分布变化、世界状态变化后不同方法的性能下降和恢复过程。

### Figure 6：Evolution Cost and Stability

展示 Meta 调用、编辑数量、结构复杂度、延迟、成本和结构振荡。

### Figure 7：Historical Backfill Effect

比较有历史回填和无历史回填条件下新节点的初始质量与长期效用。

## 17. 数据日志设计

每个 episode 记录三类日志。

### 17.1 Episode-Level Log

```json
{
  "episode_id": "ep_001",
  "task_id": "craft_iron_pickaxe",
  "world_id": "world_001",
  "method": "SEM",
  "success": 1,
  "progress": 1.0,
  "total_steps": 4210,
  "llm_calls": 18,
  "memory_calls": 7,
  "evolution_events": 1,
  "total_cost": 0.0
}
```

### 17.2 Memory Query Log

```json
{
  "episode_id": "ep_001",
  "query_id": "q_007",
  "intent": "find_reusable_route",
  "discovered_nodes": ["RouteMemory"],
  "retrieved_records": ["e_018", "e_024"],
  "source_refs": ["jmem_018", "jmem_024"],
  "query_cost": 0.12,
  "outcome": "useful"
}
```

### 17.3 Evolution Log

```json
{
  "generation": 4,
  "current_architecture": "A_3",
  "proposal": "CREATE_NODE",
  "symptom_refs": ["incident_017", "opportunity_009"],
  "candidate_architecture": "A_4",
  "edit_valid": 1,
  "candidate_accepted": 1,
  "backfill_coverage": 0.74,
  "heldout_effect": 0.18,
  "architecture_cost": 0.06
}
```

## 18. 结果章节的写法

结果不能只报告最终任务成功率，而应围绕以下问题组织：

1. SEM 是否改善长程任务能力；
2. 性能变化是否与真实记忆结构变化同步；
3. 新记忆抽象是否能够被有效创建和使用；
4. 历史回填是否提高新结构的初始价值；
5. SEM 是否改善任务迁移和环境漂移适应；
6. 可信编译和候选门控是否有效降低错误结构进入运行时的风险；
7. 结构收益是否足以覆盖额外的推理和维护成本。

主表展示整体任务效用和长程成功率，机制表展示消融实验，结构表展示编辑质量和架构变化，成本表展示模型调用、查询和维护开销。

## 19. 研究结论

本文提出 SEM，一种能够从持久化交互经验中持续演化长期记忆语义组织的完整方法。SEM 将长期记忆表示为具有类型、来源、维护模式、访问方式和转换规则的 Typed Memory DAG，并通过证据底座、架构无关监测、Meta-Architect、可信编译、候选门控、历史回填和前向激活形成完整闭环。

SEM 的关键变化不是简单增加记忆条目，而是使 Agent 能够重新组织长期记忆内部的语义责任。Agent 可以根据持续任务经验判断哪些记忆需要创建，哪些节点需要拆分，哪些节点应该合并，哪些结构已经失去价值，以及新结构如何重新解释过去经验。

这种能力使长期记忆从静态存储组件转变为可持续适应的语义系统，为持久化开放世界 Agent 的长期认知、任务迁移、失败恢复和环境适应提供新的方法基础。

## 20. 论文贡献

### Contribution 1：记忆语义进化方法

提出 SEM，将长期记忆的演化对象从内容和检索扩展到记忆语义组织结构。

### Contribution 2：Typed Memory DAG

提出具有类型、来源、维护和访问语义的可进化 Memory DAG，为长期记忆结构提供统一表示。

### Contribution 3：自主结构编辑机制

提出基于真实经验的 CREATE、RETIRE、SPLIT 和 MERGE 结构编辑机制，使 Agent 能够形成新的记忆语义抽象。

### Contribution 4：可信结构编译与采纳

提出从 Meta proposal 到 Typed IR、Candidate Materialization、Validation 和 Forward Activation 的可信结构演化流程。

### Contribution 5：历史证据重解释机制

提出独立于当前记忆架构的持久化证据底座和 Historical Backfill，使新的记忆结构能够重建和利用历史经验。

### Contribution 6：长程 Minecraft Agent 记忆语义进化评估体系

建立覆盖长期任务、任务迁移、环境变化、结构稳定性、证据完整性、演化质量和系统成本的实验方法。

## 21. 最终一句话

本文最终希望读者记住的不是“我们增加了一个记忆库”，也不是“我们让模型生成了更多经验总结”，而是：

> A persistent agent should evolve the semantics of its memory before its memory becomes structurally inadequate.

中文表述为：

> 持久化智能体不仅要积累记忆，还要在记忆结构不再适合长期任务时，自主演化记忆的语义组织。
