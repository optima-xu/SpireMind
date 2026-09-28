# Security Policy

## Supported versions

SpireMind 目前处于 alpha，只维护最新发布版本和 `main` 分支。游戏桥接兼容性另受
`bridge.lock.json` 中固定版本约束。

## Reporting a vulnerability

若仓库启用了 GitHub Private Vulnerability Reporting，请使用仓库 **Security** 页面中的
**Report a vulnerability**。若该入口不可用，可创建一个不含利用细节、API key、存档或个人路径的
简短 issue，请维护者建立私密沟通渠道。

请勿在公开 issue、PR、trace 或截图中提交：

- API key、Authorization header 或 `.env` 内容
- 私有模型 endpoint 中的访问凭证
- 游戏存档或可识别个人环境的完整运行日志

SpireMind 不会将 API key写入 trace；本地配置和运行目录仍应按敏感文件管理。
