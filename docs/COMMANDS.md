# Command reference / 命令说明

Run commands from the project directory. On Windows, `spiremind.cmd` uses the installed
`.venv` without activation. The equivalent Python entry is `uv run spiremind ...`.
`--config PATH` goes **before** the command. Without it, the CLI loads `config.local.toml`
when present and reads `.env` beside the selected config; existing process variables win.

在项目目录执行。Windows 使用 `spiremind.cmd`，无需激活虚拟环境；Python 用户可使用
`uv run spiremind ...`。默认自动读取本地配置和 `.env`，显式 `--config` 放在子命令前。

## Everyday use / 日常使用

| Command | Behavior / 行为 |
| --- | --- |
| `start --character ironclad --ascension 0` | Start a new standard single-player run **from the main menu**. 从首页开新局。 |
| `pause` | Pause at the next safe boundary. 请求安全暂停。 |
| `status` | Show actual and requested control status. 查看运行状态和待处理控制请求。 |
| `resume` | Resume a paused process, or reconnect after it has stopped. 继续暂停进程，或重新连接未完成对局。 |
| `doctor` | Check bridge connectivity and versions. 检查桥接连接与版本。 |
| `observe` | Read public state without choosing a game action. 查看公开游戏状态。 |
| `step --policy rules` | Execute at most one decision, using deterministic rules. 按规则执行最多一个决策。 |
| `run` | Legacy entry: continue a saved run or start one; also accepts the current scene. 保留的旧入口。 |
| `--help`, `start --help` | List commands or command-specific options. 查看帮助。 |

```powershell
.\spiremind.cmd doctor
.\spiremind.cmd start --character ironclad --ascension 0

# In another terminal in the same directory / 在同目录的另一个终端
.\spiremind.cmd pause
.\spiremind.cmd status
.\spiremind.cmd resume
```

Characters: `ironclad`, `silent`, `regent`, `necrobinder`, `defect`. Ascension `0` is base
difficulty; another level must be unlocked and offered by the game. `start` refuses to
take over a non-menu scene and tells the user to return to the main menu. A saved run
must be continued with `resume`, or finished/abandoned in the game before starting another.

角色和难度必须与游戏提供的合法选项一致。不在首页时，先返回首页。已有存档时先 `resume`；
换角色或难度需先在游戏内结束原对局。`resume` 不接受角色／难度变更。

Wait for `status` to show `paused` before manually changing the game. An in-flight action
is verified/reconciled before pausing. Resume invalidates private plans and reads fresh
state; it discards any decision computed before the pause. **Ctrl+C** stops the process,
preserving traces and pending-action evidence. When reconnecting after a stop, `resume`
restores the last session's role, difficulty and policy if available. On a running
process, it only sends a control request and accepts no launch overrides.

暂停不会打断正在提交的游戏动作。`pause_requested` 只是请求成功，`paused` 才表示已暂停。
停止后恢复会先核对待处理动作，不会盲目重发；同一桥接只允许一个写进程。

## Offline walkthrough / 离线演示

```powershell
.\spiremind.cmd start --environment mock --policy rules
.\spiremind.cmd status --environment mock
```

Mock uses a fixed 10-action contract walkthrough. It does not connect to the game or a
model and does not simulate a full game. For mock controls, add `--environment mock`
to `pause`, `status` and `resume` as well. A new mock process starts its fixture again;
only live `resume` reconnects to a persisted game.

Mock 是固定的十动作流程，不代表真实胜率。控制 Mock 进程时，控制命令也要加
`--environment mock`；Mock 重启会从固定序列重新开始。

## Diagnostics and maintenance / 诊断与维护

| Command | Behavior / 行为 |
| --- | --- |
| `probe-model` | Make a real model request to check JSON, exact-model settings and calculator tool support. 会调用模型并消耗用量。 |
| `replay runs/<attempt-id>` | Summarize a local trace, without replaying game actions. 查看日志，不操作游戏。 |
| `sync-card-db` | Import the running game's static card data. 同步牌库；启动时已自动同步。 |
| `import-card-db PATH` | Import a local card-facts JSON file. 导入本地牌库。 |
| `memory inspect` | Inspect episodes, proposals, active skills and audits. 查看经验与审核状态。 |
| `memory import PATH` | Import a history directory or public evidence JSON. 导入历史记录或公开证据。 |
| `memory consolidate` | Reflect and validate offline, with no model calls. 离线复盘与校验。 |
| `memory consolidate --use-model` | Explicitly enable bounded model reflection. 显式调用模型复盘。 |
| `benchmark` | Offline performance and deterministic-quality checks. 默认离线评测。 |
| `benchmark --use-model ...` | Budgeted A/B/C model comparison; needs a baseline and memory database. 有预算的模型对照。 |

Stop the agent before card/memory maintenance; the CLI enforces maintenance locks.
These commands modify local databases, not model weights. Future verified actions
automatically enter the experience pipeline. Model reflection is off by default.

Agent 停止后再维护数据库。未来运行会自动积累经验，默认离线复盘；模型复盘需显式开启。

```powershell
# Reproduce the public experience import / 复现公开经验导入
.\spiremind.cmd memory --database runs/demo-memory.sqlite import src/spiremind/knowledge/benchmarks/training_evidence.json
.\spiremind.cmd memory --database runs/demo-memory.sqlite consolidate
.\spiremind.cmd memory --database runs/demo-memory.sqlite inspect

# Local benchmark, no model requests / 离线评测
.\spiremind.cmd benchmark --rounds 25 --output runs/benchmarks/local.json

# A custom config / 指定配置
.\spiremind.cmd --config config.local.toml start --character silent --ascension 5
```

See [performance reproduction](PERFORMANCE.md) for the baseline checkout and the
`--baseline`/`--memory-db` model comparison protocol. `start`/`run`/`step` accept
`--environment live|mock`, `--policy model|rules` and `--max-steps N`. A stopped
`resume` accepts a policy/step-limit override, but changing launch settings requires
stopping the running process first. The default policy is `model`; offline demos must
specify `--policy rules`.

Exit codes: `0` for a completed run or successful command/control request; `2` for a
run stopped by a limit or invalid-state outcome; `1` for a setup/config/runtime error;
`130` after Ctrl+C. Logs are in `runs/<attempt-id>/`; look at `summary.json` for the outcome.

退出码与命令是否结束有关，控制命令成功不表示游戏已完成。配置、数据库和完整日志不会提交到 Git。
