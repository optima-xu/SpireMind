# 安装与运行

实机桥接针对 **Windows、STS2 v0.111.0、标准单人模式**。其他游戏版本需重新验证补丁。
Python 决策代码支持 Windows/Linux、Python 3.11–3.13。

## 推荐安装

先安装 [Git for Windows](https://git-scm.com/downloads/win)，关闭游戏，然后执行：

```powershell
git clone https://github.com/optima-xu/SpireMind.git
Set-Location SpireMind
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1
```

脚本会寻找 Steam 游戏目录，使用 uv 准备 Python 3.13 和锁定的运行依赖；缺少 uv 或 .NET 9 SDK
时调用[官方 uv 安装器](https://docs.astral.sh/uv/reference/installer/)和
[官方 .NET 安装器](https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-install-script)。
工具安装在项目 `.tools/`，不需要手动激活虚拟环境或全局修改 PATH。已有 uv/.NET 可复用。
桥接按 `bridge.lock.json` 固定提交，应用兼容补丁，构建并复制三个模组文件，逐一校验哈希。
安装过程中游戏必须保持关闭。

```powershell
# 非默认 Steam 库
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -GameRoot 'D:\SteamLibrary\steamapps\common\Slay the Spire 2'

# 只安装 Python 演示；跳过游戏、Git 桥接和 .NET
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -Offline

# 使用阿里云模型配置模板
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -Provider deepseek
```

`-Offline` 表示跳过实机集成，首次下载 Python/依赖仍需要网络。重复运行会保留 `.env` 和
`config.local.toml`；`-Provider` 只影响首次创建的配置，不会覆盖已有服务地址。
如果升级了游戏，请先重新验证桥接，不要直接沿用旧补丁。

## 配置模型

安装后编辑 `config.local.toml` 和 `.env`：

- 通用模板填写 `base_url`、`model`，密钥变量为 `OPENAI_API_KEY`。
- 阿里云模板填写自己的部署地址，密钥变量为 `DASHSCOPE_API_KEY`，默认 `enable_thinking=true`。
- `calculator_mode="required"` 要求接口支持标准 `tools`、`tool_choice` 和工具结果消息。
  不支持 function calling 时可改为 `"off"`，此时不再强制计算器；`"auto"` 也不保证调用。
- 不支持 `response_format` 时可设置 `json_mode=false`，最终决策仍须是合法 JSON。

CLI 默认自动读取 `config.local.toml`，再加载同目录的 `.env`；已有进程环境变量优先。
`.env` 只支持字面量 `KEY=value`、引号和注释，不执行命令或展开变量。
使用其他配置：`.\spiremind.cmd --config PATH doctor`。

```powershell
# 无密钥演示
.\spiremind.cmd start --environment mock --policy rules

# 主动测试模型；会调用 API
.\spiremind.cmd probe-model
```

`probe-model` 检查 JSON、模型设置、动作绑定和计算器往返，结果写入 `runs/model-probe.json`。

## 首页启动、暂停与恢复

从 Steam 打开游戏并启用 STS2AIMCP 模组，停在**首页／主菜单**：

```powershell
.\spiremind.cmd doctor
.\spiremind.cmd start --character ironclad --ascension 0
```

不在首页时，先返回首页；`start` 会拒绝接管当前场景。角色可选 `ironclad`、`silent`、`regent`、
`necrobinder`、`defect`，进阶必须已解锁。首页有未完成对局时使用 `resume`，换角色／难度前
先在游戏内完成或放弃原对局。启动会自动同步当前版本牌库。

在同目录的另一个终端执行 `pause`，并用 `status` 确认已到 `paused` 后再手动操作。
`resume` 继续暂停的进程；Ctrl+C 停止后也可用 `resume` 重新连接未完成对局。
运行中的动作会完成验证或对账再暂停，恢复时重新读状态。完整命令见[命令说明](COMMANDS.md)。

模组存档与原版存档分开。Mock 只是固定流程测试，不是游戏模拟器。

## 手动安装与开发

已有 Python/uv 的用户可跳过安装脚本：

```powershell
uv sync --locked
Copy-Item .env.example .env
Copy-Item config.example.toml config.local.toml
```

不要覆盖已有配置。实机桥接仍需 .NET 9 SDK 和游戏目录；关闭游戏后执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/prepare-bridge.ps1 -GameRoot 'D:\SteamLibrary\steamapps\common\Slay the Spire 2' -Install
```

省略 `-Install` 只构建到 `build/mods/STS2AIMCP`。脚本不覆盖不匹配的 bridge checkout。
Python 用户也可用 `uv run spiremind ...`，默认配置与 `.env` 行为相同。源码升级前停止 Agent：

```powershell
git pull --ff-only
uv sync --locked
uv run pytest -q
```

## 排查

| 现象 | 检查 |
| --- | --- |
| 安装找不到游戏 | 使用 `-GameRoot` 指定目录，或 `-Offline` 体验演示。 |
| `doctor` 无法连接 | 游戏是否运行、模组是否启用、`[game].base_url` 是否正确。 |
| 模型返回 401/403 | `.env` 的变量名是否与 `api_key_env` 一致，密钥是否属于该 endpoint。 |
| `start` 提示先返回首页 | 返回主菜单；已有对局时用 `resume`。 |
| `pause_requested` 后仍未暂停 | 等待当前模型请求或动作对账完成，查看 `status`。 |
| `resume` 找不到对局 | 从 Steam 启动游戏；空首页用 `start` 开新局。 |
| 命令返回退出码 2 | 达到运行预算或状态检查停止，查看 `runs/<attempt-id>/summary.json`。 |

每次运行保存脱敏配置、状态、上下文、决策和 summary。密钥、配置、数据库、`.tools/`、`runs/`
及桥接 checkout 被 Git 忽略；分享日志前检查本地路径和游戏信息。实机验证范围见[验收记录](ACCEPTANCE.md)。
