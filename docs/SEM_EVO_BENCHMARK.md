# SEM benchmark 设计与评分

## 1. 目标

SEM benchmark 用一个可重复的 memory-agent-environment loop 测量：
经历是否被检索、经验是否迁移到后续任务、失败后是否形成结构性恢复、
以及新世界条件下旧记忆是否会产生负迁移。它不是单纯的 memory dump
测试，也不是只看一次任务成功率。

可执行实现为 projects/sem_paper/benchmarks/evo_protocol.py。benchmark
revision v2 固定四个 track，每个 track 是六个有序 episode：

| episode | 作用 |
|---|---|
| discovery | 写入一个带 key 的新经历 |
| reuse | 查询并复用该 key |
| recovery | 注入一次可审计失败 |
| adaptation | 观察失败后的下一次适应 |
| discovery | 写入第二个 key |
| heldout_transfer | 在后续 episode 查询第二个 key |

## 2. 四个 track

- memory_retrieval：测长期记忆能否返回正确经历；
- experience_transfer：测一个 episode 的信息能否支持后续 reuse；
- closed_loop_recovery：测失败反馈是否进入 outcome，并触发下一轮恢复；
- world_change：测旧经验存在时，新的上下文/证据是否仍能被正确区分。

每个 stream 有稳定 stream id、seed、episode digest；同一 stream 被
所有 treatment 成对运行。默认四个 track、每 track 两个 stream，共
32 个 treatment-stream runs。stream digest 与 score trace 都写入结果，
便于重放和审计。

## 3. 评分

每个 treatment-stream 产生以下分数：

| 指标 | 含义 |
|---|---|
| experience_gain_auc | 六个 episode 的成功曲线相对 fixed_typed 的配对差 |
| final_transfer_gain | heldout_transfer 相对 fixed_typed 的配对差 |
| adaptation_recovery | recovery 后首次恢复成功的 episode 距离 |
| negative_transfer_rate | 非 discovery episode 中失败的比例 |
| memory_cost | 记忆 entry 数 |
| verified_effect_rate | 有 verified outcome 的 episode 比例 |
| candidate/adopted/rejected | SEM 候选生命周期 |
| generation_count | 结构图 generation 增量 |

这里的 AUC 是六个固定位置的离散均值，不是把 task 行当作独立
观测。fixed_typed 的配对差定义为 0；其它 treatment 的 gain 使用同一
stream 的 fixed_typed score 做减法。
## 4. 与 Minecraft 主实验的关系

EvoBench 是便宜、确定性的 method-level diagnostic suite，用于检验
SEM 的记忆演化机制和评分管线。Minecraft 主实验则使用
experiments/manifests/sem_minecraft_tasks_v2.json，把相同四个 treatment
接到真实 Noetrium Mineflayer bridge 和真实 model planner。

两者不能混合统计，也不能把 EvoBench 的结果当作 Minecraft 结果。
Minecraft 结果以 grounded inventory、movement、combat、placement 等
环境 effect receipt 为准；EvoBench 只验证 memory/evolution 的因果
诊断。

## 5. 命令

    python -m projects.sem_paper.cli evobench --streams-per-track 2
    python -m projects.sem_paper.cli evobench --track experience_transfer

EvoBench 输出的 claim_status 是 diagnostic_only。论文中可将它作为
机制验证和 sanity check，主结论必须来自真实 Minecraft assignment
层面的 paired results。
