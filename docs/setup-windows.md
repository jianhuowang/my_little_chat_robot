# Windows 安装与配置

本指南仅配置本机上的 AstrBot、NapCatQQ 和 DeepSeek。不要把 AstrBot 或 NapCat 管理页面暴露到公网，也不要把真实 API Key 或 QQ 登录凭据写入仓库、截图或日志。

## 1. 准备 DeepSeek

1. 在 DeepSeek 开放平台创建 API Key，只充值可接受损失的小额余额。
2. 在项目根目录复制示例文件：

   ```powershell
   Copy-Item -LiteralPath .env.example -Destination .env
   notepad .env
   ```

3. 只在本机 `.env` 中替换 `DEEPSEEK_API_KEY`。

## 2. 安装 uv 和 AstrBot

在 PowerShell 中确认 `uv` 可用；若未安装，使用 Windows Package Manager：

```powershell
winget install --id astral-sh.uv -e
uv tool install astrbot --python 3.12
where.exe astrbot
astrbot --version
```

初始化运行目录：

```powershell
.\scripts\Initialize-AstrBot.ps1
```

## 3. 安装和登录 NapCatQQ

从 NapCatQQ 官方 Release 下载 Windows 版本，按照官方 Windows Shell 指南启动，并使用专门的 QQ 小号扫码。不要使用主 QQ 号。NapCat WebUI 默认端口是 `6099`。

## 4. 连接 OneBot v11

确认 AstrBot WebUI 只监听 `127.0.0.1:6185`，NapCat WebUI 也不对公网开放。在 AstrBot WebUI 创建 `OneBot v11` 机器人：启用，主机 `0.0.0.0`，端口 `6199`。若配置 Token，NapCat 两侧必须一致。

在 NapCat WebUI 选择“网络配置 → 新建 → WebSocket 客户端”，URL 填写 `ws://127.0.0.1:6199/ws`。AstrBot 控制台出现 `aiocqhttp(OneBot v11) 适配器已连接` 才算成功。

`0.0.0.0:6199` 是 OneBot 适配器的监听地址，不是管理页面地址。不要在路由器或 Windows 防火墙中把 `6099`、`6185` 或 `6199` 映射到公网；需要远程管理时，应另行设计带认证的安全访问方案。

## 5. 配置 DeepSeek

启动 AstrBot 时使用 `.\scripts\Start-AstrBot.ps1`，使 `$DEEPSEEK_API_KEY` 仅进入当前进程。

在“服务提供商 → 新增”优先选择 DeepSeek；若当前版本没有 DeepSeek 卡片，则选择 OpenAI 兼容提供商。填写：API Base URL `https://api.deepseek.com/v1`，API Key `$DEEPSEEK_API_KEY`，模型 `deepseek-v4-flash`。

模型自定义参数：`max_tokens` 为 `512`，自定义请求体为 `{"thinking":{"type":"disabled"}}`。将最大上下文轮数 `max_context_length` 设为 `10`，每次淘汰轮数 `dequeue_context_length` 设为 `1`。关闭流式输出和所有工具。

不要配置备用模型、自动模型路由、联网搜索、图片理解或其他多模态能力。在 AstrBot 人格设置中配置系统提示词，要求回复明确说明“我是机器人/AI 助手”，不得冒充真人。

## 6. 配置低成本规则

按照 `config/astrbot-v1-checklist.json` 设置：群聊需要 @ 或唤醒词，私聊无需唤醒前缀，`unique_session=false`，60 秒最多 5 条且超出丢弃，忽略机器人自身消息；关闭主动回复、图片描述、STT、TTS、Web 搜索和工具。第一版不安装额外的非文本消息插件，图片、语音、视频和文件按 AstrBot/NapCat 默认方式忽略或提示不支持，不应触发额外模型调用。需要排除某个私聊联系人时，在 AstrBot 自定义规则中对其关闭消息处理。

使用 `/sid` 获取管理员 UID，在 WebUI 添加管理员。使用 `/reset` 清空当前会话，使用 `/stats` 查看当前会话 Token。管理员 UID 和 QQ 登录凭据只在本机管理，不要提交到仓库或发送到群聊。

## 7. 检查

```powershell
.\scripts\Test-Prerequisites.ps1
.\scripts\Get-DeepSeekBalance.ps1
```

检查通过后，按[验收清单](acceptance-checklist.md)逐项完成手工验证。安装、扫码登录和 WebUI 配置都需要用户本人完成；本仓库不会自动登录 QQ、创建密钥、充值或续费。
