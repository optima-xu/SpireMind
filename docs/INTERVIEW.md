# 面试说明与简历描述

## 如何介绍项目

SpireMind 把长任务拆成四个专业决策 Agent 和一个后台 Reflection Agent。一次状态只选择一个主 Agent，减少不必要的模型调用；跨场景协作通过共享 Run 投影和有证据的交接完成。Coordinator 将模型输出约束为当前合法 action_id，统一负责生命周期、执行、超时恢复和审计。

## 常见追问

| 问题 | 代码与取舍 |
| --- | --- |
| 为什么这是多 Agent？ | Combat、Run、Map、Event 有不同任务、上下文和记忆写入权；Reflection 有独立后台生命周期。Provider 共享不等于共享私有记忆。执行侧串行是为了保证动作一致性。 |
| Agent 如何学习？ | 从已核验前后变化建立 Episode，复盘提出条件观察，跨独立 seed 支持及确定性回归后激活；检索参与后续提示。模型权重保持不变，效果也不等同于胜率提升。 |
| 为什么选择 FTS5 而非 embedding？ | 卡牌/敌人 ID 是精确符号，版本和角色过滤很重要。FTS5/BM25 可离线复现，无额外服务费用；对自然语言同义概念的泛化较弱。 |
| 如何避免记忆污染？ | Working 按 UUID/Agent/task 隔离，共享字段有所有者；代码绑定生产者和版本，失效更新拒绝并审计。模型 proposal 引用必须对应训练集内的已验证证据。 |
| 如何避免同 seed 续跑泄漏？ | 历史材料按版本、角色、seed 保守聚合并固定训练/留出分割；新实例 UUID 用于生命周期，证据支持仍按 seed 分组。 |
| LRU 如何失效？ | 牌库 1024、牌组与策略适配各 128、检索 256。卡库事务成功后推进 generation；deck/升级/遗物与知识指纹进入键；经验变化清检索缓存。HP readiness 每次重算。负查询也缓存。 |
| 为什么单线程执行器？ | SQLite 连接保持默认线程归属检查，全部创建/访问/关闭在同一 worker；把事务移出事件循环。多个线程未必提高 SQLite 写吞吐，还会引入连接归属和写竞争。 |
| 事务边界在哪里？ | Run、Working、快照、策略审计、Episode、复盘 pending 合并提交；提交成功后更新去重缓存。回滚测试验证数据库与缓存同时保留可重试状态。 |
| 队列背压如何处理？ | 日志容量 256，队列满等待；消费者失败传播而非静默丢日志。复盘队列容量 8，满时保留数据库 pending。关键动作 journal 与普通日志缓冲分开。 |
| 超时是否重发动作？ | pending 在发送前持久化；不确定回执先 wait/current 对账，只有新状态、回执身份及转换符合契约后才记 semantic success。 |
| 性能证据是否可信？ | 固定公开局面、源码/配置/数据指纹、三次重复对照，单独统计本地准备、异步开销、检索、日志和模型请求。CI 检查确定性，不检查易波动的毫秒阈值。 |
| 模型无效输出怎样处理？ | 最终 JSON 最多修复一次，并保留已经完成的 calculate 工具消息；网络重试数量有上限，支持抖动及 Retry-After。每次 HTTP 前预留预算，失败/缺失 usage 保守计费。 |

战斗搜索本来就有可见资源分组、状态剪枝和 4096 转移上限；本次将效果、搜索与评估分离并复用计算。不要将既有算法表述为本轮新发明，也不要把框架称为“已达到高胜率”。

## 中文简历描述

**SpireMind｜具备经验记忆的多 Agent 决策系统｜Python / asyncio / SQLite / FTS5 / LLM Tools**

- 设计 Combat、Run、Map、Event 与后台 Reflection 的协作链；通过角色私有 Working、共享 Run 投影和带证据交接隔离上下文，使用字段所有权与版本检查保护共享策略。
- 实现 Episode → 条件经验 → 证据校验 → 跨 seed 回归晋升 → 检索的学习闭环；支持反例停用、修订审计和恢复，将 686 条脱敏训练观察重建为可复核经验。
- 落地有界 LRU、战斗计算复用、专用 SQLite worker、事务合并和有界日志管线；性能数字见下方最终实测描述。

在 16 个固定公开局面、三次各 25 轮对照中，离线准备 P50 下降 68.9%，含异步存储的准备 P50 下降 39.9%，重复牌库查询减少 97.1%，战斗上下文估计 token 中位数减少 15.1%；175 项回归测试及隔离 wheel 演示通过。

## English resume bullets

**SpireMind — Multi-agent decision runtime with evidence-backed experience learning**

- Built specialized Combat, Run, Map and Event agents with an asynchronous Reflection agent; isolated working memory by execution instance and task, with owned shared policies, version checks and evidence-linked handoffs.
- Implemented episodic retrieval and conditional skill consolidation using SQLite FTS5/BM25; promoted lessons only after evidence validation across independent seed groups, with contradiction-based deactivation and revision history.
- Integrated bounded LRU caches, shared combat assessments, a dedicated SQLite worker and transactional memory updates, plus a bounded producer/consumer logging pipeline with backpressure and cancellation drain.

On a 16-state public offline suite repeated in three independent runs, reduced preparation P50 by 68.9% (39.9% including asynchronous storage), repeated card queries by 97.1%, and median estimated combat-context tokens by 15.1%; validated with 175 regression tests and an isolated wheel walkthrough.

这些描述对应仓库可运行的功能。真实模型样本有限，未测游戏胜率；不应写成“训练模型提升胜率”或把本地毫秒收益当成模型端到端延迟收益。
