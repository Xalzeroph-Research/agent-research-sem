# Noetrium / SEM 项目交接记录

更新时间：2026-09-09；服务器时区：Asia/Shanghai；主机：ubuntu-desktop-2204。

本文件记录 Linux node-2、Windows 本地镜像、GitHub、Noetrium、SEM、Docker、Qwen3-8B、Minecraft 和已有实验状态。它是运行交接记录，不替代最新设计规范。

## 1. 目标与硬约束

- 当前 SEM 使用 Qwen3-8B，暂不启用多模态。
- SEM 实验固定使用 Noetrium commit 255ca63e 的独立 frozen worktree；不要切到 Noetrium main 或未来版本。
- Noetrium 可继续开发，但固定 SEM 实验必须保持同一个 Noetrium worktree、Docker image、model qualification closure 和 protocol。
- 最高规范是 2026-09-07/08 的 docs/SEM_IMPLEMENTATION_ALIGNMENT.md；其次是 docs/NOETRIUM_SEM_INTEGRATION_MATRIX.md；SEM_PROTOCOL.md 服从前两者。旧 SEM v0.29 只作历史参考，不能作为当前依据。
- 下游实现前必须先查 Noetrium public facade、public contract 和自动生成 interface schema。已有公开能力时不能猜接口、复制私有逻辑或 import 私有模块；若能力缺失先修 Noetrium 上游。
- 修改、测试和 Linux commit 先在 node-2 完成；最后才用 Windows Portable Git + bundled SSH 对齐和 push。不要在中途由 Windows 覆盖 Linux。
- 文档不包含 API key、SSH 私钥、密码或 token。

## 2. Linux node-2 目录

服务器 SSH alias：sem-node-2；服务器项目根：/data/hdd3/agent-research-runtime。

| 路径 | 用途 | 状态/注意 |
|---|---|---|
| /data/hdd3/agent-research-runtime/agent-research-platform-system | Noetrium canonical 主仓库 | main，HEAD 154c7891；有未跟踪 nohup.out，保留 |
| /data/hdd3/agent-research-runtime/noetrium-sem-pinned-255ca63e | SEM 实验的冻结 Noetrium | detached HEAD 255ca63e；运行 SEM 必须挂载它 |
| /data/hdd3/agent-research-runtime/noetrium-dev | 独立 Noetrium dev worktree | branch noetrium-dev，当前 255ca63e；不用于当前 SEM 矩阵 |
| /data/hdd3/agent-research-runtime/agent-research-sem | SEM canonical 仓库 | main，HEAD 438f8534；未跟踪 .sem-sync/、n' LAST_FILES、results/ 必须保留 |
| /data/hdd3/agent-research-runtime/noetrium | 历史/运行产物 | 不要当 SEM 源码挂载点 |
| /data/hdd3/agent-research-runtime/sem | 历史/运行产物 | 不要替代 canonical SEM |
| /data/hdd3/agent-research-runtime/sem/releases | SEM 历史发布产物 | 保留 |
| /data/hdd3/agent-research-runtime/noe-validation | Noetrium 验证产物 | 只读检查 |
| /data/hdd3/agent-research-runtime/validation | 验证结果 | 含 sem-method-5515bb0f-noetrium、sem-method-5515bb0f-sem |
| /data/hdd3/agent-research-runtime/runs | 运行产物 | 保留 |
| /data/hdd3/agent-research-runtime/image-transfer | 镜像传输/中间产物 | 保留 |
| /data/hdd3/agent-research-runtime/sem-results | SEM pilot、矩阵日志和结果 | 每次新实验使用新目录，不覆盖旧目录 |
| /data/hdd3/agent-research-runtime/sem-action-recovery | 较早 action recovery | 历史证据，保留 |
| /data/hdd3/agent-research-runtime/sem-real-state | 较早真实运行状态 | 历史产物，保留 |
| /data/hdd3/agent-research-runtime/sem-real-state-node2 | 较早 node-2 状态 | 历史产物，保留 |
| /data/hdd3/agent-research-runtime/sem-evo-state-node2 | SEM evolution 状态 | 保留 |

## 3. Minecraft 目录

| 路径 | 用途 |
|---|---|
| /data/hdd3/agent-research-runtime/minecraft-data/vanilla-1.21.1 | server.jar、active world 和 server.log |
| /data/hdd3/agent-research-runtime/minecraft-data/vanilla-1.21.1/sem-minecraft-primary-v2 | active world；assignment reset 时会先归档 |
| /data/hdd3/agent-research-runtime/minecraft-data/sem-minecraft-primary-v2-template | fresh-world template |
| /data/hdd3/agent-research-runtime/minecraft-assignment-archives | 每次 assignment 的旧 world archive；不要清理 |
| /data/hdd3/agent-research-runtime/minecraft-primary-v2.pid | active Java pidfile |
| /data/hdd3/agent-research-runtime/agent-research-sem/reset_sem_v2.sh | reset、归档、复制 template、启动、readiness |
| /data/hdd3/agent-research-runtime/minecraft-data/bridge-state | bridge 状态 |

## 4. Windows 和 GitHub

- Windows 根目录：E:\Agent-Research-Workspace
- SEM 镜像：E:\Agent-Research-Workspace\projects\active\agent-research-sem
- Portable Git：E:\Agent-Research-Workspace\shared\runtimes\git-2.55.0.3\bin\git.exe
- bundled SSH：E:\Agent-Research-Workspace\shared\runtimes\git-2.55.0.3\usr\bin\ssh.exe
- SSH config：E:\Agent-Research-Workspace\shared\config\ssh\config
- Remote Desktop device：869b0d28-acef-4a9b-a946-581d2566feee
- Noetrium remote：https://github.com/Xalzeroph/Noetrium.git
- SEM remote：git@github.com:Xalzeroph-Research/agent-research-sem.git

Linux Noetrium HEAD 是 154c7891，GitHub 主分支已核验到 154c789145e...。Linux SEM HEAD 是 438f8534，GitHub 主分支已核验到 438f8534...。Noetrium 服务器上的 origin/main ahead 2 是 HTTPS tracking 信息滞后，不能据此重复提交。

Linux commit 完成后，Windows 用 bundled Git 对齐并 push：

    cmd.exe /c "set GIT_SSH_COMMAND=E:/Agent-Research-Workspace/shared/runtimes/git-2.55.0.3/usr/bin/ssh.exe -F E:/Agent-Research-Workspace/shared/config/ssh/config && cd /d E:/Agent-Research-Workspace/projects/active/agent-research-sem && E:/Agent-Research-Workspace/shared/runtimes/git-2.55.0.3/bin/git.exe fetch sem-node-2:/data/hdd3/agent-research-runtime/agent-research-sem main:refs/remotes/server/main && E:/Agent-Research-Workspace/shared/runtimes/git-2.55.0.3/bin/git.exe merge --ff-only server/main && E:/Agent-Research-Workspace/shared/runtimes/git-2.55.0.3/bin/git.exe push git@github.com:Xalzeroph-Research/agent-research-sem.git main:main"

push 后用 git ls-remote 核验 SHA。不要把 $git 等 PowerShell 变量写进 process command，Windows process layer 会吞掉 $。

## 5. 版本和当前代码

### Noetrium

- canonical path：agent-research-platform-system
- branch/HEAD：main / 154c7891
- 关键功能提交：2ff6bdb9 feat(platform): publish generated downstream interface schemas，随后 merge 为 154c7891
- 新增 scripts/generate_interface_schemas.py，产出 noetrium/contracts/interface_schema.json
- scripts/update_generated_docs.py --check 自动重新生成并校验 schema
- discovery public API：load_downstream_interface_schema()、find_downstream_symbol_schema(...)
- 当前生成规模约 172 systems、500 API modules、3659 public symbols

### SEM

- canonical path：agent-research-sem
- branch/HEAD：main / 438f8534
- 关键提交：720a662f（upstream canonical Minecraft action facade）、db5016ea（planner 从 upstream action catalog 派生）、9429a204/2b4b89f4（planner bounded retry）、fd9f9b15/438f8534（reset readiness 改为 bash /dev/tcp，脚本 executable）
- 当前未跟踪内容 .sem-sync/、n' LAST_FILES、results/ 不属于交接文档，必须不动。

## 6. 最新设计边界

Noetrium 负责 generic contracts、provider composition、lifecycle、identity、durable state、effect certainty、checkpoint/recovery、runtime supervision、evidence transport。SEM 负责 scientific memory semantics、demand detection、semantic topology、Transform/Meta proposals、candidate validation、historical backfill、forward-only adoption。

当前 treatment：no_memory、flat_episodic、fixed_typed、sem；旧 fixed_memory 无效。正式矩阵为 4 variants × 3 repetitions = 12 assignments，每个 assignment 12 tasks，共 144 task episodes。

通用 multimodal observation/serving upstream 已有 noetrium.platform.MultimodalAgentObservationPort、invoke_multimodal_model 和 model multimodal contracts；当前 SEM 不启用 live multimodal variant。未来 part source、codec 和 modality set 必须 provider-owned、可扩展，不能硬编码一种 VLM 格式。

当前迁移状态：method/session/outcome、memory adapter、typed graph、study/variant/run planning、qualified model client、typed Minecraft action/observation/effect、artifact finalization/verification 已接入。后续迁移顺序仍是 run/checkpoint composition、typed environment/effect/recovery、typed model serving、persistent server runtime、完整 evidence/observability/matched matrix。

## 7. 测试和自动 schema

    cd /data/hdd3/agent-research-runtime/agent-research-platform-system
    python scripts/update_generated_docs.py --check
    python -m pytest -q tests/test_downstream_contracts.py tests/test_interface_schema_generation.py tests/test_minecraft_environment_v1.py tests/test_minecraft_action_codecs_v1.py tests/test_runtime_pge_public_contract_v1.py
    # 上次结果：125 passed in 1.79s

    cd /data/hdd3/agent-research-runtime/agent-research-sem
    PYTHONPATH=/data/hdd3/agent-research-runtime/noetrium-sem-pinned-255ca63e:/data/hdd3/agent-research-runtime/agent-research-sem python -m pytest -q
    # 上次结果：33 passed in 1.59s

容器 image 内没有 pytest；不要用 /opt/venv/bin/python -m pytest 作为容器测试假设。

## 8. Docker 运行环境

固定 image：noetrium/minecraft:sem-final；当前 image id：sha256:06c2013353d8f3793b3d463816279c2016a5b5e4ce50103ec32d0a4232e836b0。

必需环境：

    NODE_PATH=/opt/noetrium/noetrium_platform/capabilities/environment/minecraft/providers/assets/mineflayer_bridge/node_modules
    PYTHONPATH=/workspace/noe:/workspace/sem

标准挂载：

    -v /data/hdd3/agent-research-runtime/agent-research-sem:/workspace/sem:ro
    -v /data/hdd3/agent-research-runtime/noetrium-sem-pinned-255ca63e:/workspace/noe:ro
    -v /data/hdd3/agent-research-runtime/qualifications-vN:/workspace/qual-vN:ro
    -v /data/hdd3/agent-research-runtime:/data/hdd3/agent-research-runtime

正式 reset-in-container 需要 --privileged --pid=host --network host；但容器退出后容器内启动的 Java 可能一起退出。若只想在 host 留下 Minecraft，使用 host reset supervisor。

## 9. Qwen3-8B 和 qualification

当前核验 Qwen 正常运行：PID 100863，endpoint http://127.0.0.1:8001，model id qwen，model root /data/hdd2/models/Qwen3-8B，max model length 32768，process start marker proc-starttime:184446236，vLLM 使用 bfloat16、tensor parallel 2、GPU memory utilization 0.85、enforce eager。不要 kill/restart Qwen。

v6 closure：/data/hdd3/agent-research-runtime/qualifications-v6/qwen3-8b-sem-pinned-v6.json；closure digest aaa9a42d3cd1d3016dbb343a3e0f71a8635daca1a6994c8ef4931523850cbe3b；deployment qwen3-8b-planner-tp2；qualified role planner。

真实 binding diagnostic 已确认 v6 过期：receipt valid_until=1788917616.975022，当前时间已超过它，因此 Noetrium 返回 qualified model binding unavailable: ValueError 是正确的 qualification 拒绝，不是 Qwen API 故障。继续实验前必须在 frozen Noetrium + 当前 SEM planner prompt digest 下重新 formal qualify/live canary，生成新 closure（例如 v7）；禁止手工改 JSON 绕过 Noetrium。

## 10. Minecraft 当前状态和恢复

当前检查时 pidfile 内容为 1240125，对应 Java 不存在，25565/25575 没有监听。这是 confirmatory v3 Docker 退出后的状态；Qwen 和旧容器仍在。

宿主机恢复 fresh world：

    bash /data/hdd3/agent-research-runtime/agent-research-sem/reset_sem_v2.sh handoff-recovery

脚本会停止旧 Java、归档 active world 到 minecraft-assignment-archives、从 template 复制 fresh world、启动 java -Xms512M -Xmx2G -jar server.jar nogui，并通过 bash /dev/tcp/127.0.0.1/25565 做 readiness。不要在旧 Java 未确认退出时启动第二个 server。

只读检查：

    p=$(cat /data/hdd3/agent-research-runtime/minecraft-primary-v2.pid 2>/dev/null)
    ps -p "$p" -o pid=,ppid=,stat=,etime=,cmd=
    ss -ltnp | rg ':25565|:25575' || true
    tail -80 /data/hdd3/agent-research-runtime/minecraft-data/vanilla-1.21.1/server.log

## 11. Docker 容器当前保护清单

上次核验仍在运行的容器：

| id | name | image | 规则 |
|---|---|---|---|
| 37dba89eafe3 | frosty_beaver | noetrium/minecraft:sem-final | 旧诊断，保留 |
| e8d59ac87a45 | exciting_poincare | noetrium/minecraft:sem-final | 旧诊断，保留 |
| b51de62bfdb1 | infallible_mclean | noetrium/minecraft:sem-final | 旧诊断，保留 |
| 1691a955bcbc | api-relay-test | python:3.12-slim | 无关服务，不动 |
| 7c827c4acf39 | confident_bose | bigcodebench/bigcodebench-evaluate:latest | 无关服务，不动 |
| 6c296a1ba117 | serene_ganguly | python:3.12-slim | 无关服务，不动 |

正式矩阵 v1–v3 用 --rm，已经退出并删除。任何清理动作都需要明确授权。

## 12. 已有 pilot 和矩阵尝试

| 目录 | 结论 |
|---|---|
| qwen3-8b-docker-pilot-v9 | Qwen 输出 goto.target_position，违反 upstream action contract；随后 planner 改为注入 upstream catalog |
| qwen3-8b-docker-pilot-v10 | 使用过期 v4 closure/model binding |
| qwen3-8b-docker-pilot-v11 | Qwen 输出 observe_entities.limit=256，upstream 范围 [1,100]；随后加入 bounded retry |
| qwen3-8b-docker-pilot-v12 | 完成 exploratory pilot，但 MC_REQUIRE_WORLD_RESET=0，因此 pilot_not_claim_ready |
| qwen3-8b-confirmatory-v1-20260909 | reset 时旧 Java 占端口，普通容器无权限 kill host PID |
| qwen3-8b-confirmatory-v2-20260909 | --privileged --pid=host 可 reset，但 image 没有 ss；随后 readiness 改为 /dev/tcp |
| qwen3-8b-confirmatory-v3-20260909 | fresh reset/readiness 成功，但第一 assignment 前因 v6 closure 过期而 model binding 拒绝 |

v12：19 steps、10 verified actions、0 rejected、12 memory queries、success rate 0.5、utility mean 0.375、duration 123.041s；12 tasks 中 6 success、6 failure。成功为 logs/cobblestone/pickaxe/furnace/ore/ingot；失败包括 bucket、navigation、combat、building、iron pickaxe、shield。不能把 v12 当论文结论。

矩阵日志：

    /data/hdd3/agent-research-runtime/sem-results/qwen3-8b-confirmatory-v1-20260909/matrix.log
    /data/hdd3/agent-research-runtime/sem-results/qwen3-8b-confirmatory-v2-20260909/matrix.log
    /data/hdd3/agent-research-runtime/sem-results/qwen3-8b-confirmatory-v3-20260909/matrix.log

## 13. 继续实验的顺序

1. 只读检查 Qwen PID、/v1/models、start marker、argv identity；不重启 Qwen。
2. 以 frozen Noetrium 255ca63e + SEM 438f8534 做新的 formal qualification/live canary，得到新 closure。
3. 在同一挂载和 PYTHONPATH=/workspace/noe:/workspace/sem 下运行 b.diagnose(planner_model_requirement())，必须无 diagnostics。
4. 使用新结果目录跑 MC_REQUIRE_WORLD_RESET=1 的真实 smoke/pilot，确认 fresh-world reset、action recovery、effect receipt、model request、artifact/evidence closure。
5. 通过后再跑完整矩阵：python -m projects.sem_paper.cli real --repetitions 3。
6. 矩阵结束先运行 analyze，检查 matched repetition、effect certainty、memory evidence 和 audit evidence。
7. 只有冻结 protocol、真实 model planner、fresh-world reset、verified effect receipts、memory evidence closure 和完整 matched matrix 都满足，才可 claim-ready。
8. Linux 修改/测试/commit 全部完成后，最后 Windows fetch、ff-only merge、push、git ls-remote 核验。

## 14. 常见运行命令

    cd /data/hdd3/agent-research-runtime/agent-research-sem
    python -m projects.sem_paper.cli doctor
    python -m projects.sem_paper.cli protocol
    python -m projects.sem_paper.cli smoke
    python -m projects.sem_paper.cli evobench
    python -m projects.sem_paper.cli benchmark-catalog
    python -m projects.sem_paper.cli external-prepare
    python -m projects.sem_paper.cli real-pilot --planner-mode model
    python -m projects.sem_paper.cli real --repetitions 3
    python -m projects.sem_paper.cli analyze

正式 Docker 必须设置 SEM_PLANNER_MODE=model、SEM_REPETITIONS=3、SEM_MODEL_QUALIFIED_CLOSURE=/workspace/qual-vN/qwen3-8b-sem-pinned-vN.json、SEM_MODEL_REQUEST_ROOT=/workspace/results/model-requests、SEM_RESULTS_DIR=/workspace/results、MC_HOST=127.0.0.1、MC_PORT=25565、MC_VERSION=1.21.1、MC_REQUIRE_WORLD_RESET=1、MC_ACTION_RECOVERY_ROOT=/workspace/results/action-recovery、MC_CONNECT_TIMEOUT_S=90、MC_COMMAND_TIMEOUT_S=90，以及 MC_ASSIGNMENT_RESET_COMMAND='bash /data/hdd3/agent-research-runtime/agent-research-sem/reset_sem_v2.sh {assignment_id}'。

## 15. 交接第一轮检查清单

    date -Is; hostname
    git -C /data/hdd3/agent-research-runtime/agent-research-platform-system status --short --branch
    git -C /data/hdd3/agent-research-runtime/noetrium-sem-pinned-255ca63e rev-parse HEAD
    git -C /data/hdd3/agent-research-runtime/agent-research-sem status --short --branch
    git -C /data/hdd3/agent-research-runtime/agent-research-sem rev-parse HEAD
    pgrep -af 'vllm.entrypoints.openai.api_server'
    curl -sS http://127.0.0.1:8001/v1/models
    docker ps --format '{{.ID}} {{.Names}} {{.Image}} {{.Status}}'
    p=$(cat /data/hdd3/agent-research-runtime/minecraft-primary-v2.pid 2>/dev/null); ps -p "$p" -o pid=,stat=,cmd=
    ss -ltnp | rg ':25565|:25575' || true

交接时的核心判断：当前公开接口迁移代码和测试已完成；未完成的是新的 Qwen qualification、可重复 fresh-world confirmatory run 和完整科学矩阵。v12 pilot 与 v1–v3 失败日志都不是正式实验结论。
