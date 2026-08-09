import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_committed_policy_matches_v1_design() -> None:
    policy = json.loads((ROOT / "config/astrbot-v1-checklist.json").read_text(encoding="utf-8"))

    assert policy["model"]["id"] == "deepseek-v4-flash"
    assert policy["model"]["max_tokens"] == 512
    assert policy["model"]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert policy["model"]["max_context_length"] == 10
    assert policy["model"]["dequeue_context_length"] == 1
    assert policy["platform"]["unique_session"] is False
    assert policy["platform"]["group_requires_mention_or_wake"] is True
    assert policy["platform"]["friend_message_needs_wake_prefix"] is False
    assert policy["platform"]["rate_limit"] == {"time": 60, "count": 5, "strategy": "discard"}
    assert policy["platform"]["ignore_bot_self_message"] is True
    assert policy["features"] == {
        "active_reply": False,
        "image_caption": False,
        "stt": False,
        "tts": False,
        "tools": False,
        "web_search": False,
    }


def test_repository_ignores_real_env_file() -> None:
    ignore_lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert ".env" in ignore_lines
    assert "DEEPSEEK_API_KEY=replace-with-your-local-key" in (ROOT / ".env.example").read_text(encoding="utf-8")
