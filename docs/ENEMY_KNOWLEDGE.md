# Enemy Knowledge 设计与维护

SpireMind 在本地保存 STS2 v0.111.0 的 115 个敌人条目。机器可读数据位于
`src/spiremind/knowledge/enemies/v0.111.0.json`，可读图鉴位于
`docs/ENEMY_BESTIARY_v0.111.0.md`。运行 Agent 不需要访问网络。

## 数据来源与边界

基础数据来自 [Spire Codex](https://github.com/ptrlrd/spire-codex) 固定目录
`data-beta/v0.111.0` 的英文怪物、简体中文怪物和英文能力文件。生成器记录三个源文件的
SHA-256、固定版本 URL 和最终条目摘要哈希。每个条目保存规范化 ID、中英文名、类型、区域、
生命范围、招式、循环、固有能力、简短特性和最多三条战术建议。

自动摘要只陈述源文件可支持的招式、数值、循环和能力。源数据没有把所有场景机制关联回怪物；
这类高危规则通过 `CURATED` 明确审校。目前无厌沙虫条目额外记录 `sandpit_power` 与
`frantic_escape` 的保命顺序；旧日雕像条目说明 Slow 会提高其受到的伤害，并建议先打较弱攻击、
最后打最强多段攻击。两条覆盖均由真实桥接状态复核。

这些游戏数据归 Mega Crit Games 所有。Spire Codex API 条款和项目许可链接保存在数据文件及
`src/spiremind/knowledge/enemies/NOTICE.md`；数据不应被解释为 SpireMind MIT 代码授权的一部分。

## 运行时行为

`EnemyKnowledge` 启动时校验 schema、条目数和 ID 唯一性。`ContextCompiler` 仅在 Combat 场景执行：

1. 使用桥接已规范化的 `enemy.id` 精确匹配，不按显示名猜测。
2. 只选择仍存活的当前敌人，同类多只只注入一次。
3. 要求知识库与游戏版本精确匹配；未知 ID 或其他版本不注入旧资料。
4. 只注入 `name/type`、最多三条关键特性和两条攻略，不把 115 条完整图鉴塞进 prompt。
5. `L4_enemy_knowledge` 位于其他可选攻略之前；编译器按当前不同敌人数预留空间，若仍超过硬上限则按画面顺序逐项容纳。

静态资料只用于规划。当前 `L1_current_state` 中的生命、意图、能力描述和卡牌文字始终具有更高
权威；prompt 的 system contract 也明确写入了这个优先级。

## 更新版本

游戏更新后先停止 Agent，再审查生成器中的版本、字段和人工覆盖，随后执行：

```powershell
uv run python scripts/build_enemy_knowledge.py
uv run pytest -q tests/test_enemy_knowledge.py --basetemp=runs/pytest-enemies
```

不要把旧文件简单改名到新版本。必须重新抓取固定版本文件、检查条目数与 ID 集合、复核新增的
特殊能力，并为新版本增加匹配测试。
