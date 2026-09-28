# Contributing to SpireMind

感谢提交问题、文档和代码改进。项目当前固定验证 STS2 v0.111.0；涉及游戏版本、桥接协议或公开
状态字段的变更，请在 PR 中写明实际验证范围。

## 开发环境

```powershell
git clone https://github.com/optima-xu/SpireMind.git
Set-Location SpireMind
uv sync --locked
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run pytest -q
```

提交前也应验证发布包：

```powershell
uv build
uv run python scripts/smoke_wheel.py
```

## Pull request 要求

- 说明具体问题、最终行为和验证命令。
- 策略改动应使用真实公开状态或精简 fixture 证明，不使用隐藏抽牌顺序、动作 preview 或 evaluator。
- 对未知机制保持 `unknown` 或安全跳过，不把启发式结果描述成确定机制。
- 保持 OpenAI-compatible provider 通用；服务商字段放在 `extra_body` 或单独示例配置中。
- 不提交 `.env`、本地 endpoint、API key、`runs/`、SQLite、游戏存档、编译产物或 `references/`。
- 只更新与改动相关的文档和测试。

较大的协议、状态 schema 或许可变更，建议先开 issue 说明范围。
