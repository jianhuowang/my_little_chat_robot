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

AstrBot 版本必须为 `4.13.0` 或更高；`$DEEPSEEK_API_KEY` 形式的服务商密钥环境变量从 `4.13.0` 才开始支持。若版本更低，先运行 `uv tool upgrade astrbot`，再次确认版本后再继续。

初始化运行目录：

```powershell
.\scripts\Initialize-AstrBot.ps1
```

初始化脚本默认读取仓库 `.env` 的 `ASTRBOT_RUNTIME_DIR`；只有显式传入 `-RuntimeDir` 时才覆盖它。第一次启动前，在该运行目录的 `data/cmd_config.json` 中把 `dashboard.host` 改为 `127.0.0.1`，确认 `dashboard.port` 为 `6185`。

然后在一个专用 PowerShell 窗口启动 AstrBot，并让这个窗口保持运行：

```powershell
.\scripts\Start-AstrBot.ps1
```

从此处开始，在第二个 PowerShell 窗口执行配置检查、前置检查和余额查询；不要关闭运行 AstrBot 的专用窗口。WebUI 应只通过 `http://127.0.0.1:6185` 访问。

## 3. 安装和登录 NapCatQQ

从 NapCatQQ 官方 Release 下载 Windows 版本。NapCat 的 WebUI 默认会监听所有地址；在登录或打开 WebUI 前，停止 NapCat，在 NapCat 配置目录的 `webui.json` 中明确设置：

```json
{
  "host": "127.0.0.1",
  "port": 6099
}
```

保留该文件中自动生成的 Token 等其他字段，不要用上面的片段覆盖整个文件。重新启动 NapCat 后，确认日志中的 WebUI 地址是 `http://127.0.0.1:6099`，再按照官方 Windows Shell 指南使用专门的 QQ 小号扫码；不要使用主 QQ 号。

## 4. 连接 OneBot v11

确认 AstrBot WebUI 监听 `127.0.0.1:6185`、NapCat WebUI 监听 `127.0.0.1:6099`。在 AstrBot WebUI 创建 `OneBot v11` 机器人：启用，反向 WebSocket 主机 `127.0.0.1`，端口 `6199`。若配置 Token，NapCat 两侧必须一致。

在 NapCat WebUI 选择“网络配置 → 新建 → WebSocket 客户端”，URL 填写 `ws://127.0.0.1:6199/ws`。AstrBot 控制台出现 `aiocqhttp(OneBot v11) 适配器已连接` 才算成功。

不要把任一监听地址改成通配地址或局域网地址，也不要在路由器或 Windows 防火墙中把 `6099`、`6185` 或 `6199` 映射到公网；需要远程管理时，应另行设计带认证的安全访问方案。

## 5. 配置 DeepSeek

在“服务提供商 → 新增”优先选择 DeepSeek；若当前版本没有 DeepSeek 卡片，则选择 OpenAI 兼容提供商。填写：API Base URL `https://api.deepseek.com/v1`，API Key `$DEEPSEEK_API_KEY`，模型 `deepseek-v4-flash`。

记下 WebUI 中该服务商的 ID，保存配置，然后在专用窗口按 `Ctrl+C` 停止 AstrBot。打开运行目录中的 `data/cmd_config.json`，在顶层 `provider` 数组中找到 `id` 与刚才记录一致、且 `api_base` 为 `https://api.deepseek.com/v1` 的那个对象。只把该对象的 `model_config` 设置为以下精确值；该对象的其他字段保持不变：

```json
"model_config": {
  "model": "deepseek-v4-flash",
  "max_tokens": 512,
  "extra_body": {
    "thinking": {
      "type": "disabled"
    }
  }
}
```

同一文件的 `provider_settings` 必须设置 `default_provider_id` 为这个 ID、`max_context_length` 为 `10`、`dequeue_context_length` 为 `1`、`web_search` 为 `false`、`streaming_response` 为 `false`。只保留这一个已启用的聊天服务商，不配置后备模型或自动路由；服务商 modalities 只保留文本，并关闭所有工具。

保存并重启 AstrBot。为了核对持久化结果，在第二个 PowerShell 窗口运行下面的只读命令；把路径和 `$providerId` 改成自己的非敏感值。命令只输出模型配置、Base URL 和密钥引用状态，不要显示或复制 `key`：

```powershell
$providerId = "your-provider-id"
$config = Get-Content -LiteralPath runtime\astrbot\data\cmd_config.json -Encoding UTF8 -Raw | ConvertFrom-Json
$provider = $config.provider | Where-Object { $_.id -eq $providerId }
if ($null -eq $provider) { throw "Provider ID not found" }
$provider.model_config | ConvertTo-Json -Depth 6
$provider.api_base
if (@($provider.key) -contains '$DEEPSEEK_API_KEY') { "API key reference: OK" } else { "API key reference: CHECK" }
```

预期模型配置与上面的 JSON 完全一致，Base URL 是 `https://api.deepseek.com/v1`，密钥引用状态为 `OK`。若不一致，停止 AstrBot、修正 `data/cmd_config.json`、保存并重启 AstrBot，再检查一次。

不要配置备用模型、自动模型路由、联网搜索、图片理解或其他多模态能力。在 AstrBot 人格设置中配置系统提示词；只有被直接询问身份时才说明自己是 AI，不得冒充真人或作品角色。

## 6. 配置低成本规则

按照 `config/astrbot-v1-checklist.json` 设置：群聊需要 @ 或唤醒词，私聊无需唤醒前缀，`unique_session=false`，60 秒最多 5 条且超出丢弃，忽略机器人自身消息；关闭主动回复、图片描述、STT、TTS、Web 搜索和工具。第一版不安装额外的非文本消息插件，图片、语音、视频和文件按 AstrBot/NapCat 默认方式忽略或提示不支持，不应触发额外模型调用。需要排除某个私聊联系人时，在 AstrBot 自定义规则中对其关闭消息处理。

使用 `/sid` 获取管理员 UID，在 WebUI 添加管理员。使用 `/reset` 清空当前会话，使用 `/stats` 查看当前会话 Token。管理员 UID 和 QQ 登录凭据只在本机管理，不要提交到仓库或发送到群聊。

## 7. 检查

```powershell
.\scripts\Test-Prerequisites.ps1
.\scripts\Get-DeepSeekBalance.ps1
```

前置检查会读取 Windows 的实际 TCP 监听表；`6099`、`6185`、`6199` 任一端口没有监听，或存在通配/非回环监听，都会失败。不要为了让检查通过而开放防火墙或改成全接口监听。

检查通过后，按[验收清单](acceptance-checklist.md)逐项完成手工验证。安装、扫码登录和 WebUI 配置都需要用户本人完成；本仓库不会自动登录 QQ、创建密钥、充值或续费。

## 8. 生成人格与本地热梗提示词

在项目根目录运行：

```powershell
uv run qq-deepseek-setup render-persona
notepad runtime\persona\astrbot-persona.txt
```

命令只输出生成路径、活跃/过期词条数和 SHA-256，不会显示完整提示词或密钥。生成文件位于 `runtime/persona/astrbot-persona.txt`。把文件的全部内容复制到 AstrBot WebUI 的 `default` 人格并保存；不要直接修改 AstrBot 的 SQLite 数据库。

词库源文件是 `config/meme-lexicon.json`，最多 20 条，推荐保持 10–15 条。每条都有过期日期；更新后重新运行生成命令并在 WebUI 重新保存。机器人每条回复最多一个热梗，语境不合适时不用；严肃求助、健康、安全、法律、财务、冲突和负面情绪场景禁止玩梗。自动发送表情包不属于第一版。

官方参考：[AstrBot OneBot v11](https://docs.astrbot.app/en/platform/aiocqhttp.html)、[AstrBot 服务商配置](https://docs.astrbot.app/en/providers/start.html)、[AstrBot 模型参数](https://docs.astrbot.app/en/config/model-config.html)、[NapCat WebUI 配置](https://napneko.github.io/config/basic)、[DeepSeek 思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)。
