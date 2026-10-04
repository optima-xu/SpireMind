# Agent 鲁棒性与经验学习改造

日期：2026-10-04。保留 Coordinator、Combat / Run / Map / Event 专业 Agent 和独立 Reflection 的分工。本轮使用历史公开状态、固定测试和离线性能对照，没有请求模型或操作游戏。改造前的问题证据见[质量复盘](AGENT_QUALITY_REVIEW.md)。

## 执行与模型边界

- **恢复按阶段计时**：观察、执行、核验分别计算 180 秒恢复预算，失败 I/O 和退避计入对应阶段。健康模型请求和本地准备不占用桥接窗口，观察成功也不会掩盖持续回执错误。模型故障仍使用独立恢复窗口，失败时不发送回退动作。
- **先完成旧动作对账**：动作回执已返回、后续读取失败时，Runtime 保留该转换。下一步先观察和核验旧回执，完成之前不请求新决策或再次发送动作。成功对账写入独立日志，replay 与历史导入合并核验结果。
- **数值绑定当前动作**：`calculate(action_ids=[...])` 返回绑定 decision/revision 的实时 Block、owner damage、目标预览等事实。模型最终 JSON 的 `forecast` 必须与选定动作支持的字段一致；不一致复用已有计算器结果修复一次，仍错误则拒绝。未知机制只给公开预览，不能推断精确 HP 结果。自由文本理由未作语义验证。
- **可观察状态与用量**：`status` 提供当前阶段、开始时间和恢复预算。服务端 reported usage 与保守预算估算分别保存；明确的 403/429 等拒绝不虚构 token 消耗，传输中断、取消和缺少 usage 的未知情况仍预留保守预算。
- **Windows 文件锁恢复**：控制文件和普通 trace 的原子替换对瞬时 `PermissionError` 做有界退避；持续失败继续传播。关键 pending 仍在请求发送前持久化，不能通过重发游戏动作处理本地文件错误。

主要实现：`runtime/agent.py`、`runtime/{control,trace,async_trace}.py`、`core/files.py`、`context/action_facts.py`、`providers/{calculator,openai}.py`。

## 战斗判断

在 v0.111.x 支持范围内，Body Slam 会在先获得格挡后重新计算伤害；计算前必须用当前预览校验 Block / Strength / Weak 公式。Plating 只计入回合结束时的格挡，不提前增加 Body Slam 伤害。Pyre 的本回合能量以公开 energy 为准，不再次叠加。涉及未知版本、反应能力或不确定舍入时放弃精确组合证明。

免费、未污染的 Rage 在当前仍有可支付攻击、需要额外格挡且没有出牌上限或未知反应能力时，可以先于攻击；已证明斩杀优先级更高。该局部顺序检查可以在 Surrounded / Unmovable 的全局模拟不完整时成立，但不声称精确朝向、首次格挡次数或整回合生存结果。

公开回归文件包含实际 revisions 36、37、200、202、203、209、217，删除个人路径、endpoint、原 run/decision ID 和隐藏牌堆信息。例如目标预览 19.5 会取整为 19，双重打击目标单段 22.5 会取整为 22；实时格挡已经包含加成，不再加一次 Dexterity。revision 209 的规则先选择免费 Rage。固定状态验证数值归属与合法选择，不执行这些动作。

主要实现：`strategies/tactics/{effects,assessment,search,setup}.py`、`strategies/combat.py`。

## 经验学习接入运行

启动默认在 SQLite 所属线程离线导入变化的历史；指纹覆盖数据与源码，未变化时复用。缺少 summary 的中断 trace 也纳入，核验依赖实际前后公开状态与回执，未知保持未知。未来已核验动作继续写入相同 Episode / Reflection 流程；战斗内选牌不触发虚假的战斗结束。

FTS5/BM25 使用包括当前敌人 ID 的公开符号取 32 个候选，再按当前合法动作、手牌、玩家能力和 HP 排序。最多两条 Episode、三条 active Skill、600 个估计 token；编译器逐条优先容纳经验。检索缓存同时覆盖当前能量、HP 区间和敌人 ID，证据或经验修订后失效。

新增 `rage_before_attack` 条件战术：完整公开前后状态重新证明免费 Rage 的能量、HP 和能力变化，一个训练 seed 形成 candidate，三个独立训练 seed 才激活。使用前重查当前状态；已验证训练反例立即停用，并阻止对应的强制牌序和精确搜索。测试覆盖激活后实际影响 Combat 决策及反例停用。模型自由文本不能直接变成执行规则。

本机维护锁内先备份数据库，再导入历史，实测结果：

| 项目 | 结果 |
| --- | --- |
| 历史 trace | 47，其中 35 缺少正常结束总结 |
| 独立 seed / 训练 / 留出 | 13 / 9 / 4 |
| 本次新增 Episode | 3,759 |
| 合并后 Episode / 训练 / 留出 | 4,257 / 2,058 / 2,199 |
| 已激活数值观察 | 2 |
| 已激活条件战术 | 0 |
| 重复 bootstrap | 命中缓存，无重复导入 |

现有 65 条已核验 Rage 证据全部属于留出 seed，没有用来激活战术。持久化分组也约束后续在线 Episode；重新导入不会搬动原 seed。实际两条 active 是 Block +5 和 deck count +1 的条件观察。该结果证明学习路径接入；战术实战收益仍需新训练 seed 和独立评测，不能以测试构造的三个 seed 充当实战证据。详细设计见[分层记忆](MULTI_AGENT_MEMORY.md)。

## 三次离线性能对照

A 为改造前 Git 提交 `8c0f2ae416791543438fee705c52d5d2725b3da9`，已经包含缓存与异步架构；B 为本轮源码提交 `376b7f4`。固定 16 个公开留出状态：6 战斗、2 奖励、2 商店、2 地图、2 事件、1 休息、1 选牌。不读取实机学习库，不调用 HTTP；每次每状态 30 个热样本，共 480 个。生产异步接口另测 80 个样本。冷缓存清空事实、牌组、检索和 progress 投影缓存。

原始报告：[第 1 次](benchmarks/robustness-offline-1.json)、[第 2 次](benchmarks/robustness-offline-2.json)、[第 3 次](benchmarks/robustness-offline-3.json)。Windows / Python 3.13.13；每份记录 source / dataset / config SHA256。源码指纹包含文件换行，复现同时核对 Git 版本。下面耗时单位为 ms，P50 / P95 不混合成端到端模型耗时。

| 次数 | A 热 P50 / P95 | B 热 P50 / P95 | A 冷 P50 / P95 | B 冷 P50 / P95 | B 含异步存储热 P50 |
| --- | --- | --- | --- | --- | --- |
| 1 | 1.059 / 2.105 | 1.086 / 1.962 | 6.330 / 10.078 | 6.268 / 8.365 | 1.937 |
| 2 | 1.064 / 1.964 | 1.326 / 2.557 | 6.765 / 30.597 | 7.816 / 43.650 | 2.637 |
| 3 | 1.210 / 2.133 | 1.233 / 2.191 | 7.470 / 10.910 | 8.723 / 11.008 | 2.566 |

取三次 P50 的中位数，A **1.064**、B **1.233 ms**，B 增加约 15.8%，没有稳定本地加速。每份 A/B 的牌库查询均为 **16**，SELECT 为 **530**、准备事务 **16**，没有新增查询减少。原先的 25% 本地耗时与 80% 查询减少目标针对更早的架构基线；本轮相对已优化版本没有再达成这些目标，JSON 如实保留 `targets_passed=false`。

六个战斗的上下文估计 token 中位数 **5,647 → 4,272，减少 24.35%**，三次一致；逐场相对降幅的中位数为 **22.73%**，对应 JSON 的 `combat_context_median_fraction`。精简重复 exporter 元信息、说明与已存在的数值，保留实时未知机制、合法动作和安全结论，并增加绑定的预测事实。估算采用 UTF-8 字节口径，不能视为服务商实际计费或模型延迟收益。

生产异步准备 P50 三次中位数 **2.566 ms**，未进行同接口 A/B 对比。1000 条日志写入并排空的 A 同步结果为 409.8 / 611.0 / 571.7 ms，B 同步为 407.0 / 464.3 / 2533.5 ms，B 异步为 134.5 / 220.5 / 200.6 ms。异步日志机制在 A 已存在，这些 I/O 测量只保留运行证据，不作为新增架构收益。

## 复现与验收

```powershell
uv run pytest -q
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv build
uv run python scripts/smoke_wheel.py

# Export the already optimized baseline; no live game/model calls.
git archive --format=zip --output=runs/robustness-baseline.zip 8c0f2ae416791543438fee705c52d5d2725b3da9
Expand-Archive -LiteralPath runs/robustness-baseline.zip -DestinationPath runs/robustness-baseline
.\spiremind.cmd benchmark --baseline runs/robustness-baseline --rounds 30 --output runs/robustness-local.json
```

本地 Python 3.11 / 3.13 全量测试各 **221 项通过**，Ruff 检查与格式通过，sdist / wheel 构建通过。隔离 wheel 安装验证包内知识、十个已核验 Mock 动作和 16 状态离线 benchmark。新增回归覆盖恢复计时、旧回执对账、缓存独立副本、未知机制、数值修复、用量分类、历史重复导入、训练／留出隔离、事务回滚、战术晋升／反例和 Windows 文件锁恢复。

Windows / Linux、Python 3.11 / 3.13 的远端检查由现有 [GitHub CI](https://github.com/optima-xu/SpireMind/actions/workflows/test.yml)执行，包括构建和隔离安装。CI 验证确定性行为，不按耗时阈值判失败。源码指纹、原始数据和测试共同限定性能声明；本轮没有新增模型对照或完整实机，因此不报告胜率提升。

仍未完整建模双敌朝向、Unmovable 隐藏计数及其他未知反应机制；不支持的效果继续阻止精确组合证明。经验学习目前的战术覆盖有限，药水长期收益、构筑边际价值和跨 Agent 因果归因仍需后续扩展。
