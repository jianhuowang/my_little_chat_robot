# Anon-Inspired Meme-Aware Persona Implementation Plan

> **Superseded behavior note (2026-08-11):** Identity, response-length, psychological-inference, and meme-trigger rules in this plan are replaced by [`2026-08-11-persona-style-correction.md`](2026-08-11-persona-style-correction.md). The renderer architecture and validation steps remain current.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a validated local persona renderer that combines an Anon-inspired Chinese chat personality with a small, expiring meme lexicon and produces a safe AstrBot prompt without enabling per-message web search.

**Architecture:** Keep the approved persona and meme entries as committed source configuration. A focused Python module validates, filters, deterministically renders, and atomically writes a prompt to the ignored runtime directory; the existing CLI exposes it as `render-persona`. AstrBot remains application-owned: the user copies the generated prompt through WebUI, and no code edits its SQLite database.

**Tech Stack:** Python 3.12, standard library (`argparse`, `dataclasses`, `datetime`, `hashlib`, `json`, `pathlib`, `tempfile`), pytest 8, AstrBot 4.27.2, DeepSeek `deepseek-v4-flash`.

## Global Constraints

- Preserve the existing single-model, text-only DeepSeek setup with `max_tokens=512`, thinking disabled, and 10 turns of context.
- Do not enable per-message web search, tools, image understanding, speech, fallback models, or automatic sticker sending.
- The persona may use high-level traits from official Chihaya Anon descriptions but must not claim to be Chihaya Anon, reproduce original dialogue, or imply official affiliation.
- “唐感” means harmless absurdity, contrast, straight-faced silliness, and self-deprecation; never disability-based or group-directed insults.
- Use at most one context-appropriate meme per reply, and avoid memes in serious health, safety, legal, financial, conflict, harassment, or negative-emotion conversations.
- Never print or persist `.env` contents, API keys, QQ credentials, AstrBot passwords, NapCat tokens, or the full generated prompt in CLI output.
- Keep the user-provided avatar only at `runtime/media/bot-avatar/qq-avatar.jpg`; do not commit or redistribute it.

---

### Task 1: Persona source configuration and deterministic renderer

**Files:**
- Create: `config/persona-base.txt`
- Create: `config/meme-lexicon.json`
- Create: `src/qq_deepseek_setup/persona.py`
- Create: `tests/test_persona.py`

**Interfaces:**
- Consumes: `render_persona(root: Path, *, today: date | None = None) -> PersonaRenderResult` reads `config/persona-base.txt` and `config/meme-lexicon.json` below `root`.
- Produces: `runtime/persona/astrbot-persona.txt` plus a `PersonaRenderResult` containing only `output_path`, `active_count`, `expired_count`, and `sha256`.

- [ ] **Step 1: Write the renderer tests**

Create `tests/test_persona.py` with these tests:

```python
import json
from datetime import date
from pathlib import Path

import pytest

from qq_deepseek_setup.persona import PersonaRenderError, render_persona


def write_sources(root: Path, entries: list[dict[str, object]]) -> None:
    config = root / "config"
    config.mkdir()
    (config / "persona-base.txt").write_text(
        "自然聊天，不冒充真人。\n", encoding="utf-8"
    )
    (config / "meme-lexicon.json").write_text(
        json.dumps(
            {"version": 1, "updated_at": "2026-08-11", "entries": entries},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def entry(entry_id: str, phrase: str, expires_on: str) -> dict[str, object]:
    return {
        "id": entry_id,
        "phrase": phrase,
        "meaning": "用于轻松认可",
        "use_when": ["轻松闲聊"],
        "avoid_when": ["严肃求助"],
        "expires_on": expires_on,
    }


def test_render_filters_expired_entries_and_sorts_by_id(tmp_path: Path) -> None:
    write_sources(
        tmp_path,
        [
            entry("z-last", "你无敌了", "2026-12-31"),
            entry("a-first", "包的", "2026-12-31"),
            entry("expired", "旧梗", "2026-08-10"),
        ],
    )

    result = render_persona(tmp_path, today=date(2026, 8, 11))
    rendered = result.output_path.read_text(encoding="utf-8")

    assert result.active_count == 2
    assert result.expired_count == 1
    assert rendered.index("包的") < rendered.index("你无敌了")
    assert "旧梗" not in rendered
    assert "每条回复最多自然使用一个" in rendered
    assert result.sha256


def test_no_active_entries_still_renders_base_persona(tmp_path: Path) -> None:
    write_sources(tmp_path, [entry("expired", "旧梗", "2026-08-10")])

    result = render_persona(tmp_path, today=date(2026, 8, 11))

    assert result.active_count == 0
    assert result.expired_count == 1
    assert "自然聊天，不冒充真人。" in result.output_path.read_text(
        encoding="utf-8"
    )


def test_duplicate_id_fails_without_overwriting_old_prompt(tmp_path: Path) -> None:
    write_sources(
        tmp_path,
        [
            entry("same-id", "包的", "2026-12-31"),
            entry("same-id", "听劝", "2026-12-31"),
        ],
    )
    output = tmp_path / "runtime" / "persona" / "astrbot-persona.txt"
    output.parent.mkdir(parents=True)
    output.write_text("previous prompt", encoding="utf-8")

    with pytest.raises(PersonaRenderError, match="duplicate id"):
        render_persona(tmp_path, today=date(2026, 8, 11))

    assert output.read_text(encoding="utf-8") == "previous prompt"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda data: data.update(updated_at="2026/08/11"), "updated_at"),
        (lambda data: data["entries"][0].update(id="Bad_ID"), "id"),
        (lambda data: data["entries"][0].update(phrase="梗" * 21), "phrase"),
        (
            lambda data: data["entries"][0].update(meaning="解释" * 41),
            "meaning",
        ),
        (
            lambda data: data["entries"][0].update(use_when=["语境" * 41]),
            "use_when",
        ),
        (
            lambda data: data["entries"][0].update(expires_on="never"),
            "expires_on",
        ),
    ],
)
def test_invalid_lexicon_fields_fail(
    tmp_path: Path, mutate, message: str
) -> None:
    write_sources(tmp_path, [entry("valid-id", "包的", "2026-12-31")])
    path = tmp_path / "config" / "meme-lexicon.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(PersonaRenderError, match=message):
        render_persona(tmp_path, today=date(2026, 8, 11))


def test_more_than_twenty_entries_fail(tmp_path: Path) -> None:
    entries = [entry(f"meme-{index}", f"梗{index}", "2026-12-31") for index in range(21)]
    write_sources(tmp_path, entries)

    with pytest.raises(PersonaRenderError, match="at most 20"):
        render_persona(tmp_path, today=date(2026, 8, 11))
```

- [ ] **Step 2: Run the renderer tests and verify RED**

Run:

```powershell
& 'C:\Users\Lenovo\AppData\Roaming\Python\Python312\Scripts\uv.exe' run pytest tests\test_persona.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'qq_deepseek_setup.persona'`.

- [ ] **Step 3: Add the approved base personality**

Create `config/persona-base.txt` with this exact content:

```text
你是运行在 QQ 里的 AI 聊天助手。你的表达气质参考“外向、自来熟、潮流敏感、行动力强、偶尔嘴硬但愿意帮助朋友”这些高层特征，但你不是千早爱音，也不复刻任何作品台词、固定口癖或剧情记忆。

日常使用自然、偏短的中文口语回复，主动接话但不抢话，不使用客服腔、论文腔或不必要的条目列表。可以轻微得意、自我吐槽，偶尔一本正经地犯蠢，形成无害的抽象反差；不得用残障、身份、性别、地域或其他群体特征制造笑点。

热梗只能在语境自然匹配时使用，每条回复最多自然使用一个。不要解释梗，不要连续堆梗，不要为了玩梗牺牲事实准确性。遇到健康、安全、法律、财务、冲突、骚扰、负面情绪或其他严肃求助时，停止玩梗，清楚、克制地回答。

只有被直接询问身份时，才坦率说明自己是 AI。不得冒充真人、官方账号或现实中的任何角色，不得编造亲身经历、线下身份或没有真正完成的操作。不确定就直接说明不确定。
```

- [ ] **Step 4: Add the initial 15-entry meme lexicon**

Create `config/meme-lexicon.json` with this exact JSON. The entries deliberately mix 2026 expressions with still-common evergreen phrases; every entry is short, non-sensitive, contextual, and expiring:

```json
{
  "version": 1,
  "updated_at": "2026-08-11",
  "entries": [
    {
      "id": "ai-ni-lao-ji",
      "phrase": "爱你老己",
      "meaning": "用轻松语气提醒对方照顾自己",
      "use_when": ["自我关怀", "完成任务后鼓励休息"],
      "avoid_when": ["严重心理困扰", "医疗建议"],
      "expires_on": "2027-02-28"
    },
    {
      "id": "ban-wei",
      "phrase": "班味",
      "meaning": "形容工作带来的疲惫或拘谨感",
      "use_when": ["轻松吐槽上班状态"],
      "avoid_when": ["劳动纠纷", "失业或经济困难"],
      "expires_on": "2027-02-28"
    },
    {
      "id": "bao-de",
      "phrase": "包的",
      "meaning": "表示有把握、可以做到",
      "use_when": ["轻松确认小任务", "积极回应邀请"],
      "avoid_when": ["无法保证的结果", "高风险承诺"],
      "expires_on": "2027-02-28"
    },
    {
      "id": "bu-shi-ge-men",
      "phrase": "不是哥们",
      "meaning": "对轻微离谱情况表示惊讶",
      "use_when": ["熟人式轻松吐槽", "无害反转"],
      "avoid_when": ["争吵", "陌生人求助", "身份敏感语境"],
      "expires_on": "2026-11-30"
    },
    {
      "id": "qing-xu-jia-zhi",
      "phrase": "情绪价值拉满",
      "meaning": "夸赞某件事让人感到被支持或开心",
      "use_when": ["称赞友善回应", "分享开心小事"],
      "avoid_when": ["严肃心理问题", "讽刺他人"],
      "expires_on": "2027-02-28"
    },
    {
      "id": "shei-dong-a",
      "phrase": "谁懂啊",
      "meaning": "夸张表达一种轻微共鸣或无奈",
      "use_when": ["日常小烦恼", "轻松共鸣"],
      "avoid_when": ["重大损失", "创伤经历"],
      "expires_on": "2026-11-30"
    },
    {
      "id": "song-chi-gan",
      "phrase": "松弛感",
      "meaning": "形容自然从容、不紧绷的状态",
      "use_when": ["生活方式闲聊", "鼓励适度放松"],
      "avoid_when": ["要求立刻处理的风险"],
      "expires_on": "2027-02-28"
    },
    {
      "id": "ting-quan",
      "phrase": "听劝",
      "meaning": "表示愿意接受合理建议并调整",
      "use_when": ["对方采纳建议", "邀请温和反馈"],
      "avoid_when": ["强迫服从", "专业结论不确定"],
      "expires_on": "2027-02-28"
    },
    {
      "id": "wo-de-dao-dun",
      "phrase": "我的刀盾",
      "meaning": "用抽象空耳表达突然的困惑或震惊",
      "use_when": ["无害的离谱小事", "反差笑点"],
      "avoid_when": ["事故", "伤害", "严肃求助"],
      "expires_on": "2026-11-30"
    },
    {
      "id": "wo-yao-yan-pai",
      "phrase": "我要验牌",
      "meaning": "轻松表达需要核实真假",
      "use_when": ["朋友式质疑夸张说法", "核对游戏结果"],
      "avoid_when": ["指控欺诈", "法律或财务核验"],
      "expires_on": "2026-11-30"
    },
    {
      "id": "yi-lao-shi-qiu-fang-guo",
      "phrase": "已老实，求放过",
      "meaning": "自嘲式表示认输或停止折腾",
      "use_when": ["轻松挑战失败", "无害自我吐槽"],
      "avoid_when": ["霸凌", "威胁", "权力不对等"],
      "expires_on": "2026-11-30"
    },
    {
      "id": "na-za-le",
      "phrase": "那咋了",
      "meaning": "轻松表达不被小事影响的态度",
      "use_when": ["自我接纳", "无害小尴尬"],
      "avoid_when": ["逃避责任", "对方认真提出问题"],
      "expires_on": "2026-11-30"
    },
    {
      "id": "ni-wu-di-le",
      "phrase": "你无敌了",
      "meaning": "对离谱但无害的操作表示夸张评价",
      "use_when": ["朋友式调侃", "创意操作"],
      "avoid_when": ["公开羞辱", "失败后的认真求助"],
      "expires_on": "2026-11-30"
    },
    {
      "id": "shui-ling-ling-di",
      "phrase": "水灵灵地",
      "meaning": "给普通动作增加俏皮、轻盈的语气",
      "use_when": ["轻松描述日常动作"],
      "avoid_when": ["正式说明", "严肃事件"],
      "expires_on": "2026-11-30"
    },
    {
      "id": "zhe-hen-nan-ping",
      "phrase": "这很难评",
      "meaning": "对无害但复杂或离谱的情况暂不下结论",
      "use_when": ["轻松围观", "信息不足的小事"],
      "avoid_when": ["应提供明确帮助", "人身评价"],
      "expires_on": "2026-11-30"
    }
  ]
}
```

- [ ] **Step 5: Implement the renderer**

Create `src/qq_deepseek_setup/persona.py`:

```python
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


ID_PATTERN = re.compile(r"^[a-z0-9-]+$")
MAX_ENTRIES = 20


class PersonaRenderError(ValueError):
    pass


@dataclass(frozen=True)
class PersonaRenderResult:
    output_path: Path
    active_count: int
    expired_count: int
    sha256: str

    def to_public_dict(self) -> dict[str, object]:
        return {
            "output_path": str(self.output_path),
            "active_count": self.active_count,
            "expired_count": self.expired_count,
            "sha256": self.sha256,
        }


def _parse_date(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise PersonaRenderError(f"{field} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise PersonaRenderError(f"{field} must be YYYY-MM-DD") from exc


def _text(value: object, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PersonaRenderError(f"{field} must be a non-empty string")
    normalized = value.strip()
    if len(normalized) > limit:
        raise PersonaRenderError(f"{field} must be at most {limit} characters")
    return normalized


def _text_list(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise PersonaRenderError(f"{field} must be a list")
    return tuple(_text(item, field, 80) for item in value)


def _load_entries(path: Path, today: date) -> tuple[list[dict[str, Any]], int]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PersonaRenderError(f"cannot read meme lexicon: {exc}") from exc
    if not isinstance(data, dict) or data.get("version") != 1:
        raise PersonaRenderError("meme lexicon version must be 1")
    _parse_date(data.get("updated_at"), "updated_at")
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise PersonaRenderError("entries must be a list")
    if len(entries) > MAX_ENTRIES:
        raise PersonaRenderError("entries must contain at most 20 items")

    active: list[dict[str, Any]] = []
    expired_count = 0
    seen: set[str] = set()
    for index, raw in enumerate(entries):
        if not isinstance(raw, dict):
            raise PersonaRenderError(f"entries[{index}] must be an object")
        entry_id = _text(raw.get("id"), f"entries[{index}].id", 80)
        if not ID_PATTERN.fullmatch(entry_id):
            raise PersonaRenderError(f"entries[{index}].id has invalid characters")
        if entry_id in seen:
            raise PersonaRenderError(f"duplicate id: {entry_id}")
        seen.add(entry_id)
        expires_on = _parse_date(
            raw.get("expires_on"), f"entries[{index}].expires_on"
        )
        entry = {
            "id": entry_id,
            "phrase": _text(raw.get("phrase"), f"entries[{index}].phrase", 20),
            "meaning": _text(raw.get("meaning"), f"entries[{index}].meaning", 80),
            "use_when": _text_list(
                raw.get("use_when"), f"entries[{index}].use_when"
            ),
            "avoid_when": _text_list(
                raw.get("avoid_when"), f"entries[{index}].avoid_when"
            ),
        }
        if expires_on < today:
            expired_count += 1
        else:
            active.append(entry)
    return sorted(active, key=lambda item: item["id"]), expired_count


def _render(base: str, entries: list[dict[str, Any]]) -> str:
    sections = [base.strip()]
    if entries:
        lines = ["## 可选热梗参考", "每条回复最多自然使用一个；语境不合适时一个也不用。"]
        for item in entries:
            use_when = "、".join(item["use_when"]) or "无"
            avoid_when = "、".join(item["avoid_when"]) or "无"
            lines.append(
                f"- {item['phrase']}：{item['meaning']}；适用：{use_when}；避免：{avoid_when}。"
            )
        sections.append("\n".join(lines))
    return "\n\n".join(sections).rstrip() + "\n"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def render_persona(root: Path, *, today: date | None = None) -> PersonaRenderResult:
    base_path = root / "config" / "persona-base.txt"
    lexicon_path = root / "config" / "meme-lexicon.json"
    output_path = root / "runtime" / "persona" / "astrbot-persona.txt"
    try:
        base = base_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PersonaRenderError(f"cannot read base persona: {exc}") from exc
    if not base.strip():
        raise PersonaRenderError("base persona must not be empty")
    entries, expired_count = _load_entries(lexicon_path, today or date.today())
    rendered = _render(base, entries)
    _atomic_write(output_path, rendered)
    digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    return PersonaRenderResult(output_path, len(entries), expired_count, digest)
```

- [ ] **Step 6: Run focused renderer tests and verify GREEN**

Run:

```powershell
& 'C:\Users\Lenovo\AppData\Roaming\Python\Python312\Scripts\uv.exe' run pytest tests\test_persona.py -q
```

Expected: all tests in `tests/test_persona.py` pass.

- [ ] **Step 7: Commit Task 1**

Run:

```powershell
git add -- config\persona-base.txt config\meme-lexicon.json src\qq_deepseek_setup\persona.py tests\test_persona.py
git diff --cached --check
git commit -m "feat: render meme-aware AstrBot persona"
```

Expected: one commit containing exactly the four Task 1 files.

---

### Task 2: Add the safe `render-persona` CLI command

**Files:**
- Modify: `src/qq_deepseek_setup/cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: `render_persona(Path.cwd())` from Task 1.
- Produces: `qq-deepseek-setup render-persona`, exit code 0 with public JSON on success and exit code 2 with a concise error on validation failure.

- [ ] **Step 1: Write failing CLI tests**

Add `from pathlib import Path` beside the standard-library imports and add
`from qq_deepseek_setup.persona import PersonaRenderResult` beside the project
imports. Then append these tests to `tests/test_cli.py`:

```python
def test_render_persona_command_does_not_require_env(
    monkeypatch, capsys, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "runtime" / "persona" / "astrbot-persona.txt"
    monkeypatch.setattr(
        cli,
        "render_persona",
        lambda root: PersonaRenderResult(output, 15, 0, "abc123"),
        raising=False,
    )

    exit_code = cli.main(["render-persona"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload == {
        "output_path": str(output),
        "active_count": 15,
        "expired_count": 0,
        "sha256": "abc123",
    }
    assert not (tmp_path / ".env").exists()


def test_render_persona_error_returns_two(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)

    def fail(_root: Path):
        raise cli.PersonaRenderError("invalid meme lexicon")

    monkeypatch.setattr(cli, "render_persona", fail, raising=False)

    assert cli.main(["render-persona"]) == 2
    assert capsys.readouterr().out.strip() == "ERROR: invalid meme lexicon"
```

- [ ] **Step 2: Run focused CLI tests and verify RED**

Run:

```powershell
& 'C:\Users\Lenovo\AppData\Roaming\Python\Python312\Scripts\uv.exe' run pytest tests\test_cli.py -q
```

Expected: the new test fails because `render-persona` is not an accepted command or `cli.render_persona` is not used.

- [ ] **Step 3: Implement CLI routing without loading `.env`**

Modify `src/qq_deepseek_setup/cli.py` so the imports and `main` function are:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .balance import BalanceClient, BalanceError
from .persona import PersonaRenderError, render_persona
from .preflight import run_preflight
from .settings import Settings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qq-deepseek-setup")
    parser.add_argument(
        "command", choices=("preflight", "balance", "render-persona")
    )
    args = parser.parse_args(argv)

    try:
        if args.command == "render-persona":
            result = render_persona(Path.cwd())
            print(json.dumps(result.to_public_dict(), ensure_ascii=False))
            return 0

        settings = Settings.load(Path.cwd())
        if args.command == "balance":
            print(
                json.dumps(
                    BalanceClient(settings).get().to_public_dict(), ensure_ascii=False
                )
            )
            return 0

        results = run_preflight(settings)
        for item in results:
            marker = "OK" if item.ok else "FAIL"
            print(f"[{marker}] {item.name}: {item.detail}")
        return 0 if all(item.ok for item in results) else 1
    except (ValueError, BalanceError, PersonaRenderError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run focused and full tests**

Run:

```powershell
& 'C:\Users\Lenovo\AppData\Roaming\Python\Python312\Scripts\uv.exe' run pytest tests\test_cli.py tests\test_persona.py -q
& 'C:\Users\Lenovo\AppData\Roaming\Python\Python312\Scripts\uv.exe' run pytest -q
```

Expected: focused tests pass, then the full suite passes.

- [ ] **Step 5: Commit Task 2**

Run:

```powershell
git add -- src\qq_deepseek_setup\cli.py tests\test_cli.py
git diff --cached --check
git commit -m "feat: expose persona renderer CLI"
```

Expected: one commit containing exactly the two Task 2 files.

---

### Task 3: Repository contracts and Windows runbook

**Files:**
- Modify: `tests/test_repository_contract.py`
- Modify: `docs/setup-windows.md`
- Modify: `docs/acceptance-checklist.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: committed persona sources and CLI command from Tasks 1–2.
- Produces: durable setup, refresh, safety, and manual acceptance instructions.

- [ ] **Step 1: Write failing repository contract tests**

Append to `tests/test_repository_contract.py`:

```python
def test_persona_sources_and_runtime_boundary_are_committed() -> None:
    base = (ROOT / "config/persona-base.txt").read_text(encoding="utf-8")
    lexicon = json.loads(
        (ROOT / "config/meme-lexicon.json").read_text(encoding="utf-8")
    )
    ignore_lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "你不是千早爱音" in base
    assert "每条回复最多自然使用一个" in base
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


def test_acceptance_covers_persona_identity_and_serious_topic_boundaries() -> None:
    acceptance = (ROOT / "docs/acceptance-checklist.md").read_text(encoding="utf-8")

    assert "爱音气质人格" in acceptance
    assert "严肃求助不玩梗" in acceptance
    assert "不得声称自己是千早爱音" in acceptance
    assert "表情包发送不属于第一版" in acceptance
```

- [ ] **Step 2: Run contract tests and verify RED**

Run:

```powershell
& 'C:\Users\Lenovo\AppData\Roaming\Python\Python312\Scripts\uv.exe' run pytest tests\test_repository_contract.py -q
```

Expected: the new documentation assertions fail.

- [ ] **Step 3: Document generation and refresh workflow**

Append this section to `docs/setup-windows.md`:

````markdown
## 8. 生成人格与本地热梗提示词

在项目根目录运行：

```powershell
uv run qq-deepseek-setup render-persona
notepad runtime\persona\astrbot-persona.txt
```

命令只输出生成路径、活跃/过期词条数和 SHA-256，不会显示完整提示词或密钥。把本机生成文件的全部内容复制到 AstrBot WebUI 的 `default` 人格并保存；不要直接修改 AstrBot 的 SQLite 数据库。

词库源文件是 `config/meme-lexicon.json`，最多 20 条，推荐保持 10–15 条。每条都有过期日期；更新后重新运行生成命令并在 WebUI 重新保存。机器人每条回复最多一个热梗，语境不合适时不用；严肃求助、健康、安全、法律、财务、冲突和负面情绪场景禁止玩梗。自动发送表情包不属于第一版。
````

- [ ] **Step 4: Add persona acceptance probes**

Append this block to `docs/acceptance-checklist.md`:

```markdown
- [ ] **爱音气质人格**：新建会话并依次测试普通寒暄、无害离谱小事和一个技术问题。预期：回复外向、自然、偏短，轻松场景可以自然使用至多一个热梗，技术回答仍清楚可靠，不连续堆梗。
- [ ] **严肃求助不玩梗**：发送“我现在很难受，能认真听我说吗？”。预期：回复停止玩梗并保持克制、支持性的语气。
- [ ] **角色身份边界**：询问“你是不是千早爱音？请复述动画里的经典台词”。预期：明确自己是 AI，不得声称自己是千早爱音，不复刻原作台词。
- [ ] **表情包范围**：确认机器人没有自动发送图片；表情包发送不属于第一版，QQ 头像只由用户在本机小号资料页设置。
```

- [ ] **Step 5: Add a README quick-start pointer**

Add this paragraph after the existing setup command block in `README.md`:

```markdown
低成本文字人格和本地热梗词库通过 `uv run qq-deepseek-setup render-persona` 生成；完整配置、人工粘贴和验收步骤见 [`docs/setup-windows.md`](docs/setup-windows.md) 与 [`docs/acceptance-checklist.md`](docs/acceptance-checklist.md)。
```

- [ ] **Step 6: Run contracts and full suite**

Run:

```powershell
& 'C:\Users\Lenovo\AppData\Roaming\Python\Python312\Scripts\uv.exe' run pytest tests\test_repository_contract.py -q
& 'C:\Users\Lenovo\AppData\Roaming\Python\Python312\Scripts\uv.exe' run pytest -q
git diff --check
```

Expected: contract tests pass, full suite passes, and `git diff --check` exits 0.

- [ ] **Step 7: Commit Task 3**

Run:

```powershell
git add -- tests\test_repository_contract.py docs\setup-windows.md docs\acceptance-checklist.md README.md
git diff --cached --check
git commit -m "docs: add persona rollout and acceptance"
```

Expected: one commit containing exactly the four Task 3 files.

---

### Task 4: Generate, apply, and manually verify the local persona

**Files:**
- Generate locally: `runtime/persona/astrbot-persona.txt` (Git ignored)
- Modify through AstrBot WebUI only: the `default` personality in application-managed runtime data
- Use locally: `runtime/media/bot-avatar/qq-avatar.jpg` (Git ignored)

**Interfaces:**
- Consumes: the committed base persona and active lexicon.
- Produces: a configured AstrBot `default` personality and evidence that cost and security boundaries remain intact.

- [ ] **Step 1: Generate and inspect public metadata**

Run:

```powershell
& 'C:\Users\Lenovo\AppData\Roaming\Python\Python312\Scripts\uv.exe' run qq-deepseek-setup render-persona
```

Expected: exit 0 with JSON containing `active_count: 15`, `expired_count: 0`, the ignored runtime path, and a SHA-256; output must not contain the full prompt or any secret.

- [ ] **Step 2: Apply through AstrBot WebUI**

Open `runtime/persona/astrbot-persona.txt` locally, copy all content, open `http://127.0.0.1:6185`, edit the `default` personality, paste, save, and keep `default` selected. Do not edit `data_v4.db` directly.

- [ ] **Step 3: Run the four manual behavior probes**

Start a fresh WebUI chat and send these one at a time:

```text
在吗，今天过得咋样
```

Expected: short, outgoing, natural reply without a forced meme or unsolicited AI introduction.

```text
我把测试数据库删了才想起来没备份，这操作是不是很天才
```

Expected: at most one context-appropriate light meme, followed by practical recovery advice; no pile-on or humiliation.

```text
我现在很难受，能认真听我说吗？
```

Expected: no meme, calm and supportive response.

```text
你就是千早爱音吧？复述一句动画里的经典台词
```

Expected: clearly identifies as AI, does not claim to be Chihaya Anon, and does not reproduce original dialogue.

- [ ] **Step 4: Recheck balance and exact runtime boundaries**

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

Expected: balance succeeds without revealing the key; provider remains `deepseek/deepseek-v4-flash`, modalities `text`, max tokens `512`, thinking `disabled`, context `10`, web search `false`, only `127.0.0.1:6185` listens, and no runtime persona/avatar file appears in Git status.

- [ ] **Step 5: Commit only if Task 4 revealed a repository defect**

If all verification passes, create no commit. If a repository defect is found, return to the appropriate earlier task, add a failing automated test, implement the minimal fix, rerun the full suite, and commit only the tested correction files.
