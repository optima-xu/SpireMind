# 重构暂停记录

用户于 2026-10-30 要求暂停，随后要求继续；现已完成重构及本轮离线验收。以下保留暂停时的进度记录。

最终验证：240 项 pytest 通过（18.91 秒），Ruff 检查通过，95 个 Python 文件格式检查通过；8/8 个标注决策局面通过；16 个场景离线性能评测完成；wheel/sdist 离线构建成功，独立安装环境完成 10 步规则演示、8 个标注局面及性能评测。真实模型和游戏 API 调用数均为 0。

当前架构说明见 `docs/ARCHITECTURE.md`，机器可读验收记录在 `runs/validation/refactor-2026-10-30.json`。未提交或推送代码；真实模型效果与实战胜率尚未验证。

## 约束

- 任务：根据架构审阅重构 SpireMind，逻辑清楚、改善决策，删除无用抽象和重复代码。
- 模型必须使用 `deepseek-flash`，密钥变量为 `deepseek_api_key`，不再默认使用原来的服务商密钥。
- 用户要求先不要调用 API。本轮没有调用模型或游戏 API；HTTP 测试使用 MockTransport，并在 pytest 中禁止真实 HTTP。
- 不提交、不推送；保留现有工作区。没有启动游戏或真实 Agent。

## 当前改动

- 模块迁移到 core、decision、application、adapters、learning、evaluation；CLI 解析与 bootstrap 组装分开。
- core 保存共享上下文、事实、模型错误和响应；决策层不再导入数据库或具体模型客户端。增加依赖边界测试。
- DecisionFrame 在每次决策中统一评估、排除已知无法支付的 HP 成本动作，并在执行前再次验证。CombatStrategy 复用同一份评估。
- MemoryManager 在副本中计算转移，SQLite 提交成功后发布；增加已提交转移去重、策略版本检查、工作作用域删除。
- PendingTransition 和 ExecutionJournal 保存待核对动作，支持重启后先恢复、再决策；不会直接重发。
- 转移核验增加 run/version/character 约束；单独记录保守的即时效果核验 confirmed/conflict/unknown。
- 公用资源转移函数用于输出、生存搜索和效果核验；支持在其他手牌未知时保留已证明的已知致胜路径，不冒称最大伤害。
- 修复目标专属数值污染其他目标的可变缓存问题。
- 增加 RunIntent、战斗反馈和卡牌奖励相对于跳过的牌组缺口比较。
- 经验检索使用完整状态指纹；后台整理按作业相关证据签名筛选；相同经验不重复增加版本。
- 删除 combat_tactics 转发模块，以及生产代码未使用的 current_plan、assumptions、rejected_options、decision_context 和相关清空接口。
- status 显式读取 trace_dir；增加 `evaluate` 命令及 8 个独立标注的离线局面。
- config.py、两份示例配置、忽略的 config.local.toml/config.deepseek.toml、.env.example 已切换 DeepSeek。未查看或输出真实密钥。
- README 中英文、部署/命令说明及安装默认配置已部分更新。

## 暂停时已完成的验证

- 最近完成的整套测试：233 passed in 17.36s。含真实 HTTP 拦截、依赖边界、动作门控、事务故障注入、重启恢复、目标预览隔离、DeepSeek 模拟请求检查。
- 之后又增加了两个测试，删除了未用工作记忆字段，调整了结束对局保存、baseline worker 定位、抽牌搜索限制、恢复入口、文档等；这些最新修改尚未重新运行完整测试。
- `uv build --offline --cache-dir .uv-cache` 成功生成 wheel 和 sdist，但发生在最后几处源代码和文档修改之前，产物不是最终版本。
- 没有实战胜率或真实模型效果结论。

## 暂停时的后续工作（现已处理）

1. 检查最新改动，运行 Ruff 修复排序、格式化和静态检查。
2. 运行完整离线 pytest，特别关注新的经验缓存/增量整理测试、工作记忆字段删除、抽牌搜索限制和恢复逻辑。
3. 运行 `evaluate` 生成报告，以及离线 benchmark；不要使用 `--use-model`、probe-model 或真实游戏入口。
4. 完成 `docs/ARCHITECTURE.md`：README 和 pyproject 已引用该文件，但暂停时尚未创建。说明实际边界、迁移、有限机制覆盖和尚待实战验证，不能声称完整战斗模拟器。
5. 检查旧模块导入和现行使用文档；历史审阅 `docs/ARCHITECTURE_REVIEW_2026-10-30.md` 保留为旧版本审阅。
6. 重新离线构建并验证 wheel 的模块和知识/评测资源；现有 smoke_wheel.py 会安装依赖，若执行需选择无需联网的验证方式。
7. 检查 git diff，汇报最终测试结果、API 未调用及剩余实战验证限制。不擅自提交或启动实机。

Windows 环境下受限进程创建 asyncio 本地通信曾卡住；异步 pytest 需使用已获自动审查允许的受限环境外执行。测试命令使用独立工作区临时目录：

```powershell
$refactorTemp = Join-Path (Get-Location).Path ('.pytest-tmp-refactor-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -u -m pytest -q -p no:cacheprovider --basetemp $refactorTemp
```

暂停时没有仍在运行的测试、构建或 Agent 进程。
