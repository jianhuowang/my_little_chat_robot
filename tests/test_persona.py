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
    entries = [
        entry(f"meme-{index}", f"梗{index}", "2026-12-31")
        for index in range(21)
    ]
    write_sources(tmp_path, entries)

    with pytest.raises(PersonaRenderError, match="at most 20"):
        render_persona(tmp_path, today=date(2026, 8, 11))
