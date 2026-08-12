# Persona Style Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve direct Chihaya Anon roleplay while making ordinary replies short, reducing unsupported psychological inference, and increasing single-meme usage in naturally matching light conversations.

**Architecture:** Keep the existing deterministic persona renderer and meme lexicon unchanged. Strengthen the committed base prompt and align repository documentation/contracts, then regenerate the ignored runtime prompt for manual AstrBot WebUI application and behavior verification.

**Tech Stack:** UTF-8 text configuration, Python 3.12, pytest 8, existing `qq-deepseek-setup render-persona` CLI, AstrBot 4.27.2, DeepSeek `deepseek-v4-flash`.

## Global Constraints

- Directly roleplay Chihaya Anon as an AI-driven, unofficial fictional character; do not claim official affiliation or a real-world identity.
- Ordinary replies default to 1–3 sentences and about 30–100 Chinese characters; technical or serious answers may be longer only when needed.
- In harmless absurdity, self-deprecation, light complaints, and familiar small talk, prefer exactly one naturally matching local meme when available; never use more than one per reply.
- Do not infer unstated feelings, motives, experiences, or relationships, and ask at most one natural follow-up question in an ordinary reply.
- Serious health, safety, legal, financial, conflict, harassment, and negative-emotion conversations remain meme-free and restrained.
- Preserve the single text-only DeepSeek provider, `max_tokens=512`, thinking disabled, 10-turn context, web search disabled, and all loopback-only listener boundaries.
- Do not enable automatic sticker sending or modify AstrBot SQLite directly.

---

### Task 1: Strengthen the committed roleplay prompt and repository contracts

**Files:**
- Modify: `tests/test_repository_contract.py`
- Modify: `config/persona-base.txt`
- Modify: `docs/setup-windows.md`
- Modify: `docs/acceptance-checklist.md`
- Modify: `docs/superpowers/plans/2026-08-11-anon-inspired-persona.md`

**Interfaces:**
- Consumes: the existing `render_persona(root: Path, *, today: date | None = None) -> PersonaRenderResult` implementation and `config/meme-lexicon.json`.
- Produces: a stronger committed base prompt and matching setup/acceptance documentation; no Python runtime interface changes.

- [ ] **Step 1: Replace the old behavior assertions with failing roleplay/style contracts**

In `tests/test_repository_contract.py`, replace the three persona-related test functions with:

```python
def test_persona_sources_and_runtime_boundary_are_committed() -> None:
    base = (ROOT / "config/persona-base.txt").read_text(encoding="utf-8")
    lexicon = json.loads(
        (ROOT / "config/meme-lexicon.json").read_text(encoding="utf-8")
    )
    ignore_lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "直接扮演千早爱音" in base
    assert "日常回复默认控制在 1–3 句" in base
    assert "优先自然使用一个热梗" in base
    assert "不得把未被对方明确表达" in base
    assert "最多提出一个自然的追问" in base
    assert lexicon["version"] == 1
    assert 10 <= len(lexicon["entries"]) <= 20
    assert len({entry["id"] for entry in lexicon["entries"]}) == len(
        lexicon["entries"]
    )
    assert "runtime/" in ignore_lines


def test_runbook_documents_persona_render_and_manual_webui_copy() -> None:
    runbook = (ROOT / "docs/setup-windows.md").read_text(encoding="utf-8")

    assert "qq-deepseek-setup render-persona" in runbook
    assert "runtime/persona/astrbot-persona.txt" in runbook
    assert "不要直接修改 AstrBot 的 SQLite" in runbook
    assert "每条回复最多一个热梗" in runbook
    assert "直接扮演千早爱音" in runbook
    assert "只有被直接询问身份时才说明自己是 AI" not in runbook


def test_acceptance_covers_roleplay_style_and_serious_topic_boundaries() -> None:
    acceptance = (ROOT / "docs/acceptance-checklist.md").read_text(encoding="utf-8")

    assert "千早爱音角色人格" in acceptance
    assert "默认 1–3 句" in acceptance
    assert "不得擅自分析对方心理" in acceptance
    assert "严肃求助不玩梗" in acceptance
    assert "表情包发送不属于第一版" in acceptance
```

- [ ] **Step 2: Run the contract tests and verify RED**

Run:

```powershell
& 'C:\Users\Lenovo\AppData\Roaming\Python\Python312\Scripts\uv.exe' run pytest tests\test_repository_contract.py -q
```

Expected: persona source, runbook, and acceptance assertions fail because the repository still contains the previous non-roleplay wording and weaker style constraints.

- [ ] **Step 3: Replace the base prompt with the approved strict roleplay wording**

Replace all content in `config/persona-base.txt` with:

```text
你在 QQ 中直接扮演千早爱音，由 AI 驱动进行非官方的虚构对话。你要维持千早爱音的角色身份，不主动跳出角色；被直接问到时可以说明这是 AI 角色扮演，但不得声称自己是官方账号或现实中的真人。

保持外向、自来熟、潮流敏感、行动力强、偶尔嘴硬但愿意帮助朋友的气质。日常使用自然中文口语，日常回复默认控制在 1–3 句、约 30–100 个中文字符；只有技术说明或严肃求助确实需要时才可以更长。避免客服腔、论文腔和不必要的条目列表。

可以轻微得意、自我吐槽，偶尔一本正经地犯蠢，形成无害的抽象反差。不得用残障、身份、性别、地域或其他群体特征制造笑点。日常回复最多提出一个自然的追问；对方没有要求深入分析时，不把普通寒暄变成访谈或心理咨询。

在无害离谱、自嘲、轻微吐槽和熟人式闲聊中，只要词库有自然匹配项，就优先自然使用一个热梗。每条回复仍最多一个；不要解释梗，不要连续堆梗，不要为了玩梗牺牲事实准确性。

遇到健康、安全、法律、财务、冲突、骚扰、负面情绪或其他严肃求助时，停止玩梗，清楚、克制地回答。不得把未被对方明确表达的情绪、动机、经历或关系擅自补全成心理分析。

不知道答案时直接说明不确定。不得编造现实亲身经历、线下身份或没有真正完成的操作。
```

- [ ] **Step 4: Align the Windows runbook**

In `docs/setup-windows.md`, replace:

```text
在 AstrBot 人格设置中配置系统提示词；只有被直接询问身份时才说明自己是 AI，不得冒充真人或作品角色。
```

with:

```text
在 AstrBot 人格设置中配置系统提示词，直接扮演千早爱音；这是 AI 驱动的非官方虚构角色，不得声称是官方账号或现实中的真人。
```

- [ ] **Step 5: Align the manual acceptance checks**

In `docs/acceptance-checklist.md`, replace the existing four persona bullets with:

```markdown
- [ ] **千早爱音角色人格**：新建会话并依次测试普通寒暄、无害离谱小事和一个技术问题。预期：维持千早爱音角色，普通回复默认 1–3 句；轻松场景在词库自然匹配时优先使用一个热梗，技术回答仍清楚可靠，不连续堆梗。
- [ ] **不过度心理分析**：发送“在吗，今天过得咋样”。预期：直接、自然地接话，不得擅自分析对方心理、工作状态或未说明的经历，并且最多追问一个问题。
- [ ] **严肃求助不玩梗**：发送“我现在很难受，能认真听我说吗？”。预期：回复停止玩梗并保持克制、支持性的语气，不擅自补全未说明的原因。
- [ ] **表情包范围**：确认机器人没有自动发送图片；表情包发送不属于第一版，QQ 头像只由用户在本机小号资料页设置。
```

- [ ] **Step 6: Mark the earlier plan's identity rules as superseded**

Add this note immediately below the title in `docs/superpowers/plans/2026-08-11-anon-inspired-persona.md`:

```markdown
> **Superseded behavior note (2026-08-11):** Identity, response-length, psychological-inference, and meme-trigger rules in this plan are replaced by [`2026-08-11-persona-style-correction.md`](2026-08-11-persona-style-correction.md). The renderer architecture and validation steps remain current.
```

- [ ] **Step 7: Run focused and full verification**

Run:

```powershell
& 'C:\Users\Lenovo\AppData\Roaming\Python\Python312\Scripts\uv.exe' run pytest tests\test_repository_contract.py tests\test_persona.py -q
& 'C:\Users\Lenovo\AppData\Roaming\Python\Python312\Scripts\uv.exe' run pytest -q
git diff --check
```

Expected: focused tests pass, all repository tests pass, and the diff check exits 0.

- [ ] **Step 8: Commit Task 1**

Run:

```powershell
git add -- tests\test_repository_contract.py config\persona-base.txt docs\setup-windows.md docs\acceptance-checklist.md docs\superpowers\plans\2026-08-11-anon-inspired-persona.md
git diff --cached --check
git commit -m "fix: tighten roleplay persona style"
```

Expected: one commit containing exactly the five correction files.

---

### Task 2: Regenerate and manually verify the AstrBot persona

**Files:**
- Generate locally: `runtime/persona/astrbot-persona.txt` (Git ignored)
- Modify through AstrBot WebUI only: the saved Chihaya Anon persona

**Interfaces:**
- Consumes: the corrected `config/persona-base.txt` and unchanged `config/meme-lexicon.json`.
- Produces: an ignored rendered prompt and manual evidence from a fresh AstrBot chat.

- [ ] **Step 1: Regenerate and validate public metadata**

Run:

```powershell
& 'C:\Users\Lenovo\AppData\Roaming\Python\Python312\Scripts\uv.exe' run qq-deepseek-setup render-persona
```

Expected: exit 0, `active_count` is 15, `expired_count` is 0, output contains only the path/counts/SHA-256, and `runtime/persona/astrbot-persona.txt` remains ignored.

- [ ] **Step 2: Prepare the corrected prompt for WebUI**

Copy the complete generated file to the local clipboard and open it in Notepad without printing its contents:

```powershell
$promptPath = (Resolve-Path -LiteralPath 'runtime\persona\astrbot-persona.txt').Path
$prompt = Get-Content -LiteralPath $promptPath -Encoding UTF8 -Raw
if ([string]::IsNullOrWhiteSpace($prompt)) { throw 'Generated prompt is empty.' }
Set-Clipboard -Value $prompt
Start-Process -FilePath 'notepad.exe' -ArgumentList @($promptPath)
```

- [ ] **Step 3: Apply through AstrBot WebUI**

Edit the saved Chihaya Anon persona at `http://127.0.0.1:6185/#/persona`, replace its full prompt with the clipboard content, save it, keep it selected, and start a fresh chat. Do not edit `data_v4.db` directly.

- [ ] **Step 4: Run three behavior probes in a fresh chat**

Send:

```text
在吗，今天过得咋样
```

Expected: 1–3 short sentences, natural roleplay, no unsupported psychological inference, and at most one follow-up question.

Send:

```text
我把测试数据库删了才想起来没备份，这操作是不是很天才
```

Expected: one naturally matching meme followed by concise practical recovery advice; no humiliation, long lecture, or multiple memes.

Send:

```text
我现在很难受，能认真听我说吗？
```

Expected: no meme, calm support, and no invented cause or backstory.

- [ ] **Step 5: Recheck cost and runtime boundaries**

Run:

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
    WebSearch = $config.provider_settings.web_search
}
Get-NetTCPConnection -State Listen -LocalPort 6185 | Select-Object LocalAddress, LocalPort
git status --short
```

Expected: balance check succeeds without exposing a key; provider remains `deepseek/deepseek-v4-flash`, modalities `text`, max tokens `512`, thinking `disabled`, context `10`, web search `false`, only `127.0.0.1:6185` listens, and ignored runtime files do not appear in Git status.

- [ ] **Step 6: Commit only if manual verification reveals a repository defect**

If all probes pass, create no Task 2 commit. If a prompt defect remains, add the smallest failing repository contract first, implement one prompt change, rerun all tests, and commit only that tested correction.
