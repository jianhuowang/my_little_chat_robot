from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

from dotenv import dotenv_values


PLACEHOLDER_KEYS = {"", "replace-with-your-local-key", "your-api-key"}


@dataclass(frozen=True)
class Settings:
    deepseek_api_key: str
    deepseek_base_url: str
    astrbot_runtime_dir: Path

    @classmethod
    def from_mapping(cls, values: Mapping[str, str | None]) -> "Settings":
        key = (values.get("DEEPSEEK_API_KEY") or "").strip()
        if key in PLACEHOLDER_KEYS:
            raise ValueError("DEEPSEEK_API_KEY is missing or still uses the example value")

        base_url = (values.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/")
        parsed = urlparse(base_url)
        try:
            port = parsed.port
        except ValueError:
            port = None
            valid_port = False
        else:
            valid_port = port is None or 0 < port <= 65535
        if parsed.scheme != "https" or not parsed.hostname or not valid_port:
            raise ValueError("DEEPSEEK_BASE_URL must be a valid HTTPS URL")

        runtime = Path(values.get("ASTRBOT_RUNTIME_DIR") or "runtime/astrbot")
        return cls(key, base_url, runtime)

    @classmethod
    def load(cls, root: Path) -> "Settings":
        return cls.from_mapping(dotenv_values(root / ".env"))

    @property
    def masked_key(self) -> str:
        if len(self.deepseek_api_key) <= 8:
            return "****"
        return f"{self.deepseek_api_key[:4]}...{self.deepseek_api_key[-4:]}"
