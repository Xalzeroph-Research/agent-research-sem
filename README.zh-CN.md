# Agent Research SEM

Self-Evolving Memory（SEM）是构建在 Noetrium 上的下游研究方法。最新方法稿
和 docs/SEM_PROTOCOL.md 是科学定义；本仓库不会根据 scripted fixture
重新定义方法。

## 所有权边界

- Noetrium 负责 typed contract、Method/runtime 边界、Memory Graph 校验与
  原子激活、环境 provider、qualified model、实验计划、checkpoint、恢复和
  evidence 基础设施。
- SEM 负责 treatment 语义、evidence 解释、架构无关监控、candidate proposal、
  历史回填和科学 audit。
- Minecraft 动作规划属于 agent/environment adapter；SEM memory core 不拥有
  Minecraft 动作名或任务计划。
- scripted run 只是 conformance smoke，不能产生 Minecraft 科学性能结论。

## 四个标准 treatment

| Treatment | 持久记忆 | 拓扑演化 |
|---|---:|---:|
| no_memory | 否 | 否 |
| flat_episodic | 是 | 否 |
| fixed_typed | 是，固定 Typed Memory DAG | 否 |
| sem | 是 | proposal-blind CREATE/RETIRE/SPLIT/MERGE |

在线采纳不要求正的 utility delta。utility、transfer、recovery、cost 和
negative transfer 属于隔离的 held-out audit channel，不能进入运行时记忆物化。

## SEM 使用的 Noetrium 公共接口

SEM 通过自动生成的 public facade 使用 Noetrium：

- noetrium.contracts.systems.components：VersionedMemoryGraph、快照、
  typed node/edge、operation 和原子图状态；
- noetrium.contracts.systems.participant__method：MethodSession、
  MethodEndpointPort、MethodSessionRuntime、MethodServices、snapshot、
  task outcome 和 recall contract；
- noetrium.contracts.systems.participant__agent：AgentMemoryPort、
  AgentMemoryContext、AgentStepReceipt 和 durable checkpoint；
- noetrium.contracts.systems.environment__minecraft：环境、observation、
  action、effect 和 evidence 边界；
- noetrium.contracts.systems.model__request 以及 qualified project-model
  binding：immutable model identity、request context、prompt identity、
  request recording 和 closure verification。

open_sem_method_session() 通过 Noetrium 的 method endpoint/runtime 边界
打开 SEM session；SemMethodAgentMemoryAdapter 是 cognition 到 SEM 的唯一
memory seam。

## 快速开始

需要 Python 3.11+，并把 Noetrium 和本仓库放入 PYTHONPATH：

~~~bash
export PYTHONPATH=/path/to/agent-research-platform-system:/path/to/agent-research-sem
python -m projects.sem_paper.cli doctor
python -m projects.sem_paper.cli protocol
python -m projects.sem_paper.cli smoke
python -m projects.sem_paper.cli evobench --streams-per-track 2
~~~

真实 Minecraft pilot/matrix 还需要 vanilla server、Noetrium Minecraft
provider、已发布的 qualified model closure、durable model-request evidence、
assignment world reset、verified action receipt 和闭合的 task evidence。否则
只能称为 exploratory/smoke evidence，不能作为 confirmatory SEM claim。

详见 docs/SEM_PROTOCOL.md、docs/SEM_IMPLEMENTATION_ALIGNMENT.md、
docs/NOETRIUM_SEM_INTEGRATION_MATRIX.md 和 docs/SEM_EVO_BENCHMARK.md。
