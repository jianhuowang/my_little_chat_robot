# Chihaya Anon Emote Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local AstrBot plugin that answers “来只千早爱音” with a random image without calling DeepSeek and occasionally appends an image to normal LLM replies within shared rolling limits.

**Architecture:** Keep all deterministic behavior in a dependency-light Python package inside the plugin: trigger matching, validated settings, rolling quota persistence, image selection, and a controller. Keep `main.py` as a thin AstrBot 4.27.2 adapter using message-event and decorating-result hooks. A repository CLI prepares the user-owned image folders into the Git-ignored runtime plugin directory; Pillow is used only during this installation step to validate images and convert WebP to PNG.

**Tech Stack:** Python 3.12, pytest 8, AstrBot 4.27.2 plugin API, NapCat/OneBot v11 (`aiocqhttp`), Pillow 11/12 for offline asset preparation, PowerShell 5.1-compatible deployment scripts.

## Global Constraints

- Private chat triggers only on trimmed `来只千早爱音` or `/来只千早爱音`; group chat triggers without At whenever a non-self message contains the exact contiguous phrase `来只千早爱音`.
- A direct request never calls DeepSeek and never enters conversation context.
- Normal final LLM replies append an image with probability `0.20`; command results, errors, empty results, and stream fragments are never decorated.
- Direct and passive images share a rolling `3600`-second quota: at most `3` per session and `10` globally, with a same-session cooldown of `300` seconds.
- Direct requests blocked by cooldown or quota return one approved local joke; passive replies blocked for any reason remain text-only.
- Quota reservation is persisted before an image is appended or returned; a later platform-send failure does not refund it.
- Session identifiers are SHA-256 hashes in state and logs; never log QQ IDs, group IDs, API keys, NapCat tokens, or full unified message origins.
- Runtime state, prepared images, local configuration, and downloaded third-party binaries remain under Git-ignored `runtime/`; no image binary is committed.
- The plugin runtime uses only Python standard library plus AstrBot APIs. Pillow is an installer dependency, not imported by the running plugin.
- Existing DeepSeek provider settings, five-messages-per-minute text limit, persona, and loopback-only listeners remain unchanged.

## File Structure

- `plugins/__init__.py`: makes repository plugin packages importable in tests.
- `plugins/chihaya_emotes/__init__.py`: plugin package marker and version.
- `plugins/chihaya_emotes/settings.py`: validated immutable runtime settings.
- `plugins/chihaya_emotes/trigger.py`: private/group trigger matching and session-key hashing.
- `plugins/chihaya_emotes/quota.py`: concurrency-safe rolling quota and atomic JSON state.
- `plugins/chihaya_emotes/image_pool.py`: recursive scanning, digest de-duplication, and no-immediate-repeat selection.
- `plugins/chihaya_emotes/controller.py`: framework-neutral direct/passive decisions.
- `plugins/chihaya_emotes/main.py`: AstrBot event adapter only.
- `plugins/chihaya_emotes/_conf_schema.json`: WebUI-editable defaults.
- `plugins/chihaya_emotes/metadata.yaml`: local plugin metadata and AstrBot version floor.
- `src/qq_deepseek_setup/emote_assets.py`: safe offline image validation, WebP conversion, and runtime staging.
- `scripts/Install-ChihayaEmotes.ps1`: repository-bound PowerShell wrapper around asset preparation and plugin copy.
- `tests/test_emote_settings_trigger.py`: configuration and matching tests.
- `tests/test_emote_quota.py`: rolling-window, persistence, corruption, privacy, and concurrency tests.
- `tests/test_emote_image_pool.py`: scan, de-duplication, and selection tests.
- `tests/test_emote_controller.py`: direct/passive behavior and shared-quota tests.
- `tests/test_emote_plugin_contract.py`: AstrBot adapter/config/metadata source contracts.
- `tests/test_emote_assets.py`: installer conversion and de-duplication tests.
- `tests/test_powershell_wrappers.py`: installer wrapper parser and safety contracts.
- `tests/test_repository_contract.py`: repository policy and runbook assertions.
- `docs/setup-windows.md`: installation/reload/configuration runbook.
- `docs/acceptance-checklist.md`: live QQ acceptance probes.

---

### Task 1: Add validated settings and exact trigger boundaries

**Files:**
- Create: `plugins/__init__.py`
- Create: `plugins/chihaya_emotes/__init__.py`
- Create: `plugins/chihaya_emotes/settings.py`
- Create: `plugins/chihaya_emotes/trigger.py`
- Create: `tests/test_emote_settings_trigger.py`

**Interfaces:**
- Produces: `EmoteSettings.from_mapping(raw, warn) -> EmoteSettings`.
- Produces: `matches_request(message_type, text, *, is_self) -> bool` where `message_type` is `"private"` or `"group"`.
- Produces: `hash_session(unified_msg_origin: str) -> str`, a 64-character lowercase SHA-256 digest.

- [ ] **Step 1: Write failing settings and trigger tests**

Create `tests/test_emote_settings_trigger.py` with parameterized cases for both message types and invalid configuration:

```python
from plugins.chihaya_emotes.settings import EmoteSettings
from plugins.chihaya_emotes.trigger import hash_session, matches_request


def test_defaults_are_the_approved_limits() -> None:
    assert EmoteSettings.from_mapping({}) == EmoteSettings(
        chat_probability=0.20,
        session_cooldown_seconds=300,
        session_hourly_limit=3,
        global_hourly_limit=10,
        window_seconds=3600,
    )


def test_invalid_values_fall_back_without_leaking_values() -> None:
    warnings: list[str] = []
    settings = EmoteSettings.from_mapping(
        {
            "chat_probability": 2,
            "session_cooldown_seconds": 0,
            "session_hourly_limit": 11,
            "global_hourly_limit": 10,
            "window_seconds": -1,
        },
        warnings.append,
    )
    assert settings == EmoteSettings()
    assert warnings
    assert all("2" not in item and "11" not in item for item in warnings)


def test_private_request_is_complete_match_with_optional_slash() -> None:
    assert matches_request("private", " 来只千早爱音 ", is_self=False)
    assert matches_request("private", "/来只千早爱音", is_self=False)
    assert not matches_request("private", "今天来只千早爱音看看", is_self=False)


def test_group_request_is_contains_match_without_mention() -> None:
    assert matches_request("group", "今天来只千早爱音看看", is_self=False)
    assert not matches_request("group", "来个千早爱音", is_self=False)
    assert not matches_request("group", "来只千早爱音", is_self=True)


def test_session_hash_is_stable_and_irreversible_in_shape() -> None:
    digest = hash_session("aiocqhttp:GroupMessage:private-value")
    assert len(digest) == 64
    assert digest == hash_session("aiocqhttp:GroupMessage:private-value")
    assert "private-value" not in digest
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests\test_emote_settings_trigger.py -q
```

Expected: collection fails with `ModuleNotFoundError` for `plugins.chihaya_emotes`.

- [ ] **Step 3: Implement the immutable settings validator**

In `plugins/chihaya_emotes/settings.py`, define the exact dataclass and validator:

```python
from dataclasses import dataclass
from typing import Callable, Mapping


@dataclass(frozen=True)
class EmoteSettings:
    chat_probability: float = 0.20
    session_cooldown_seconds: int = 300
    session_hourly_limit: int = 3
    global_hourly_limit: int = 10
    window_seconds: int = 3600

    @classmethod
    def from_mapping(
        cls,
        raw: Mapping[str, object],
        warn: Callable[[str], None] = lambda _message: None,
    ) -> "EmoteSettings":
        defaults = cls()

        def number(name: str, default: float, low: float, high: float) -> float:
            value = raw.get(name, default)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                warn(f"Invalid {name}; using approved default")
                return default
            converted = float(value)
            if not low <= converted <= high:
                warn(f"Invalid {name}; using approved default")
                return default
            return converted

        def positive_int(name: str, default: int) -> int:
            value = raw.get(name, default)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                warn(f"Invalid {name}; using approved default")
                return default
            return value

        candidate = cls(
            chat_probability=number("chat_probability", defaults.chat_probability, 0, 1),
            session_cooldown_seconds=positive_int(
                "session_cooldown_seconds", defaults.session_cooldown_seconds
            ),
            session_hourly_limit=positive_int(
                "session_hourly_limit", defaults.session_hourly_limit
            ),
            global_hourly_limit=positive_int(
                "global_hourly_limit", defaults.global_hourly_limit
            ),
            window_seconds=positive_int("window_seconds", defaults.window_seconds),
        )
        if candidate.session_hourly_limit > candidate.global_hourly_limit:
            warn("Invalid quota relationship; using approved defaults")
            return defaults
        return candidate
```

- [ ] **Step 4: Implement the two trigger modes and hashed session key**

In `plugins/chihaya_emotes/trigger.py`, add:

```python
import hashlib
from typing import Literal


REQUEST_TEXT = "来只千早爱音"


def matches_request(
    message_type: Literal["private", "group"],
    text: str,
    *,
    is_self: bool,
) -> bool:
    if is_self:
        return False
    normalized = text.strip()
    if message_type == "private":
        if normalized.startswith("/"):
            normalized = normalized[1:]
        return normalized == REQUEST_TEXT
    if message_type == "group":
        return REQUEST_TEXT in normalized
    return False


def hash_session(unified_msg_origin: str) -> str:
    return hashlib.sha256(unified_msg_origin.encode("utf-8")).hexdigest()
```

Set `__version__ = "0.1.0"` in `plugins/chihaya_emotes/__init__.py`; keep `plugins/__init__.py` empty.

- [ ] **Step 5: Run GREEN and commit Task 1**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests\test_emote_settings_trigger.py -q
git diff --check
git add -- plugins\__init__.py plugins\chihaya_emotes\__init__.py plugins\chihaya_emotes\settings.py plugins\chihaya_emotes\trigger.py tests\test_emote_settings_trigger.py
git diff --cached --check
git commit -m "feat: add emote settings and triggers"
```

Expected: 5 tests pass and the commit contains exactly the five implementation/test paths.

---

### Task 2: Implement persistent rolling quota with privacy and concurrency

**Files:**
- Create: `plugins/chihaya_emotes/quota.py`
- Create: `tests/test_emote_quota.py`

**Interfaces:**
- Consumes: `EmoteSettings` from Task 1 and an already-hashed session key.
- Produces: `QuotaDecision` values `allowed`, `cooldown`, `session_limit`, `global_limit`, `probability`, and `state_error`.
- Produces: `RollingQuota.reserve(session_key, gate=lambda: True) -> Awaitable[QuotaDecision]`.

- [ ] **Step 1: Write failing quota tests with an injected clock**

Create tests using `now = [1_000.0]` and `clock=lambda: now[0]`. Cover these exact behaviors:

```python
import asyncio
import json

from plugins.chihaya_emotes.quota import QuotaDecision, RollingQuota
from plugins.chihaya_emotes.settings import EmoteSettings


def run(coro):
    return asyncio.run(coro)


def test_cooldown_and_rolling_expiry(tmp_path) -> None:
    now = [1_000.0]
    quota = RollingQuota(tmp_path / "quota-state.json", EmoteSettings(), lambda: now[0])
    assert run(quota.reserve("a")) is QuotaDecision.ALLOWED
    assert run(quota.reserve("a")) is QuotaDecision.COOLDOWN
    now[0] += 300
    assert run(quota.reserve("a")) is QuotaDecision.ALLOWED
    now[0] += 300
    assert run(quota.reserve("a")) is QuotaDecision.ALLOWED
    now[0] += 300
    assert run(quota.reserve("a")) is QuotaDecision.SESSION_LIMIT
    now[0] = 4_600.0
    assert run(quota.reserve("a")) is QuotaDecision.ALLOWED


def test_probability_gate_does_not_consume_quota(tmp_path) -> None:
    quota = RollingQuota(tmp_path / "quota-state.json", EmoteSettings(), lambda: 1_000.0)
    assert run(quota.reserve("a", gate=lambda: False)) is QuotaDecision.PROBABILITY
    assert run(quota.reserve("a")) is QuotaDecision.ALLOWED


def test_restart_restores_state_without_plain_session_id(tmp_path) -> None:
    path = tmp_path / "quota-state.json"
    first = RollingQuota(path, EmoteSettings(), lambda: 1_000.0)
    assert run(first.reserve("hashed-session")) is QuotaDecision.ALLOWED
    assert "hashed-session" in path.read_text(encoding="utf-8")
    second = RollingQuota(path, EmoteSettings(), lambda: 1_001.0)
    assert run(second.reserve("hashed-session")) is QuotaDecision.COOLDOWN


def test_concurrent_sessions_never_exceed_global_limit(tmp_path) -> None:
    settings = EmoteSettings(session_cooldown_seconds=1, session_hourly_limit=10)
    quota = RollingQuota(tmp_path / "quota-state.json", settings, lambda: 1_000.0)

    async def reserve_all():
        return await asyncio.gather(*(quota.reserve(f"s{index}") for index in range(20)))

    results = run(reserve_all())
    assert results.count(QuotaDecision.ALLOWED) == 10
    assert results.count(QuotaDecision.GLOBAL_LIMIT) == 10


def test_corrupt_state_is_quarantined(tmp_path) -> None:
    path = tmp_path / "quota-state.json"
    path.write_text("not-json", encoding="utf-8")
    quota = RollingQuota(path, EmoteSettings(), lambda: 1_000.0)
    assert run(quota.reserve("a")) is QuotaDecision.ALLOWED
    assert len(list(tmp_path.glob("quota-state.corrupt-*.json"))) == 1
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1
```

Add separate tests for the third session reservation, exact global tenth reservation, atomic-write failure returning `STATE_ERROR` without changing in-memory counts, and persisted JSON containing only version, timestamps, and hashed session-map keys.

- [ ] **Step 2: Run quota tests and verify RED**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests\test_emote_quota.py -q
```

Expected: import fails because `quota.py` does not exist.

- [ ] **Step 3: Implement decision order and atomic persistence**

In `plugins/chihaya_emotes/quota.py`, implement:

```python
from __future__ import annotations

import asyncio
import json
import os
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from time import time
from typing import Callable

from .settings import EmoteSettings


class QuotaDecision(str, Enum):
    ALLOWED = "allowed"
    COOLDOWN = "cooldown"
    SESSION_LIMIT = "session_limit"
    GLOBAL_LIMIT = "global_limit"
    PROBABILITY = "probability"
    STATE_ERROR = "state_error"


@dataclass
class _State:
    global_events: list[float] = field(default_factory=list)
    sessions: dict[str, list[float]] = field(default_factory=dict)
    last_sent: dict[str, float] = field(default_factory=dict)


class RollingQuota:
    def __init__(
        self,
        state_path: Path,
        settings: EmoteSettings,
        clock: Callable[[], float] = time,
    ) -> None:
        self.state_path = state_path
        self.settings = settings
        self.clock = clock
        self._lock = asyncio.Lock()
        self._state = self._load()

    async def reserve(
        self,
        session_key: str,
        gate: Callable[[], bool] = lambda: True,
    ) -> QuotaDecision:
        async with self._lock:
            now = self.clock()
            candidate = deepcopy(self._state)
            self._prune(candidate, now)
            last = candidate.last_sent.get(session_key)
            if last is not None and now - last < self.settings.session_cooldown_seconds:
                return QuotaDecision.COOLDOWN
            session_events = candidate.sessions.setdefault(session_key, [])
            if len(session_events) >= self.settings.session_hourly_limit:
                return QuotaDecision.SESSION_LIMIT
            if len(candidate.global_events) >= self.settings.global_hourly_limit:
                return QuotaDecision.GLOBAL_LIMIT
            if not gate():
                return QuotaDecision.PROBABILITY
            session_events.append(now)
            candidate.global_events.append(now)
            candidate.last_sent[session_key] = now
            try:
                self._save(candidate)
            except OSError:
                return QuotaDecision.STATE_ERROR
            self._state = candidate
            return QuotaDecision.ALLOWED

    def _prune(self, state: _State, now: float) -> None:
        cutoff = now - self.settings.window_seconds
        state.global_events = [stamp for stamp in state.global_events if stamp > cutoff]
        state.sessions = {
            key: [stamp for stamp in stamps if stamp > cutoff]
            for key, stamps in state.sessions.items()
            if any(stamp > cutoff for stamp in stamps)
        }
        state.last_sent = {
            key: stamp for key, stamp in state.last_sent.items() if stamp > cutoff
        }

    def _load(self) -> _State:
        if not self.state_path.exists():
            return _State()
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            if data.get("version") != 1:
                raise ValueError("unsupported state version")
            return _State(
                global_events=[float(item) for item in data["global_events"]],
                sessions={
                    str(key): [float(item) for item in stamps]
                    for key, stamps in data["sessions"].items()
                },
                last_sent={str(key): float(value) for key, value in data["last_sent"].items()},
            )
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            quarantine = self.state_path.with_name(f"quota-state.corrupt-{stamp}.json")
            try:
                self.state_path.replace(quarantine)
            except OSError:
                pass
            return _State()

    def _save(self, state: _State) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".json.tmp")
        payload = {
            "version": 1,
            "global_events": state.global_events,
            "sessions": state.sessions,
            "last_sent": state.last_sent,
        }
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(temporary, self.state_path)
```

Do not add any logger call containing `session_key`, state JSON, or event data.

- [ ] **Step 4: Run GREEN and commit Task 2**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests\test_emote_quota.py -q
& .\.venv\Scripts\python.exe -m pytest tests\test_emote_settings_trigger.py tests\test_emote_quota.py -q
git diff --check
git add -- plugins\chihaya_emotes\quota.py tests\test_emote_quota.py
git diff --cached --check
git commit -m "feat: persist emote rolling quota"
```

Expected: all focused tests pass; the concurrent test reports exactly 10 allowed reservations.

---

### Task 3: Add image-pool selection and framework-neutral controller

**Files:**
- Create: `plugins/chihaya_emotes/image_pool.py`
- Create: `plugins/chihaya_emotes/controller.py`
- Create: `tests/test_emote_image_pool.py`
- Create: `tests/test_emote_controller.py`

**Interfaces:**
- Produces: `ImagePool.refresh() -> int`, `ImagePool.choose(session_key) -> Path | None`, and `ImagePool.discard(path) -> None`.
- Produces: `DirectReply(image: Path | None, text: str | None, stop_llm: bool)`.
- Produces: `EmoteController.direct(message_type, text, unified_msg_origin, is_self) -> Awaitable[DirectReply | None]`.
- Produces: `EmoteController.passive(unified_msg_origin) -> Awaitable[Path | None]`.

- [ ] **Step 1: Write failing pool and controller tests**

Create small nonempty byte fixtures with the supported extensions; this pool layer indexes files but does not decode image pixels. Assert that recursive scan accepts `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp` case-insensitively; ignores hidden/zero-byte/unsupported files; collapses byte-identical files by SHA-256; and avoids returning the previous path for the same session when at least two files exist. Actual decoding and WebP conversion are tested after Pillow is introduced in Task 5.

In `tests/test_emote_controller.py`, use a temporary pool and quota to assert:

```python
def test_direct_request_stops_llm_and_returns_image(controller) -> None:
    reply = run(controller.direct("group", "求你来只千早爱音", "umo-1", False))
    assert reply is not None
    assert reply.stop_llm is True
    assert reply.image is not None
    assert reply.text is None


def test_direct_limit_returns_local_joke(controller) -> None:
    first = run(controller.direct("private", "来只千早爱音", "umo-1", False))
    second = run(controller.direct("private", "来只千早爱音", "umo-1", False))
    assert first.image is not None
    assert second.image is None
    assert second.text in controller.limit_messages


def test_passive_probability_and_direct_request_share_quota(controller) -> None:
    assert run(controller.passive("umo-1")) is not None
    blocked = run(controller.direct("private", "来只千早爱音", "umo-1", False))
    assert blocked.image is None


def test_passive_failure_is_silent(controller_with_empty_pool) -> None:
    assert run(controller_with_empty_pool.passive("umo-1")) is None
```

Also test probability values just below and equal to `0.20`, empty-pool direct text, state-write failure, and a selected file disappearing before return.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests\test_emote_image_pool.py tests\test_emote_controller.py -q
```

Expected: imports fail for `image_pool` and `controller`.

- [ ] **Step 3: Implement digest-based image scanning and per-session selection**

In `plugins/chihaya_emotes/image_pool.py`, implement `SUPPORTED_SUFFIXES`, recursive scan with `Path.rglob("*")`, hidden-path and zero-byte rejection, chunked SHA-256, sorted canonical paths, a `_last_by_session` map, injected `random.Random`, one rescan after a missing-file selection, and `discard()` that removes only the exact resolved pool entry. Never follow directory symlinks or junctions during recursive discovery.

The selection core must be:

```python
def choose(self, session_key: str) -> Path | None:
    available = [path for path in self._paths if path.is_file()]
    if not available:
        self.refresh()
        available = [path for path in self._paths if path.is_file()]
    if not available:
        return None
    previous = self._last_by_session.get(session_key)
    candidates = [path for path in available if path != previous] or available
    chosen = self._rng.choice(candidates)
    self._last_by_session[session_key] = chosen
    return chosen
```

- [ ] **Step 4: Implement the controller and approved fallback text**

In `plugins/chihaya_emotes/controller.py`, define these fixed messages and keep the controller independent of AstrBot imports:

```python
from dataclasses import dataclass
from pathlib import Path
from random import Random

from .image_pool import ImagePool
from .quota import QuotaDecision, RollingQuota
from .settings import EmoteSettings
from .trigger import hash_session, matches_request


LIMIT_MESSAGES = (
    "没有啦，每小时只有三只",
    "每小时只有 3600s，你先省着点",
    "本小时爱音浓度已经超标",
    "三只已经越狱完了，下个整点再来",
    "库存 0 只，尊严也不多",
)


@dataclass(frozen=True)
class DirectReply:
    image: Path | None = None
    text: str | None = None
    stop_llm: bool = True


class EmoteController:
    def __init__(self, pool: ImagePool, quota: RollingQuota, settings: EmoteSettings, rng: Random) -> None:
        self.pool = pool
        self.quota = quota
        self.settings = settings
        self.rng = rng
        self.limit_messages = LIMIT_MESSAGES

    async def direct(self, message_type: str, text: str, umo: str, is_self: bool) -> DirectReply | None:
        if not matches_request(message_type, text, is_self=is_self):
            return None
        session_key = hash_session(umo)
        image = self.pool.choose(session_key)
        if image is None:
            return DirectReply(text="今天一只都没跑出来，图片库存好像空了")
        decision = await self.quota.reserve(session_key)
        if decision is QuotaDecision.ALLOWED:
            return DirectReply(image=image)
        if decision is QuotaDecision.STATE_ERROR:
            return DirectReply(text="今天的爱音库存记账失败了，先不乱发")
        return DirectReply(text=self.rng.choice(self.limit_messages))

    async def passive(self, umo: str) -> Path | None:
        session_key = hash_session(umo)
        image = self.pool.choose(session_key)
        if image is None:
            return None
        decision = await self.quota.reserve(
            session_key,
            gate=lambda: self.rng.random() < self.settings.chat_probability,
        )
        return image if decision is QuotaDecision.ALLOWED else None
```

If a chosen path disappears, discard it, refresh once, and repeat selection before quota reservation; never reserve for a path that is already missing.

- [ ] **Step 5: Run GREEN and commit Task 3**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests\test_emote_image_pool.py tests\test_emote_controller.py -q
& .\.venv\Scripts\python.exe -m pytest tests\test_emote_settings_trigger.py tests\test_emote_quota.py tests\test_emote_image_pool.py tests\test_emote_controller.py -q
git diff --check
git add -- plugins\chihaya_emotes\image_pool.py plugins\chihaya_emotes\controller.py tests\test_emote_image_pool.py tests\test_emote_controller.py
git diff --cached --check
git commit -m "feat: select and schedule emote images"
```

Expected: all emote-core tests pass and the commit contains no image binaries.

---

### Task 4: Add the thin AstrBot adapter and plugin configuration

**Files:**
- Create: `plugins/chihaya_emotes/main.py`
- Create: `plugins/chihaya_emotes/_conf_schema.json`
- Create: `plugins/chihaya_emotes/metadata.yaml`
- Create: `tests/test_emote_plugin_contract.py`

**Interfaces:**
- Consumes: `EmoteController`, `EmoteSettings`, `ImagePool`, and `RollingQuota` from Tasks 1–3.
- Produces: AstrBot class `ChihayaEmotes(Star)` with `on_message()` and `decorate_result()` handlers.

- [ ] **Step 1: Write failing adapter contracts**

Create `tests/test_emote_plugin_contract.py` to parse JSON/YAML as text and Python AST without requiring AstrBot in the repository virtualenv. Assert all of the following:

- `_conf_schema.json` has the five approved defaults and numeric types.
- `metadata.yaml` names the plugin `chihaya_emotes`, declares version `0.1.0`, and requires AstrBot `>=4.27.2`.
- `main.py` imports only AstrBot APIs plus the plugin package/standard library.
- `on_message` is registered for all message events, calls `event.should_call_llm(False)` before awaiting controller work for a matched request, returns a stopped result, and has no LLM request call. A controller failure on a matched request must still stay local and must not fall through to DeepSeek.
- `decorate_result` uses `@filter.on_decorating_result()`, checks `result.is_llm_result()`, rejects `result.async_stream`, and appends `Comp.Image.fromFileSystem` only after the controller returns a path.
- Both handlers restrict runtime work to the explicitly supported local-image platforms `aiocqhttp` and `webchat`; QQ/NapCat is the required live acceptance target, while WebChat remains automated-test-only for the first version.

- [ ] **Step 2: Run the adapter contract and verify RED**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests\test_emote_plugin_contract.py -q
```

Expected: failures report the three missing plugin files.

- [ ] **Step 3: Add metadata and WebUI configuration schema**

Create `metadata.yaml` with local-only metadata and `_conf_schema.json` with exactly these entries:

```json
{
  "chat_probability": {"description": "普通 LLM 回复附图概率", "type": "float", "default": 0.2},
  "session_cooldown_seconds": {"description": "同一会话发图冷却秒数", "type": "int", "default": 300},
  "session_hourly_limit": {"description": "滚动窗口内每会话图片上限", "type": "int", "default": 3},
  "global_hourly_limit": {"description": "滚动窗口内全局图片上限", "type": "int", "default": 10},
  "window_seconds": {"description": "滚动额度窗口秒数", "type": "int", "default": 3600}
}
```

Use this metadata:

```yaml
name: chihaya_emotes
display_name: 千早爱音随机表情包
desc: 本地随机发送千早爱音表情包，并为最终 LLM 回复低频附图。
version: 0.1.0
author: local
repo: https://github.com/jianhuowang/my_little_chat_robot
astrbot_version: ">=4.27.2"
support_platforms:
  - aiocqhttp
  - webchat
```

- [ ] **Step 4: Implement the AstrBot adapter**

Create `main.py` with one high-priority all-message listener and one decorating hook. Its constructor must call `super().__init__(context)`, validate `AstrBotConfig`, use `Path(__file__).resolve().parent / "emotes"`, and place state beside it as `quota-state.json`.

The handler bodies must follow this exact control flow:

```python
@filter.event_message_type(filter.EventMessageType.ALL, priority=1000)
async def on_message(self, event: AstrMessageEvent):
    if event.get_platform_name() not in {"aiocqhttp", "webchat"}:
        return
    kind = "private" if event.is_private_chat() else "group"
    is_self = event.get_sender_id() == event.get_self_id()
    if not matches_request(kind, event.message_str, is_self=is_self):
        return
    event.should_call_llm(False)
    try:
        reply = await self.controller.direct(
            kind,
            event.message_str,
            event.unified_msg_origin,
            is_self,
        )
    except Exception:
        logger.exception("Chihaya emote direct request failed", exc_info=False)
        yield event.plain_result("今天的爱音好像卡在门口了，晚点再来").stop_event()
        return
    if reply is None:
        yield event.plain_result("今天先不发图啦").stop_event()
        return
    if reply.image is not None:
        yield event.image_result(str(reply.image)).stop_event()
    else:
        yield event.plain_result(reply.text or "今天先不发图啦").stop_event()


@filter.on_decorating_result()
async def decorate_result(self, event: AstrMessageEvent) -> None:
    if event.get_platform_name() not in {"aiocqhttp", "webchat"}:
        return
    result = event.get_result()
    if result is None or not result.chain or not result.is_llm_result():
        return
    if result.async_stream is not None:
        return
    try:
        image = await self.controller.passive(event.unified_msg_origin)
    except Exception:
        logger.exception("Chihaya emote decoration failed", exc_info=False)
        return
    if image is not None:
        result.chain.append(Comp.Image.fromFileSystem(str(image)))
```

Import `matches_request` from the plugin trigger module. The fixed-message exception logging above deliberately disables exception detail so plugin failures cannot disclose paths or event data; a passive failure preserves the original LLM chain, while a matched direct request remains local and never falls through to DeepSeek.

- [ ] **Step 5: Run GREEN, compile the plugin, and commit Task 4**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests\test_emote_plugin_contract.py -q
& .\.venv\Scripts\python.exe -m compileall -q plugins\chihaya_emotes
& .\.venv\Scripts\python.exe -m pytest -q
git diff --check
git add -- plugins\chihaya_emotes\main.py plugins\chihaya_emotes\_conf_schema.json plugins\chihaya_emotes\metadata.yaml tests\test_emote_plugin_contract.py
git diff --cached --check
git commit -m "feat: integrate emotes with AstrBot"
```

Expected: the adapter contract, compilation, and full suite pass; no runtime file is staged.

---

### Task 5: Build the safe local asset installer

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/qq_deepseek_setup/cli.py`
- Create: `src/qq_deepseek_setup/emote_assets.py`
- Create: `scripts/Install-ChihayaEmotes.ps1`
- Create: `tests/test_emote_assets.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_powershell_wrappers.py`

**Interfaces:**
- Produces: `prepare_emotes(source_dirs: Sequence[Path], destination: Path, allowed_root: Path) -> AssetSummary`.
- Produces CLI: `qq-deepseek-setup install-emotes --source PATH [--source PATH ...] --destination PATH --allowed-root PATH`.
- Produces wrapper: `.\scripts\Install-ChihayaEmotes.ps1 -SourceDir PATH[,PATH] [-RuntimeDir runtime\astrbot]`.

- [ ] **Step 1: Add failing installer, CLI, and PowerShell safety tests**

Use Pillow to create one PNG, a byte-identical duplicate, and one WebP in temporary source trees. Call `prepare_emotes(source_dirs, destination, allowed_root)` and assert it writes two decodable files, names outputs by lowercase SHA-256 plus final extension, converts WebP to PNG, reports one duplicate, rejects a destination outside `allowed_root`, and never writes outside the destination.

Add CLI tests asserting missing source returns exit `2` with a path-safe error, and a successful run prints JSON containing only counts and the destination path—never source filenames.

Extend `tests/test_powershell_wrappers.py` to require that the new script:

- sets `$ErrorActionPreference = "Stop"`;
- resolves repository root and requires runtime destination to remain inside it;
- calls `Assert-NoReparsePoint` before copying;
- uses `Copy-Item -LiteralPath`, never wildcard source expansion;
- refuses a running AstrBot process whose command line points at the selected runtime;
- invokes the repository virtualenv CLI without printing source directory contents.

- [ ] **Step 2: Run the focused installer tests and verify RED**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests\test_emote_assets.py tests\test_cli.py tests\test_powershell_wrappers.py -q
```

Expected: failures identify the missing asset module, missing CLI command, and missing wrapper.

- [ ] **Step 3: Add Pillow only to repository installation dependencies**

Add `"Pillow>=11,<13"` to `[project].dependencies` in `pyproject.toml`, then refresh the lock and environment:

```powershell
& 'C:\Users\Lenovo\AppData\Roaming\Python\Python312\Scripts\uv.exe' lock
& 'C:\Users\Lenovo\AppData\Roaming\Python\Python312\Scripts\uv.exe' sync
```

Expected: lock succeeds and importing `PIL` works in `.venv`; no Pillow import is added under `plugins/chihaya_emotes`.

- [ ] **Step 4: Implement validated conversion into a staging directory**

In `emote_assets.py`, recursively enumerate only regular non-symlink files with supported suffixes. Resolve every source and destination, reject destination roots outside the caller-selected repository runtime boundary, open each image with Pillow and call `verify()`, convert WebP to RGB/RGBA PNG, copy other formats, and name each output `<sha256><lowercase-suffix>`.

Build the complete output under a sibling `emotes.staging-<uuid>` directory. On success, rename an existing `emotes` directory to `emotes.backup-<UTC timestamp>`, rename staging to `emotes`, and return:

```python
@dataclass(frozen=True)
class AssetSummary:
    discovered: int
    installed: int
    duplicates: int
    failed: int
    converted_webp: int
    destination: Path

    def to_public_dict(self) -> dict[str, object]:
        return {
            "discovered": self.discovered,
            "installed": self.installed,
            "duplicates": self.duplicates,
            "failed": self.failed,
            "converted_webp": self.converted_webp,
            "destination": str(self.destination),
        }
```

If any setup or rename fails, leave the prior `emotes` directory recoverable and remove only the explicitly created staging directory after verifying it remains the expected sibling. Never recursively delete a user-supplied source.

- [ ] **Step 5: Extend the CLI parser without breaking existing commands**

Replace the flat `choices` parser with subparsers for `preflight`, `balance`, `render-persona`, and `install-emotes`. The new command must require at least one repeated `--source`, one `--destination`, and one `--allowed-root`; pass all three values to `prepare_emotes()`; and print only `AssetSummary.to_public_dict()` as UTF-8 JSON. Preserve existing exit codes and public output for all three current commands.

- [ ] **Step 6: Implement the repository-bound PowerShell wrapper**

The wrapper must resolve `plugins\chihaya_emotes` and the selected `runtime\astrbot\data\plugins\chihaya_emotes`, validate both are beneath the repository root and not reparse points, require AstrBot to be stopped, copy only the committed plugin files using explicit paths, then invoke:

```powershell
& $python -m qq_deepseek_setup.cli install-emotes `
    @sourceArguments `
    --destination (Join-Path $pluginTarget "emotes")
```

The default source arguments used in the live deployment step are:

```powershell
-SourceDir @(
    'C:\Documents\ChatGPT\talk_robort\世一可爱千早爱音MyGO!!!!!【表情包】分享',
    'C:\Documents\ChatGPT\talk_robort\千早爱音表情包-补充'
)
```

Do not embed QQ identifiers, tokens, API keys, or user-profile temporary paths.

- [ ] **Step 7: Run GREEN and commit Task 5**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests\test_emote_assets.py tests\test_cli.py tests\test_powershell_wrappers.py -q
& .\.venv\Scripts\python.exe -m pytest -q
git diff --check
git add -- pyproject.toml uv.lock src\qq_deepseek_setup\cli.py src\qq_deepseek_setup\emote_assets.py scripts\Install-ChihayaEmotes.ps1 tests\test_emote_assets.py tests\test_cli.py tests\test_powershell_wrappers.py
git diff --cached --check
git commit -m "feat: install local emote assets"
```

Expected: focused and full suites pass; the staged diff contains no `.env`, runtime file, downloaded image, or secret.

---

### Task 6: Align repository contracts, deploy locally, and run live acceptance

**Files:**
- Modify: `tests/test_repository_contract.py`
- Modify: `docs/setup-windows.md`
- Modify: `docs/acceptance-checklist.md`
- Generate locally: `runtime/astrbot/data/plugins/chihaya_emotes/**` (Git ignored)

**Interfaces:**
- Consumes: all committed plugin and installer files from Tasks 1–5.
- Produces: tested runbook/contracts and a locally loaded AstrBot plugin; no new public Python API.

- [ ] **Step 1: Replace the obsolete “no sticker” repository contract with failing plugin contracts**

Update `test_acceptance_covers_roleplay_style_and_serious_topic_boundaries()` so it no longer asserts `表情包发送不属于第一版`. Add assertions requiring the runbook and acceptance checklist to mention all of these exact values and behaviors: `来只千早爱音`, no group At requirement, `20%`, `300` seconds, per-session `3`, global `10`, rolling `3600`, shared quota, direct requests bypass DeepSeek, runtime images ignored, and restart persistence.

- [ ] **Step 2: Run the repository contract and verify RED**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests\test_repository_contract.py -q
```

Expected: new documentation assertions fail until the runbook and acceptance checklist are updated.

- [ ] **Step 3: Document installation, configuration, and recovery**

Add a “千早爱音表情包插件” section to `docs/setup-windows.md` with these exact operations:

1. Fully stop AstrBot while leaving NapCat/QQ state untouched.
2. Run `Install-ChihayaEmotes.ps1` with the two approved source directories.
3. Verify the public JSON summary reports `discovered=133`, `failed=0`, and `installed>0`; the final installed number may be lower only if conversion reveals content-identical outputs.
4. Start AstrBot with the existing `Start-AstrBot.ps1` and reload/enable `chihaya_emotes` in WebUI.
5. Keep defaults `0.20`, `300`, `3`, `10`, and `3600`.
6. Explain that `quota-state.json`, `emotes`, and backup directories remain local and ignored.
7. Roll back by stopping AstrBot, moving the explicit current plugin directory aside, restoring the newest explicit backup, and restarting; never delete source folders.

- [ ] **Step 4: Add live acceptance probes**

Add checklist items for:

- private exact and optional-slash commands;
- group contains-match without At and self-message loop prevention;
- DeepSeek logs/token usage unchanged for direct commands;
- a direct second request during 300-second cooldown returning one approved joke;
- test-only temporary settings proving 3/session and 10/global rolling limits, followed by restoration of defaults;
- temporary `chat_probability=1.0` proving final LLM text plus image, followed by restoration to `0.20`;
- plugin reload and full AstrBot restart preserving quota;
- empty pool and malformed state degradation;
- listener verification on `127.0.0.1:6185`, `127.0.0.1:6199`, and `127.0.0.1:6099` only.

- [ ] **Step 5: Run repository and full automated verification**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests\test_repository_contract.py -q
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\python.exe -m compileall -q src plugins
$errors = @()
Get-ChildItem -LiteralPath scripts -Filter '*.ps1' | ForEach-Object {
    $tokens = $null
    $parseErrors = $null
    [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$tokens, [ref]$parseErrors) | Out-Null
    $errors += $parseErrors
}
if ($errors.Count -ne 0) { $errors | Format-List; exit 1 }
git diff --check
```

Expected: full pytest passes, Python compilation succeeds, every PowerShell script has zero parser errors, and diff check exits 0.

- [ ] **Step 6: Commit Task 6 documentation and contracts**

Run:

```powershell
git add -- tests\test_repository_contract.py docs\setup-windows.md docs\acceptance-checklist.md
git diff --cached --check
git commit -m "docs: add emote deployment runbook"
```

Expected: exactly three tracked files are committed.

- [ ] **Step 7: Install the local plugin and images**

After confirming AstrBot is stopped, run:

```powershell
.\scripts\Install-ChihayaEmotes.ps1 -SourceDir @(
    'C:\Documents\ChatGPT\talk_robort\世一可爱千早爱音MyGO!!!!!【表情包】分享',
    'C:\Documents\ChatGPT\talk_robort\千早爱音表情包-补充'
)
.\scripts\Start-AstrBot.ps1
```

Expected: the installer reports 133 discovered source images, zero failures, and a nonzero installed pool; AstrBot starts without a plugin load error. Do not print or inspect `.env` contents.

- [ ] **Step 8: Perform live QQ acceptance with user-controlled messages**

Ask the user to send the checklist probes from private chat and at least two QQ group/session contexts. Observe only safe AstrBot/NapCat log summaries. Do not send unsolicited QQ messages or change QQ account security settings. Restore all temporary quota/probability settings to defaults after testing.

- [ ] **Step 9: Final clean-state and secret verification**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest -q
git diff --check
git status --short
git ls-files runtime napcat .env
```

Expected: all tests pass; diff check is clean; `git status --short` is empty; `git ls-files` prints none of the local runtime, NapCat, `.env`, state, or image files. Report live acceptance separately from automated verification and do not create another commit unless a tested repository defect was corrected.

---

## Cost and Resource Expectations

- Direct command: zero DeepSeek requests and zero model tokens; one local JSON update, one local image read, and one QQ image upload.
- Passive attachment: no additional model request or token usage beyond the existing text reply; one local probability/quota decision and, on an allowed result, one image upload.
- Resident memory: plugin state is a few short timestamp lists plus at most the image-path/digest index for roughly 133 files; expected to remain in the low-megabyte range rather than loading image pixels into memory.
- Disk: committed code/tests are small; runtime disk use is approximately the source image total plus WebP-to-PNG expansion and one recoverable backup during upgrades.
- Network: at the approved global cap, at most 10 image uploads per rolling hour; actual traffic equals the encoded sizes of those images.
- Installation only: Pillow decodes one image at a time, so temporary CPU and memory use is bounded and ends when installation finishes.

## Primary AstrBot References

- Plugin message events and `on_decorating_result`: <https://docs.astrbot.app/dev/star/guides/listen-message-event.html>
- Local image results and message components: <https://docs.astrbot.app/dev/star/guides/send-message.html>
- Plugin configuration schema: <https://github.com/AstrBotDevs/AstrBot/wiki/en-dev-star-guides-plugin-config>
- Plugin metadata: <https://docs.astrbot.app/dev/star/plugin-publish.html>
