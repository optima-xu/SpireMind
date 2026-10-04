# 多 Agent 的分层记忆与经验学习

该系统采用专业 Agent 路由：每个状态只有一个主决策者，Coordinator 管生命周期、合法性、执行与对账。Combat 管战斗及战斗内选牌，Run 管奖励、牌组、商店与休息，Map 管路线，Event 管事件、宝箱与模态选择。Reflection 是独立的后台任务，没有 Environment 或执行动作的能力。

## 记忆归属

`MemoryManager.context()` 为每个 Agent 生成 `MemoryContext`，包含实例 UUID、策略版本、对应 Run 投影、私有 Working、人工 Skill、交接和检索结果。模型共享 Provider，却使用不同任务和上下文。外部动作格式保持 `action_id` 和可选 `strategy_update`；生产者标记和期望版本由 Runtime 绑定，不能让模型自行指定。

Working 的键是 `(instance_id, agent, task)`。Combat 的 task 使用幕数与楼层；战斗内选牌不换 scope。其他 Agent 按场景与楼层隔离，Map 保持本幕目标。revision 变化使旧行动计划失效，当前合法动作和参数始终取自最新状态。`lost_hp_this_turn` 仅由已验证的同回合 HP 下降更新，回合切换清零。

桥接 run ID 类似 seed，会重复；它用于保守的跨局证据分组，实际执行实例另外使用 UUID。Embark、新开局及已终局 seed 的重新开始创建新实例，正常续跑恢复已有实例与 Working。`runs` 仍保存兼容的最新整局记录，旧实例可由快照、审计和 Episode 追溯。

| 共享字段 | 写入者 |
| --- | --- |
| boss_plan / potion_policy / gold_policy | Run |
| route_preferences | Map |
| needs / strengths / weaknesses / archetype_scores / readiness | 确定性的 DeckAnalyzer |
| route_horizon | 地图图结构计算 |
| current_goal | 当前 Agent 的私有 Working |
| learned lessons | Reflection，经证据验证 |

更新必须属于当前场景的生产者，并匹配读取时的 policy_version。每次最多改变两个共享策略字段；私有目标不推进共享策略版本。旧更新被拒绝时恢复最新共享策略，动作合法性仍单独核验。单个 SQLite 执行器和数据库维护锁将生产环境写入串行化。

## 交接与证据

已核验的跨角色转换会生成交接，记录 producer、consumer、前后 HP/gold、楼层、路线摘要、策略版本和证据 revision。Map 的商店、休息和 Boss 展望进入 Run；Run 的资源策略进入 Combat；Combat 与 Event 的资源变化进入下一角色的上下文。即时事实另行保留在状态及共享投影中，摘要不承担数值事实的唯一来源。

交接绑定幕数、楼层、HP、gold、牌组和药水的指纹及策略版本，资源或策略变化后失效。旧动作 ID 不进入交接。Episode 记录生产者、消费者、交接 ID 和上游策略版本；历史日志没有这些关系时保留未知，不补造依赖链。

一次更新将 Run、Working、审计、对应快照、Episode 和必要的复盘 pending 作业合并提交。失败回滚后才允许重新写入，缓存去重信息在提交成功后更新。SQLite WAL、原有 runs/snapshots 表和 schema 1/2 快照继续兼容，新增表采用增量建表，当前存储版本为 3。

## 从经验学习

这里学习的是跨局可检索经验，没有更新模型权重。历史导入连接前后状态、动作与 receipt：动作身份、前一个 decision、下一个 decision、完成状态和 verify 必须一致，才标为已核验。拒绝、超时、未完成或无法连接的记录保留未知。执行成功只证明发生了变化；死亡不能让之前每个动作自动成为反例。

启动默认在 SQLite 所属线程离线检查本地历史；数据与源码指纹未变化时复用导入结果。缺少 summary 的中断日志也可导入，按 manifest 与已记录的 receipt 判断，不把缺失结果补造为成功；后续成功对账可将同一条未验证 Episode 晋升，FTS 不重复建索引。模型复盘仍默认关闭，`[memory] enabled = false` 可关闭学习接入，`bootstrap_history = false` 仅关闭启动历史导入。

2026-10-04 的本机导入包含 47 条 live trace，其中 35 条缺少正常结束总结，分为 13 个真实 seed 组、9 个训练组和 4 个留出组。初版统计为 27 条正常结束 trace、12 个 seed、8/4 分组；原有 seed 的分组保持冻结，新出现的 seed 才加入训练。同 seed 的续跑留在同一组，`run_unknown` 等占位 ID 不参与；在线新增 Episode 也读取持久化分组，不绕过留出隔离。未来的新实例按版本、角色和 seed 聚合支持，避免重复同 seed 达到独立证据门槛。

公开复现材料包含训练组的 686 条已验证局部观察，去除原始 action_id、decision_id、endpoint、个人路径和完整运行序列，保留资源前后值、条件、证据摘要及指纹。导入时重新检查 HP、gold、Block 和牌组数量差值。原始日志与 SQLite 不发布。

流程是 `观察 → Episode → 复盘 proposal → 验证证据 → candidate → 三个独立 seed 支持与回归 → active`。无效条件、不存在的证据、跨角色/版本引用、留出集引用和与实际差值不符的 proposal 被拒绝。模型指令被改写成规范的条件观察，避免模型自由文本直接变成执行规则。

确定性复盘只提炼可核算的局部效果；可选模型复盘也受相同门控。当前已激活的两条观察分别是特定条件下 `defend_ironclad` 的 Block +5，以及选牌后的 deck count +1。它们不会宣称“总该防御”或“总该选牌”。已核验同条件反例会立即停用对应经验，保留全部修订；回归覆盖这一流程。

条件战术另存于 `tactical_lessons`，当前实现 `rage_before_attack`。必须从完整公开前后状态重新核算免费愤怒的能量、HP 与 Rage 变化，不能直接信任模型理由或摘要字段。一个训练 seed 可形成 candidate，三个独立训练 seed 才激活；相同 seed 的重复支持不提高门槛计数。已验证训练反例立即停用。Combat 使用时重新检查当前文本、合法动作、费用、出牌上限、反应能力与遗物；停用记录会禁止对应愤怒强制顺序和精确搜索。公开事实支持的静态安全规则仍可独立使用，状态未知时放弃证明。

本机实际导入后共 4,257 条 Episode，训练 2,058、留出 2,199；两条数值观察 active，条件战术 active 为 0。已记录的 65 条愤怒证据全部属于留出集，未用来激活新战术。战术晋升与未来反例停用已由固定测试验证，实战收益仍需新训练 seed 和独立对照。数据迁移前建立 SQLite 备份，维护锁内执行；原始历史与数据库不发布。

## 检索与后台执行

SQLite [FTS5](https://sqlite.org/fts5.html) 用公开卡牌、敌人和遗物 ID 建索引，BM25 排序前增加版本、角色、Agent、场景、验证状态和训练集合过滤。场景公开符号是绑定参数，不作为任意 SQL。专业经验仅给对应角色；当前没有未经目标角色验证就跨 Agent 激活经验的捷径。

BM25 用包括当前敌人 ID 的公开符号先取最多 32 个候选，再按当前合法动作类型、可见手牌、玩家能力和 HP 重排；不会只凭相同版本与场景注入一条过期牌序。每次最多两条 Episode 和三条 active Skill，合计不超过 600 个估计 token，编译器优先逐条容纳经验。Episode 带“已验证转换，非最优性证明”标记。匹配条件不足或未知机制时保留不确定性；学习内容的优先级低于实时游戏事实与确定性安全结论。缓存最多 256 个检索结果，键包含当前能量、HP 区间和敌人 ID，新增证据或经验修订后失效。

复盘触发于战斗结束和终局，以公开 in-combat 信号判断；战斗内选牌弹窗不会被误认为战斗结束。先把作业记为数据库 pending，再交给容量 8 的队列；队列满时保留 pending，消费者空闲时补入。启动检查 pending，取消或失败后的作业可恢复。默认使用离线复盘，启用模型后每次运行最多 4 个请求、12,000 token，并受 Runtime 总预算约束；失败会写审计，未验证的输出不会注入决策。

## 性能和可靠性边界

牌组缓存不缓存 HP readiness：0 HP 必须计算为 0。卡牌事实按版本、升级和内容 generation 失效；牌组与策略适配键包含知识指纹，策略包不可变，更新后重新加载。知识库写入与当前 Runtime 使用相同维护锁。`PublicFacts.unpack()` 每次返回独立可变副本，战斗评估只在一次解析作用域里复用结果。

所有运行时 SQLite 连接都在专用单线程创建、使用、关闭。事件循环通过标准库执行器提交事务，取消调用者不会中断已经排队的事务；关闭在已排队工作之后执行。离线维护和测试保留同步 API。

日志使用容量 256 的 asyncio.Queue，单消费者每批最多 32 条，写入线程复用文件句柄；队列满时生产者等待，消费者错误通过 enqueue/flush/close 传播。正常退出及协作式取消排空已接收记录。SIGKILL/断电不保证内存日志队列完整；关键游戏 pending 继续独立持久化并在请求前 fsync，恢复先对账再行动。
