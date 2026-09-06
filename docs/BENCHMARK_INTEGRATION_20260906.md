# SEM benchmark 接入决策

## 结论

第一阶段接入 MineDojo 的 programmatic task metadata，并保留 Noetrium Minecraft provider 作为唯一执行与 effect-evidence 权威；同时接入 MemoryAgentBench 作为 SEM memory-only track。benchmark 不放进 `environment` ownership。

## 选择依据

- MineDojo 当前仓库列出 3142 个任务，分为 Programmatic、Creative、Playthrough；programmatic 任务可由模拟器状态自动验收，适合映射到 SEM 的 task/effect/evidence 协议。
- MemoryAgentBench 面向 incremental multi-turn memory，覆盖 retrieval、test-time learning、long-range understanding、selective forgetting，适合直接检验 SEM 的记忆层。
- EMemBench 生成基于 agent trajectory 的问题并提供程序化 ground truth，适合作为第二阶段 episodic-memory track；当前先不把 Jericho/Crafter runtime 混入 Minecraft environment。
- AgentBench 是跨八类环境的总 benchmark，适合作为外部对照，不作为 SEM environment 的所有权来源。

## 接口

`JsonTaskBenchmarkAdapter` 只导入冻结的 task metadata，输出 Noetrium `BenchmarkTaskSet`。它不执行 action、不写 memory、不接受 provider 的隐式成功；执行仍走 SEM method → Noetrium environment port → effect receipt → scientific evidence。

外部任务导出为：

```json
{"tasks":[{"task_id":"...","goal":"...","family":"programmatic","success_spec":{}}]}
```

导入前固定 source digest；运行记录必须带 benchmark id、revision、source digest、task content digest。

## 暂缓

MineDojo 的完整 simulator runtime 不直接装入当前镜像：它与现有 Mineflayer/Noetrium provider 的 runtime/世界生命周期不同。先接 metadata + programmatic success specs，再做 provider-level execution adapter；在 assignment world cut、effect receipt 和 evidence closure 全部通过前，不跑 external full-N。
