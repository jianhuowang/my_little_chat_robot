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
        state.global_events = [
            stamp for stamp in state.global_events if stamp > cutoff
        ]
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
                last_sent={
                    str(key): float(value)
                    for key, value in data["last_sent"].items()
                },
            )
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            quarantine = self.state_path.with_name(
                f"quota-state.corrupt-{stamp}.json"
            )
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
