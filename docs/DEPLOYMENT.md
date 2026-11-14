# 部署与配置指南 / Deployment & Configuration

## 1. 环境要求

| 组件 | 说明 |
| --- | --- |
| **操作系统** | 实机桥接需 **Windows**（《杀戮尖塔 2》`v0.111.0`，标准单人模式）；纯后端测试与 Web 开发支持 Windows / Linux。 |
| **Python & uv** | Python **3.11 – 3.13**，使用 [`uv`](https://docs.astral.sh/uv/) 管理虚拟环境与 `uv.lock`。 |
| **Node.js & pnpm** | Node **20+ / 22** 与 **`pnpm`**（构建 `web/` 前端静态资源需要；若仅使用终端无界面模式 `spiremind play` 可选）。 |
| **.NET 9 SDK & Git** | 仅首次自动构建/安装 `STS2AIMCP` 游戏桥接模组时需要。 |

---

## 2. 安装步骤

### 方式一：Windows 一键脚本（推荐）

先**关闭《杀戮尖塔 2》**，然后在项目根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1
```

常见可选参数：
- 手动指定 Steam 游戏目录：
  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -GameRoot 'D:\SteamLibrary\steamapps\common\Slay the Spire 2'
  ```
- 仅本地准备 Python 与前端（跳过游戏目录探测与桥接构建）：
  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -Offline
  ```

### 方式二：手动安装（开发者 / CI）

```powershell
# 1. 安装后端依赖
uv sync --locked

# 2. 复制初始配置与密钥文件（若尚不存在）
Copy-Item .env.example .env
Copy-Item config.example.toml config.local.toml

# 3. 安装并构建 Web Console 到 web/dist/
pnpm --dir web install
pnpm --dir web run build

# 4. 可选：构建并安装游戏桥接模组（先关闭游戏）
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/prepare-bridge.ps1 -GameRoot 'D:\SteamLibrary\steamapps\common\Slay the Spire 2' -Install
```

---

## 3. 配置模型与密钥

你既可以直接在 Web 控制台的 **设置与诊断 (`Settings & Doctor`)** 中选择预设、填写入 `.env` 的密钥并保存，也可以手动编辑 `config.local.toml` 和 `.env`。

### `.env`

```dotenv
deepseek_api_key=your_key_here
```

> 进程环境变量优先级高于 `.env`。前端与 `/api/settings` 接口永远不会返回明文 Key，只显示环境变量名、是否已配置及首尾脱敏预览。

### `config.local.toml` 主要字段

```toml
[model]
base_url = "https://api.deepseek.com"
model = "deepseek-flash"
api_key_env = "deepseek_api_key"
json_mode = true
calculator_mode = "required"
temperature = 0.2
max_tokens = 4096

[model.extra_body]
thinking = { type = "disabled" }

[game]
base_url = "http://127.0.0.1:8080"
character = "ironclad"
ascension = 0

[runtime]
context_tokens = 4000
max_context_tokens = 16000
max_steps = 3000
error_retry_seconds = 180

[strategy]
combat_guards = true
boss_potion_damage_fraction = 0.20

[server]
host = "127.0.0.1"
port = 8765
```

- **OpenAI 兼容接口适配**：若使用的服务不支持 Function Calling，请将 `calculator_mode` 设为 `"off"`；若不支持 `response_format`，请将 `json_mode` 设为 `false`。
- **Ollama 本地模型**：可在设置页直接点击 `Ollama` 预设（默认 `http://localhost:11434/v1`、`json_mode = false`、`calculator_mode = "auto"`）。

---

## 4. 运行与日常开发

### 生产模式（推荐日常使用）

构建一次 `web/dist/` 后，直接运行：

```powershell
.\spiremind.cmd
```

打开浏览器访问 `http://127.0.0.1:8765`。默认会托管构建好的静态页面，不占用额外的 Node 进程。

### 前后端热重载开发模式

1. 终端 1 启动后端（不自动弹窗）：
   ```powershell
   uv run spiremind ui --no-browser
   ```
2. 终端 2 启动 Vite 开发服务器（自动代理 `/api` 和 `/api/ws` 到 `8765`）：
   ```powershell
   pnpm --dir web dev
   ```
   浏览器访问 `http://localhost:5173`。

### 终端诊断与无界面模式

```powershell
# 诊断游戏桥接
.\spiremind.cmd doctor

# 同时发送一次极简 LLM 连通性测试
.\spiremind.cmd doctor --check-llm

# 无界面开新局（或加 --attach 接管当前游戏）
.\spiremind.cmd play --character ironclad --ascension 0 --policy model
```

---

## 5. 常见问题排查

- **Web 打开后页面空白或提示未构建**：确认已执行 `pnpm --dir web run build` 且 `web/dist/index.html` 存在。
- **`Start New Run` 报错提示存在存档或场景不符**：游戏处于未完成对局时请改用 **Attach Run**（或游戏内放弃/结束当前局返回主菜单）。
- **Bridge 探测失败**：确认已从 Steam 启动游戏、启用 `STS2AIMCP` 模组，且 `config.local.toml` 中的 `[game].base_url` 与桥接监听地址一致（默认 `http://127.0.0.1:8080`）。
