# 部署与使用

本文覆盖三种用途：离线验证控制流程、连接任意 OpenAI-compatible 模型，以及在 Windows 上连接
《杀戮尖塔 2》实机。实机桥接当前固定支持游戏 **v0.111.0**；其他版本需要重新验证桥接补丁和
内部状态字段。

## 1. 环境要求

通用部分需要：

- Git
- Python 3.11–3.13
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

实机运行还需要：

- Windows
- 《杀戮尖塔 2》v0.111.0
- .NET SDK 9
- 游戏自带的 Godot 引擎

## 2. 获取项目并安装依赖

```powershell
git clone https://github.com/optima-xu/SpireMind.git
Set-Location SpireMind
uv sync --locked
```

先执行完全离线的控制流测试：

```powershell
uv run spiremind run --environment mock --policy rules
```

Mock 是固定场景序列，只验证状态、路由、动作和 trace，不是游戏模拟器。

## 3. 配置模型

### 通用 OpenAI-compatible 服务

```powershell
Copy-Item .env.example .env
Copy-Item config.example.toml config.local.toml
```

编辑 `.env`：

```dotenv
OPENAI_API_KEY=replace-me
```

再在 `config.local.toml` 中填写服务商的 `base_url` 和 `model`。SpireMind 请求标准
`/chat/completions`，模型必须返回包含合法 `action_id` 的 JSON。

### 阿里云 Model Studio / DashScope 兼容接口

```powershell
Copy-Item .env.example .env
Copy-Item config.deepseek.example.toml config.local.toml
```

把 `config.local.toml` 中的 `YOUR-ENDPOINT` 替换为自己的部署地址，并在 `.env` 中设置：

```dotenv
DASHSCOPE_API_KEY=replace-me
```

示例默认关闭 `enable_thinking`。服务商不接受 `response_format` 时，将 `json_mode` 改为 `false`；
模型返回内容仍须是合法 JSON。
`calculator_mode="required"` 默认强制模型先通过标准 function tool 做一次成功计算，后续算术
可继续调用；此模式需要兼容服务支持 `tools`、`tool_choice` 和工具结果消息。若接口不支持，
可改为 `calculator_mode="off"`，但此时不再保证算术经过工具；`"auto"` 也不保证调用。

### 验证模型接口

```powershell
uv run --env-file .env spiremind --config config.local.toml probe-model
uv run --env-file .env spiremind --config config.local.toml run --environment mock
```

`probe-model` 会用 `48-11=37` 检查模型名、JSON 解析和合法动作绑定；启用计算器时还检查工具往返。结果写入 `runs/model-probe.json`。它不会输出
或保存 API key。

不使用 uv 启动时，请通过操作系统或进程环境设置同名密钥变量；程序不会自动读取 `.env`。

## 4. 构建并安装游戏桥接

先关闭游戏。将下面的路径替换为自己的游戏安装目录：

```powershell
pwsh -File scripts/prepare-bridge.ps1 `
  -GameRoot 'C:\Program Files (x86)\Steam\steamapps\common\Slay the Spire 2' `
  -Install
```

脚本会：

1. 克隆 `bridge.lock.json` 固定的 `sts2-ai-mcp` 提交。
2. 应用本仓库针对 v0.111.0 的兼容补丁。
3. 以 Release 模式构建桥接。
4. 在 `-Install` 模式下复制并校验三个模组文件的哈希。

省略 `-Install` 只会构建到 `build/mods/STS2AIMCP`。若游戏正在运行，安装会主动停止。

## 5. 启动实机 Agent

从 Steam 启动游戏，确认已加载 STS2AIMCP 模组并停在主菜单，然后依次执行：

```powershell
uv run --env-file .env spiremind --config config.local.toml doctor
uv run --env-file .env spiremind --config config.local.toml observe
uv run --env-file .env spiremind --config config.local.toml sync-card-db
uv run --env-file .env spiremind --config config.local.toml run
```

- `doctor` 检查游戏、模组和协议版本。
- `observe` 只读取当前公开状态。
- `sync-card-db` 从当前游戏版本导入静态卡牌资料；Agent 运行时不要执行它。
- `run` 继续已有模组存档，或从主菜单创建配置指定的新局。
- `step` 最多执行一个动作，适合首次接入检查。

可通过命令行覆盖角色和进阶：

```powershell
uv run --env-file .env spiremind --config config.local.toml run `
  --character ironclad --ascension 0
```

运行时不要同时手动操作游戏。相同桥接地址只允许一个 SpireMind 写进程；第二个进程会被锁拒绝。
Ctrl+C 会保留 trace 和待核对动作。

## 6. 日志、恢复与升级

每次执行在 `runs/<attempt-id>/` 保存脱敏配置、状态、上下文、决策、错误和 summary。`runs/`、`.env`、
`config.local.toml`、SQLite 和完整卡牌缓存都已加入 `.gitignore`。分享日志前仍应检查其中是否包含不想
公开的本地路径或游戏状态。

离线查看一次运行：

```powershell
uv run spiremind replay runs/<attempt-id>
```

升级步骤：

```powershell
git pull --ff-only
uv sync --locked
uv run pytest -q
```

升级前先停止 Agent。游戏版本变化后，不要沿用旧桥接补丁或把敌人知识文件简单改名；应重新验证
桥接协议、同步卡牌资料并重建对应版本知识。

## 7. 常见问题

| 现象 | 检查 |
| --- | --- |
| `doctor` 无法连接 | 游戏是否运行、模组是否加载、`[game].base_url` 是否为桥接地址 |
| 模型返回 401/403 | `.env` 的变量名是否与 `api_key_env` 一致，key 是否属于当前 endpoint |
| 模型名不匹配 | 服务商是否改写模型名；必要时审查后关闭 `require_exact_model` |
| 模型不支持 JSON mode | 设置 `json_mode=false`，同时确保提示返回纯 JSON |
| `run` 返回退出码 2 | 达到步数、时间或 token 预算，查看对应 run 的 `summary.json` |
| bridge checkout 不匹配 | 保留本地修改，另建干净 checkout；脚本不会覆盖未知提交 |

项目仍处于 alpha。已验证控制链和固定回归不代表五角色、多 seed 或高进阶胜率已经达标。
