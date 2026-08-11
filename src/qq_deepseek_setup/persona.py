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
