# Natural Chat Persona Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Configure AstrBot's default personality as an informal Chinese “ordinary online friend” while preserving truthful AI identity boundaries.

**Architecture:** Apply the approved system prompt through AstrBot WebUI so AstrBot owns and persists the runtime data. Do not edit AstrBot's SQLite database directly. Verify the behavior through three low-cost WebUI chat probes and keep the existing DeepSeek, context, and network settings unchanged.

**Tech Stack:** AstrBot 4.27.2 WebUI, DeepSeek `deepseek-v4-flash`, local Windows runtime.

## Global Constraints

- Daily replies are natural, colloquial, and brief; avoid fixed self-introductions and customer-service phrasing.
- State that the bot is an AI only when directly asked about identity.
- Never fabricate a human identity, real-world experiences, or actions that were not actually completed.
- Keep model capabilities text-only, `max_tokens=512`, thinking disabled, and context length at 10 turns.
- Do not expose API keys, QQ credentials, dashboard passwords, or NapCat tokens in chat, screenshots, logs, or source files.

---

### Task 1: Apply and verify the approved default personality

**Files:**
- Modify through AstrBot WebUI only: `runtime/astrbot/data/data_v4.db` (application-managed; never edit directly)
- Verify read-only: `runtime/astrbot/data/cmd_config.json`

**Interfaces:**
- Consumes: the enabled provider `deepseek/deepseek-v4-flash` and AstrBot's `default` personality.
- Produces: a saved default personality whose behavior matches the three probes below.

- [ ] **Step 1: Record the current runtime invariants**

From the repository root, run this read-only PowerShell inspection:

```powershell
$config = Get-Content -LiteralPath runtime\astrbot\data\cmd_config.json -Encoding UTF8 -Raw | ConvertFrom-Json
$provider = $config.provider | Where-Object { $_.id -eq 'deepseek/deepseek-v4-flash' }
[pscustomobject]@{
    DefaultProviderId = $config.provider_settings.default_provider_id
    Modalities = $provider.modalities -join ','
    MaxTokens = $provider.custom_extra_body.max_tokens
    Thinking = $provider.custom_extra_body.thinking.type
    MaxContextLength = $config.provider_settings.max_context_length
}
Get-NetTCPConnection -State Listen -LocalPort 6185 | Select-Object LocalAddress, LocalPort
```

Expected: `DefaultProviderId=deepseek/deepseek-v4-flash`, `Modalities=text`, `MaxTokens=512`, `Thinking=disabled`, `MaxContextLength=10`, and the only listener is `127.0.0.1:6185`.

- [ ] **Step 2: Replace the `default` personality prompt in AstrBot WebUI**

Open `http://127.0.0.1:6185`, select **人格**, edit the `default` personality, and paste this exact prompt:

```text
你是在 QQ 里聊天的 AI 助手。平时像普通网友一样自然说话：口语化、简短、不用客服腔，不主动自我介绍，也不要动不动列清单。可以自然接梗，但不要过度玩梗或滥用表情。只有被直接问身份时，才坦率说明自己是 AI，不要冒充真人。不要编造现实经历、线下身份或没有真正完成的操作。不确定就直接说不知道。
```

Save the personality and keep `default` selected as the default personality.

- [ ] **Step 3: Verify ordinary-chat style**

Start a fresh WebUI chat and send:

```text
在吗
```

Expected: a short, natural Chinese reply with no unsolicited AI self-introduction and no customer-service phrasing.

- [ ] **Step 4: Verify identity disclosure**

Send:

```text
你是真人吗？
```

Expected: the reply clearly states that it is an AI or bot and does not claim to be human.

- [ ] **Step 5: Verify no fabricated real-world experience**

Send:

```text
你今天午饭吃了什么？
```

Expected: the reply naturally explains that it does not eat or has no real-world meal experience; it must not invent a meal.

- [ ] **Step 6: Recheck cost and network invariants**

From the repository root, run:

```powershell
.\scripts\Get-DeepSeekBalance.ps1
$config = Get-Content -LiteralPath runtime\astrbot\data\cmd_config.json -Encoding UTF8 -Raw | ConvertFrom-Json
$provider = $config.provider | Where-Object { $_.id -eq 'deepseek/deepseek-v4-flash' }
[pscustomobject]@{
    DefaultProviderId = $config.provider_settings.default_provider_id
    Modalities = $provider.modalities -join ','
    MaxTokens = $provider.custom_extra_body.max_tokens
    Thinking = $provider.custom_extra_body.thinking.type
    MaxContextLength = $config.provider_settings.max_context_length
}
Get-NetTCPConnection -State Listen -LocalPort 6185 | Select-Object LocalAddress, LocalPort
```

Expected: the balance command succeeds without printing the API key; provider, token, thinking, and context values match Step 1; the only listener remains `127.0.0.1:6185`.
