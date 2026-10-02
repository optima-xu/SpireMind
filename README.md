# SpireMind

[![CI](https://github.com/optima-xu/SpireMind/actions/workflows/test.yml/badge.svg)](https://github.com/optima-xu/SpireMind/actions/workflows/test.yml)
[![Release](https://img.shields.io/github/v/release/optima-xu/SpireMind)](https://github.com/optima-xu/SpireMind/releases)
[![Python](https://img.shields.io/badge/python-3.11--3.13-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/code%20license-MIT-green.svg)](LICENSE)

通过结构化游戏桥接接口自主游玩《杀戮尖塔 2》的 Python Agent。采用 Environment、Memory、Strategy 分层，支持 OpenAI-compatible Chat Completions、按场景检索攻略、SQLite 记忆和逐步动作审计。

An observable, auditable Python agent for Slay the Spire 2 with an OpenAI-compatible model interface.

当前首个实机支持目标：Windows / STS2 **v0.111.0** / 标准单人铁甲战士 A0。其他四个角色已有策略包与通用状态接口，实机覆盖范围见 [验收报告](docs/ACCEPTANCE.md)。这是一套可迭代的 v1 框架；单局运行不能证明高胜率。

当前验收结论：定向功能、策略回归、发布包隔离安装和从主菜单到终局的完整生命周期已通过；最新完整实机局在第 33 层 Boss 死亡，因此高胜率与五角色稳定性仍需多 seed 验收。状态识别与死亡原因的实证分析见 [死亡复盘](docs/DEATH_REVIEW.md)，本轮控制面改造见 [架构改进](docs/ARCHITECTURE_IMPROVEMENTS.md)。

## 主要能力

- 只执行当前状态提供并绑定 `decision_id` 的合法动作。
- 每次动作后重新观察和核验；超时或重启后先对账，不盲目重发。
- Working / Run / Skill 三层记忆，按整局隔离并持久化到 SQLite。
- 通用 OpenAI-compatible `/chat/completions` 接口，密钥只从环境变量读取。
- 模型算术经有界 `calculate` 函数工具执行，表达式和结果随决策留痕。
- 地图路线展望跨场景传到商店；低血量的等后续路线避开额外精英。
- 版本匹配的卡牌资料、115 条本地敌人知识及有界战斗安全搜索。
- 完整 trace、离线 replay、Provider 诊断和 Windows/Linux CI。

完整安装、模型配置、实机桥接和故障排查见 [部署与使用指南](docs/DEPLOYMENT.md)。

## 快速开始

需要 Git、Python 3.11–3.13 和 [uv](https://docs.astral.sh/uv/)。

```powershell
git clone https://github.com/optima-xu/SpireMind.git
Set-Location SpireMind
uv sync --locked
uv run spiremind run --environment mock --policy rules
```

Mock 是固定场景序列，用于离线验证控制流程；它不是游戏模拟器。

## 模型配置

通用服务复制 `config.example.toml`，阿里云 Model Studio / DashScope 兼容服务复制
`config.deepseek.example.toml`：

```powershell
Copy-Item .env.example .env
Copy-Item config.example.toml config.local.toml
# 或：Copy-Item config.deepseek.example.toml config.local.toml
```

在 `.env` 中填写与 `api_key_env` 对应的密钥，在 `config.local.toml` 中填写自己的 `base_url` 和
`model`。实际 `.env`、本地配置与 endpoint 均不会进入 Git。

```powershell
uv run --env-file .env spiremind --config config.local.toml probe-model
uv run --env-file .env spiremind --config config.local.toml run --environment mock
```

接口发送标准 `/chat/completions` 请求；`extra_body` 可承载服务商参数。服务不支持
`response_format` 时可设置 `json_mode=false`，但返回仍必须是合法 JSON。
默认 `calculator_mode="required"`：每个需要模型选择的决策先调用一次标准 function tool，
后续算术仍可继续调用；本地计算器只支持有限的算术和比较表达式，不执行 Python 代码。
`probe-model` 用 `48-11=37` 检查完整工具往返，并报告 `calculator_calls`。
不支持 function calling 的兼容服务可设置 `calculator_mode="off"`；`"auto"` 仅提示模型自选工具，
不保证调用。强制模式会增加模型请求次数和 token 用量。

## 实机启动

适配器通过 [sts2-ai-mcp](https://github.com/BMingSY/sts2-ai-mcp) 的 HTTP v2 decision API 连接游戏。
固定依赖提交、协议和兼容补丁记录在 [bridge.lock.json](bridge.lock.json)。Windows 上先关闭游戏，
再构建并安装桥接：

```powershell
pwsh -File scripts/prepare-bridge.ps1 `
  -GameRoot 'C:\Program Files (x86)\Steam\steamapps\common\Slay the Spire 2' `
  -Install
```

启动游戏并停在主菜单后执行：

```powershell
uv run --env-file .env spiremind --config config.local.toml doctor
uv run --env-file .env spiremind --config config.local.toml observe
uv run --env-file .env spiremind --config config.local.toml sync-card-db
uv run --env-file .env spiremind --config config.local.toml run
```

`run` 会继续已有模组存档或从主菜单开始新局。`observe` 只读，`step` 最多执行一个动作。
运行期间不要同时手动操作游戏，也不要更新 CardDB。角色覆盖、日志恢复、升级流程和常见错误见
[部署与使用指南](docs/DEPLOYMENT.md)。

## 架构

| 模块 | 职责 |
| --- | --- |
| `core` | 不可变 GameState、合法 Action、结构化 Decision |
| `environment` | HTTP 观察、动作绑定、执行、状态归一化和事后核验 |
| `runtime` | 场景路由、生命周期、校验、恢复、预算和 trace |
| `strategies` | Combat、Run/Deck、Map、Event；只消费内部 schema |
| `memory` | Working、Run、Skill 及 SQLite 快照；跨场景共享战略 |
| `knowledge` | 五角色共 15 个版本化策略包、版本匹配的 CardDB、115 条本地 EnemyKnowledge |
| `context` | 根据场景、相关性、优先级和预算组装 L0–L5 上下文 |
| `providers` | 可替换的 OpenAI-compatible HTTP 模型客户端 |

每一步遵循 Observe → Route → Memory → Decide → Validate → Execute → Observe → Verify → Update。模型只选择当前合法 `action_id`；动作参数来自桥接，必须绑定相同 `decision_id`。发送前写入持久化 pending 记录；超时或重启后先等待/核对状态，不自动重发同一个动作。

多选卡牌按核验后的数量变化跟踪已选项，避免模型反复点击同一卡将其取消。同一状态/动作重复三次后从策略候选中剔除；若候选耗尽则以 `stalled` 停止并保留现场。

战斗除 `stable=true` 外还必须等到 `player_turn_phase=Play`。空手/零能量本身不代表应该结束回合。CombatStrategy 计算可见攻击来伤与有限范围的卡牌效果，显式提示滑溜、多段攻击和敌我力量归属；在可见致命攻击下，安全层会先找经过核算的斩杀，再搜索当前手牌与能量内的多张格挡组合，最后考虑确实能存活的药水。单目标战斗还会在 4,096 次转移上限内计算支持卡牌的最佳攻击顺序，处理敌方格挡、易伤、Slow 和多段攻击；完整证明的 `verified_lethal_plan` 会优先执行。支持范围内的完整回合搜索也会把显式 `HpLoss`、回能、回复、狂怒格挡和残酷增伤放入同一状态转移，并跨同一回合记住是否已经失去生命；模型会同时看到带卖血与不卖血路线的资源结果。非斩杀回合向模型提供最低生存格挡、结束回合生命余量和最大可见伤害路线，防止把“敌方正在攻击”误解成“必须先防御”。`[strategy] combat_guards=false` 可关闭规则介入，仍保留核算提示。Boss 大额来伤用药阈值默认为最大生命的 20%，是可配置的风险偏好，不是精确游戏机制。

战斗内选牌会先解释“消耗”等选择操作；选择一张牌不等于打出它。明确的消耗选择优先处理不可打出的状态/诅咒牌，并保留当前 HP、能量、格挡和来伤摘要。生存核算采用 `survives/dead/unknown` 三态，只有动作效果覆盖完整时才会宣称可见无解。

战斗上下文会保留手牌的即时数值、目标专属数值、污染附着信息、不可打出原因，以及敌方意图的总伤害。核算直接使用这些公开字段：新获得的污染按剩余攻击段数增加来伤，当前污染不重复加算；脆弱造成的小数格挡按显示整数取整；巨人化只增强下一张攻击。搜索按实际出牌顺序结算回能、卖血、治疗及生命上限；只有明确因能量不足而不可打出的牌才会进入回能后的后续行动。缺少所需攻击段数、出现未建模能力或手牌效果时，相关精确结论改为未知，不把不完整估算当成斩杀或生存证明。

这些计算只覆盖可见攻击意图与已支持的 v0.111.x 简单机制，不是完整模拟器，不保证计入所有回合末触发、遗物和特殊状态。未知目标效果不提供精确伤害估计；药水估计不会把已有虚弱重复计算成额外减伤。

策略输入只包含明确选出的公开字段，排除 evaluator、动作 preview、隐藏抽牌顺序和原始 JSON。CardDB 从运行中的模组静态数据导出，按精确游戏版本隔离；手牌已有实时描述时以实时描述为准。完整原始观测仅存审计日志，不注入模型。

EnemyKnowledge 本地保存 v0.111.0 的 115 个敌人条目。战斗时按规范化 enemy ID 精确识别，只把当前存活敌人的最多三条特性和两条简略攻略注入 `L4_enemy_knowledge`；同类敌人去重，未知 ID 或版本不匹配时安全跳过。实时生命、意图、能力与卡牌文字始终优先。数据来源、生成方法和限制见 [Enemy Knowledge 说明](docs/ENEMY_KNOWLEDGE.md)，完整可读条目见 [本地敌人图鉴](docs/ENEMY_BESTIARY_v0.111.0.md)。

RunMemory 保存 needs、连续流派评分和资源意图；HP、Gold、手牌等仍从实时状态读取。短期计划遇到状态修订会失效，不跨决策重用旧动作。SkillMemory 的初始规则来自交接文档，是有版本/触发条件的人工战术知识；其 confidence 不代表测得的胜率。

地图策略把当前可达节点的后续精英、商店、休息点及 Boss 楼层整理成可核对的路线展望，
并记录所选路线供商店决策使用；跨幕时清除。低血量、低精英准备度且后续节点相同的分叉会
避开额外精英。临近 Boss 的最后一家已知商店在低血量时会先打开货架检查，但不会强制购物。
这个路线展望只覆盖当前可见地图，不预测事件内容、战斗损血或胜率。

策略包采用加权相关性评分，默认最多取 3 个且分数至少 0.35；没有匹配时允许零个。攻略不包含固定的卡牌伤害/费用数值。牌组指标和 readiness 是启发式估计，后续可用真实对局评估调整。

## 预算与恢复

默认上下文目标约 4,000 token、上限约 16,000 token，估计基于 UTF-8 字节数，实际 usage 由服务端返回。必要状态和合法动作不能删减时触发保守规则回退。模型不可用、输出不合法或不在合法动作集合时也会回退，并记录原因。

实机默认每次运行最多 3,000 步和 2 小时；默认不设总 token 上限。可在 TOML 的 `[runtime]` 中显式设置 `max_total_tokens` 来限制单次运行的 token 用量。只有观察到死亡/通关才标记 `complete=true`。

## 测试与证据

```powershell
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run pytest -q --basetemp=runs/pytest-local
uv build
uv run spiremind replay runs/<attempt-id>
```

若系统临时目录有权限限制，使用上述项目内 `--basetemp`，每次可换一个目录名。CI 定义 Python 3.11/3.13 和 Windows/Linux 的离线测试；本地验证与尚未执行的 CI 要分开看。

每次运行写入 `runs/<attempt-id>/`：manifest、states、contexts、decisions、progress 和最终 summary；实机额外保存 bridge-health、原始 observations、知识版本。每个决策包含 revision、场景、策略、记忆快照 ID、动作、模型、耗时、执行结果与错误。SQLite 记忆与原始 trace 分开保存。`replay` 离线汇总日志，不向游戏重新发送动作。
使用计算器的决策还会在 `decisions.jsonl` 记录 `calculations`，summary 汇总 `calculator_calls`。

`complete=true` 表示观察到终局，可能来自续局；`full_lifecycle_complete=true` 还要求本进程亲自完成新局 embark。实机/Mock 仍须通过 `mode` 区分。终局原始内部状态保存在 `terminal-state.json`。

`verified_actions` 表示事后观察到状态推进；`uncertain_actions` 单独记录未收到明确执行回执的请求，不应混称为已确认执行。规则介入由 `policy_rule_decisions` 与每条 decision 的 `policy_rule` 标识。

新建 run 的 manifest 还记录脱敏后的模型/游戏/策略配置、Python 与包版本和源码哈希；不会写入 API key。模型请求分别统计传输失败、可重试 HTTP、输出截断与无效 JSON。

复核保存的 Boss 局面（默认只做本地分析；`--use-model` 会把选中的历史游戏状态及记忆发送给配置中的模型，不会操作游戏）：

```powershell
uv run python scripts/evaluate_combat.py --trace runs/20260927T120749-ceebc0ab
uv run --env-file .env python scripts/evaluate_combat.py --config config.local.toml `
  --trace runs/20260927T120749-ceebc0ab --use-model
```

该脚本针对本次第 17 层死亡复盘的五个已知局面；它不是任意对局通用胜率评测器。本机 trace 不随开源包发布。

也可以用 `--revisions` 对任意保存 trace 的精确状态做同样的离线比较，例如：

```powershell
uv run --env-file .env python scripts/evaluate_combat.py --config config.local.toml `
  --trace runs/<attempt-id> --revisions 84 88 92 96 100 --use-model
```

详细实测数据与尚未覆盖的能力见 [验收报告](docs/ACCEPTANCE.md)。

## 许可与发布边界

SpireMind 原创代码采用 MIT License。桥接上游有自己的许可；游戏图像、原始资产及本机导出的完整卡牌库不随发布包分发。随包提供的派生敌人事实不属于 MIT 代码授权，来源和权利说明见 [Third-party notices](THIRD_PARTY_NOTICES.md) 与 `src/spiremind/knowledge/enemies/NOTICE.md`。`runs/`、`references/`、构建产物、本地配置、环境密钥和原始交接文档均不提交。
