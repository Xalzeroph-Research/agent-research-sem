# SEM benchmark 接入与 baseline 决策

## 结论

主实验采用 MineEvolve 70-task suite 作为任务来源，选择 12 个能映射到
Noetrium Mineflayer 高层动作接口的任务作为当前 v2 executable subset。
这保留了公开任务的技术树、资源、导航、战斗和建造覆盖，只做最小的
success spec 与动作接口归一化。

主实验不是把外部 simulator 代码塞进 Noetrium。Noetrium 只提供通用的
environment/provider、action/effect、evidence、assignment isolation 和
study-plan contract；SEM 负责记忆方法、Minecraft task manifest、planner
适配、评分和论文实验协议。

## 同栈 baseline 与外部 SOTA reference

| 层次 | 系统 | 实验作用 | 是否进入 paired 主表 |
|---|---|---|---|
| matched lower bound | no_memory | 无长期记忆 | 是 |
| matched memory baseline | flat_episodic | 无类型关系的 episodic memory | 是 |
| matched structural baseline | fixed_typed | 固定 typed graph | 是 |
| proposed method | sem | 语义责任拓扑自进化 | 是 |
| external system reference | MineEvolve | execution-feedback self-evolution | 否，除非同接口重跑 |
| external system reference | Voyager | open-ended skill acquisition | 否，除非同接口重跑 |
| external system reference | JARVIS-1 | multimodal long-horizon Minecraft | 否，除非同接口重跑 |

原因是外部系统的 model、executor、Minecraft 版本、任务采样和成功判定
不同。直接把它们的公开成绩和 SEM 数字放在同一列会混淆系统级比较与
记忆机制的因果比较。catalog 保留来源、revision、scope、role 和
runtime_status=reference_only，后续若实现统一 adapter 才升级为可比结果。
## 外部 memory benchmark

MemoryAgentBench、MemoryArena、LongMemEval 和 BEAM 作为通用 memory
benchmark 的外部定位与可选复用来源。当前 JsonTaskBenchmarkAdapter 只
导入冻结的 task metadata 和 content digest，不执行外部 runtime，也不
改变 Noetrium environment ownership。它们的用途分别是 incremental
multi-turn memory、multi-session agent-environment loop、long-term
conversation regression 和 long-context stress。

因此，外部 benchmark 的 metadata-prepared 输出不是实验结果。若要加入
论文主结果，必须同时固定数据版本、任务顺序、模型、context budget、
success rule、assignment split 和 raw evidence schema。
## 冻结接口

真实 Minecraft task 的调用链为：

    task manifest -> SEM recall -> model planner -> Noetrium Mineflayer bridge
    -> verified action/effect receipt -> SEM task completion -> evidence/evolution

planner 只输出白名单动作；它不能声明任务成功，也不能直接写 memory。
bridge 只返回 grounded outcome、verified 标志和 self snapshot。SEM 只在
task completion 后处理 evidence、检测 structural demand 并更新自己的
semantic topology。这样 baseline 只替换 memory treatment，不替换环境
执行器或 success evaluator。

真实运行入口：

    python -m projects.sem_paper.cli real-pilot
    python -m projects.sem_paper.cli real --repetitions 3

必须配置 assignment-level fresh world reset。没有 reset 的运行可以用于
工程调试，但只能标记 exploratory_real_matrix。
