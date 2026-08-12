from __future__ import annotations

import asyncio
import json
import os
import re
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from math import isfinite
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


_SESSION_KEY_PATTERN = re.compile(r"[0-9a-f]{64}")


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
            return self._validate_state(data, self.clock())
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

    @staticmethod
    def _validate_state(data: object, now: float) -> _State:
        if not isinstance(data, dict):
            raise ValueError("invalid state structure")
        if type(data.get("version")) is not int or data["version"] != 1:
            raise ValueError("unsupported state version")
        global_events = data["global_events"]
        sessions = data["sessions"]
        last_sent = data["last_sent"]
        if (
            not isinstance(global_events, list)
            or not isinstance(sessions, dict)
            or not isinstance(last_sent, dict)
        ):
            raise ValueError("invalid state structure")

        def validate_stamp(stamp: object) -> float:
            if (
                isinstance(stamp, bool)
                or not isinstance(stamp, (int, float))
                or (isinstance(stamp, float) and not isfinite(stamp))
                or not 0 <= stamp <= now
            ):
                raise ValueError("invalid timestamp")
            return float(stamp)

        validated_global = [validate_stamp(stamp) for stamp in global_events]
        validated_sessions: dict[str, list[float]] = {}
        for key, stamps in sessions.items():
            if (
                not isinstance(key, str)
                or _SESSION_KEY_PATTERN.fullmatch(key) is None
                or not isinstance(stamps, list)
                or not stamps
            ):
                raise ValueError("invalid session state")
            validated_sessions[key] = [validate_stamp(stamp) for stamp in stamps]

        validated_last_sent: dict[str, float] = {}
        for key, stamp in last_sent.items():
            if (
                not isinstance(key, str)
                or _SESSION_KEY_PATTERN.fullmatch(key) is None
            ):
                raise ValueError("invalid last-sent state")
            validated_last_sent[key] = validate_stamp(stamp)

        if set(validated_sessions) != set(validated_last_sent):
            raise ValueError("inconsistent session keys")
        if any(
            validated_last_sent[key] != max(stamps)
            for key, stamps in validated_sessions.items()
        ):
            raise ValueError("inconsistent last-sent state")
        session_events = [
            stamp for stamps in validated_sessions.values() for stamp in stamps
        ]
        if Counter(validated_global) != Counter(session_events):
            raise ValueError("inconsistent global events")

        return _State(validated_global, validated_sessions, validated_last_sent)

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
