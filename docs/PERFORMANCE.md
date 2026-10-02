# 性能与经验学习验收

日期：2026-10-02。平台：Windows / Python 3.13.13。只执行离线公开状态及模型选择，没有操作真实游戏。

## 可复核材料与口径

基线为 `dfc5216c07b8699ad4f0c2b3805350cb3c6f57a4`：包含原有战斗、计算器和路线改动，162 项测试、Ruff 通过。模型对照的优化侧对应架构提交 `8795cf7`，随后继续优化序列化、策略适配缓存和存储调度，并修正日志失败收尾；最终离线代码为 `1db5a01`，数据对应 JSON 内的源码指纹。因此模型表不代表最终 Runtime 的端到端性能。

固定集合包含 16 个脱敏公开局面：6 战斗、2 奖励、2 商店、2 地图、2 事件、1 休息、1 选牌。它们来自留出 seed 组，未用于经验提炼。训练文件包含 686 条已核验局部观察，保存可重新核算的资源差值，不发布原始日志、数据库、endpoint 或凭据。

A = 基线提示与人工知识；B = 优化代码与人工知识，关闭学习检索；C = 优化代码与训练集冻结经验。模型 A/B/C 共用优化后的 Provider，以分离提示与检索的影响，不能将表中的差异归因于完整旧/新传输实现。

离线 worker 在隔离进程中载入各版本源代码，执行牌组分析、记忆准备、战斗 guard 核算、提示构造和上下文编译。冷测量清空事实、牌组/策略和检索缓存；热测量每个局面重复 25 次，每份报告 400 个热样本。SQLite worker 的生产接口另测每个局面 5 个热样本，共 80 个；包含线程提交和 compiler 调用。报告未包含游戏执行时间。

原始结果：[offline-1](benchmarks/offline-1.json)、[offline-2](benchmarks/offline-2.json)、[offline-3](benchmarks/offline-3.json)、[模型对照](benchmarks/model.json)、[模型复盘](benchmarks/reflection.json)。每份离线结果记录 source/dataset/config/frozen-memory SHA256；同一内容重建的 SQLite 文件可能因页布局和修订历史而有不同文件指纹。源码指纹包含实际文件换行，跨平台复现时应同时核对 Git 提交与数据指纹。

## 三次重复测量

单位为 ms；前三列为 P50 / P95，最后一列为生产异步接口 P50。

| 次数 | A | B | C | B 含异步存储 |
| --- | --- | --- | --- | --- |
| 1 | 3.243 / 5.869 | 1.078 / 1.857 | 1.395 / 2.966 | 2.313 |
| 2 | 3.306 / 5.368 | 1.144 / 2.104 | 1.253 / 2.646 | 2.254 |
| 3 | 3.491 / 5.619 | 1.015 / 2.098 | 1.218 / 2.298 | 2.359 |

三次独立测量的摘要：离线准备 P50 **3.306 → 1.078 ms（下降 67.4%）**；包含 SQLite worker 调度的 P50 为 **2.313 ms（较基线下降 30.0%）**。重复牌库查询 **546 → 16（下降 97.1%）**；战斗上下文估计 token 中位数 **6648 → 5647（下降 15.1%）**。这些是本地固定数据集结果。

上述摘要取三份报告各自 P50 的中位数，再计算前后比例。每次含异步存储的准备 P50 都降低超过 25%；不以最快的一次充当收益。按六个战斗逐场计算的 token 降幅中位数为 15.15%；直接比较六个场景 token 的中位数，降幅为 15.06%。这些均为模型无关的 UTF-8 字节估计，不是服务商 tokenizer 实测。

| 指标 | A | B | C |
| --- | --- | --- | --- |
| 冷准备 P50，三次中位数 | 15.352 ms | 8.436 ms | 13.100 ms |
| 热准备 P50，三次中位数 | 3.306 ms | 1.078 ms | 1.253 ms |
| 牌库查询次数，每轮完整测量 | 546 | 16 | 16 |
| 所统计连接的 SELECT 次数 | 547 | 450 | 450 |
| 上下文准备事务次数 | 33 | 16 | 16 |

C 的新经验数据库连接查询单独归入检索开销，SELECT 计数表只统计 worker 的记忆与牌库连接；它不宣称包含 C 的全部 SQL。卡牌/牌组/检索缓存命中及容量在原始 JSON 中保留。生产接口跨场景保留牌库缓存，仅发生 5 次牌库查询。

启用经验检索后，C 的热 P50 中位数比 B 多约 0.175 ms；冷检索有额外索引成本。学习的价值应由场景表现另行验证。

1000 条相同大小记录的完整日志写入与排空：三次同步结果为 914.4 / 1013.4 / 1081.0 ms，异步结果为 189.5 / 197.7 / 647.0 ms；中位数下降 80.5%。此项包括排空与句柄关闭，manifest 创建未计入。文件 I/O 波动明显，生产场景吞吐与队列占用还取决于日志速率，不将此比例当成固定收益。

## 真实模型对照：预算内部分完成

保持 `deepseek-v4-flash-0731`、thinking 开启、calculator required、max_completion_tokens=8192 一致。选两个战斗、一个商店、一个地图局面，第一轮 A→B→C，第二轮 C→B→A；规划最多 24 个决策，决策子预算 72 HTTP / 360,000 token，复盘子预算 8 HTTP / 40,000 token。

实际尝试 15 个决策，完成 14 个；获得第一轮的 4 组完整 A/B/C 配对。第二轮完成的两个输出保留在 records 中，未纳入配对统计。最后一次因剩余额度不足以预留完整下一请求而停止。**这不是完成两轮的评测。**

| 组别 | 配对样本数 | 决策延迟中位数 | 输入 token 总数 | 输出 token 总数 | 合法输出 |
| --- | --- | --- | --- | --- | --- |
| A | 4 | 39.63 s | 98308 | 17931 | 4/4 |
| B | 4 | 34.23 s | 69720 | 21181 | 4/4 |
| C | 4 | 43.69 s | 57905 | 15991 | 4/4 |

决策合计 59 HTTP / 345,775 token；复盘 8 HTTP / 25,914 计入预算的 token；总计 **67 HTTP / 371,689 token**。复盘中有一次响应形状错误发生在其 checkpoint 前，usage 未保留，已按 9,000 token 保守计入；后续实现改为请求前写预留、请求后写用量，避免这类账本缺口。

完整配对的 12 个输出全部在当前合法动作集合内；已建模的战斗动作没有选择已知 self_lethal。没有执行动作，因此不能核验实际战斗结果、胜率、跨角色泛化或 long-horizon 收益。B 的样本延迟较低、C 较高，均只是这四个场景的观测，不能据此宣称学习稳定提升决策质量。

模型复盘没有产生通过证据校验的新增经验；当前两条 active 观察来自确定性提炼。三次 thinking 截断被拦截，其他无效 proposal 同样不注入。自动复盘的价值首先是可审计、可拒绝与可恢复；“复盘后更会玩”仍需要更多独立局面对照。

## 质量与发布检查

176 项测试覆盖既有公开事实、未知机制、0 HP、搜索上限、合法动作、pending 对账，以及新增私有记忆隔离、策略所有权/版本、实例与 seed 分组、证据晋升/反例、留出隔离、重复导入、事务回滚、线程归属、日志背压/失败/取消排空、复盘取消恢复和逐 HTTP 预算检查。Ruff 检查与格式检查通过；sdist/wheel 构建及独立环境安装验证知识数据、10 个核验动作和离线 benchmark。

首次 CI 暴露了 Python 3.11 的日志失败竞态：句柄关闭期间新入队的 flush acknowledgement 未被清理。收尾改为关闭句柄后清理队列，并添加受事件门控的确定性回归。本地 3.11/3.13 全量测试均为 176 项通过；最终离线三次测量在修正后重新运行。

Windows/Linux CI 的耗时数值不设通过阈值，避免主机噪声。最终 GitHub CI 状态可从仓库 Actions 查看。

## 复现

```powershell
uv sync --locked
uv run spiremind memory --database runs/demo-memory.sqlite import src/spiremind/knowledge/benchmarks/training_evidence.json
uv run spiremind memory --database runs/demo-memory.sqlite consolidate
New-Item -ItemType Directory -Force runs | Out-Null
git archive --format=zip --output=runs/baseline.zip dfc5216c07b8699ad4f0c2b3805350cb3c6f57a4
Expand-Archive -LiteralPath runs/baseline.zip -DestinationPath runs/baseline
uv run spiremind benchmark --baseline runs/baseline --memory-db runs/demo-memory.sqlite --rounds 25 --output runs/offline.json
```

Linux 用 `mkdir -p runs` 和 `unzip runs/baseline.zip -d runs/baseline` 代替对应 PowerShell 命令。默认不发送 HTTP。

显式模型测试：

```powershell
uv run --env-file .env spiremind --config config.local.toml benchmark --baseline runs/baseline --memory-db runs/demo-memory.sqlite --use-model --output runs/model.json
```

每次命令有自己的子预算，CLI 不会自动合并多次实验的预算。当前模型 benchmark 的 72 请求 / 36 万 token 上限固定在实现中；跨命令总预算需要调用侧根据既有账本传入剩余额度，不能直接重复完整命令并视为预算清零。本轮已累计复盘与对照用量，并停止模型调用。
