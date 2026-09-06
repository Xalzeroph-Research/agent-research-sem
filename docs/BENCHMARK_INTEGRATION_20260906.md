# SEM benchmark 接入决策

## 结论

SEM 的第一方主 benchmark 是 SEM-EvoBench v1，而不是把外部 benchmark
搬进 Noetrium 的 environment。它负责验证 memory -> action -> outcome ->
validation -> evolution 的完整闭环。

外部对照分层接入：

| benchmark | 用途 | SEM 归属 | 当前状态 |
|---|---|---|---|
| MemoryArena | 多 session、action/feedback agent loop | external comparison | metadata only |
| MemoryAgentBench | incremental multi-turn memory 能力 | memory-only comparison | metadata only |
| LongMemEval | 长期会话回归与 temporal/update/abstention | regression | metadata only |
| BEAM | 超长上下文容量压力 | stress test | metadata only |
| MineDojo | Minecraft programmatic task source | optional task source | metadata only |

外部 benchmark 不改变 Noetrium 的 environment ownership。MineDojo 不是
memory benchmark；它只能提供冻结后的任务及 success spec。

## 接口和冻结规则

JsonTaskBenchmarkAdapter 只导入本地冻结的 task metadata，输出 Noetrium
BenchmarkTaskSet。prepare_external_benchmark 会保留 benchmark id、revision、
source digest、task content digest 和 execution owner。它不执行 action、
不写 memory，也不接受 provider 的隐式成功。

外部来源：

- MemoryArena: https://arxiv.org/abs/2602.16313
- MemoryAgentBench: https://openreview.net/forum?id=DT7JyQC3MR
- LongMemEval: https://arxiv.org/abs/2410.10813
- BEAM: https://openreview.net/forum?id=y59hf5lrMn
- MineDojo: https://github.com/MineDojo/MineDojo

## 暂缓事项

当前镜像没有把外部 simulator/runtime 当作环境依赖安装。只有在数据版本、
运行时、任务 success spec、provider mapping、assignment reset、effect
receipt 和 evidence closure 全部冻结后，才允许外部 full-N 执行。

当前 CLI 的 benchmark-catalog 和 external-prepare 是可审计的元数据入口；
输出状态仍是 metadata_only / metadata_prepared，不是实验结论。
