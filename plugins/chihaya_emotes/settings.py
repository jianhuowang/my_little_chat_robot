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
                "global_hourly_limit", defaults.global_hourly_limit),
            window_seconds=positive_int("window_seconds", defaults.window_seconds),
        )
        if candidate.session_hourly_limit > candidate.global_hourly_limit:
            warn("Invalid quota relationship; using approved defaults")
            return defaults
        return candidate
