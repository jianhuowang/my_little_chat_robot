# QQ DeepSeek Bot

Windows 上的低成本 QQ 对话机器人部署包：NapCatQQ + AstrBot + DeepSeek V4 Flash。

1. 阅读 [Windows 安装与配置](docs/setup-windows.md)。
2. 按照 [配置检查表](config/astrbot-v1-checklist.json) 配置 AstrBot。
3. 使用 [验收清单](docs/acceptance-checklist.md) 验证私聊、群聊、上下文和错误处理。

低成本文字人格和本地热梗词库通过 `uv run qq-deepseek-setup render-persona` 生成；完整配置、人工粘贴和验收步骤见 [`docs/setup-windows.md`](docs/setup-windows.md) 与 [`docs/acceptance-checklist.md`](docs/acceptance-checklist.md)。

真实 API Key 只能放在未提交的 `.env` 中。项目不会自动登录 QQ，也不会自动充值或续费。
