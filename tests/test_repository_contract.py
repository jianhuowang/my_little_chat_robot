import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def policy() -> dict[str, object]:
    return json.loads(
        (ROOT / "config/astrbot-v1-checklist.json").read_text(encoding="utf-8")
    )


def test_committed_policy_matches_v1_design() -> None:
    policy_data = policy()

    assert policy_data["model"]["id"] == "deepseek-v4-flash"
    assert policy_data["model"]["max_tokens"] == 512
    assert policy_data["model"]["extra_body"] == {
        "thinking": {"type": "disabled"}
    }
    assert policy_data["model"]["max_context_length"] == 10
    assert policy_data["model"]["dequeue_context_length"] == 1
    assert policy_data["platform"]["unique_session"] is False
    assert policy_data["platform"]["group_requires_mention_or_wake"] is True
    assert policy_data["platform"]["friend_message_needs_wake_prefix"] is False
    assert policy_data["platform"]["rate_limit"] == {
        "time": 60,
        "count": 5,
        "strategy": "discard",
    }
    assert policy_data["platform"]["ignore_bot_self_message"] is True
    assert policy_data["features"] == {
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
    assert "DEEPSEEK_API_KEY=replace-with-your-local-key" in (
        ROOT / ".env.example"
    ).read_text(encoding="utf-8")


def test_all_required_listeners_are_explicitly_loopback_only() -> None:
    policy_data = policy()

    assert policy_data["onebot"]["astrbot_host"] == "127.0.0.1"
    assert policy_data["onebot"]["astrbot_port"] == 6199
    assert (
        policy_data["onebot"]["napcat_reverse_ws_url"]
        == "ws://127.0.0.1:6199/ws"
    )
    assert policy_data["management"] == {
        "astrbot_webui_host": "127.0.0.1",
        "astrbot_webui_port": 6185,
        "napcat_webui_host": "127.0.0.1",
        "napcat_webui_port": 6099,
    }


def test_astrbot_version_and_persisted_model_config_are_exact() -> None:
    policy_data = policy()

    assert policy_data["astrbot"]["minimum_version"] == "4.13.0"
    assert policy_data["model"]["cmd_config_provider_model_config"] == {
        "model": "deepseek-v4-flash",
        "max_tokens": 512,
        "extra_body": {"thinking": {"type": "disabled"}},
    }


def test_runbook_has_two_window_first_run_and_persistence_checks() -> None:
    runbook = (ROOT / "docs/setup-windows.md").read_text(encoding="utf-8")

    assert "AstrBot 版本必须为 `4.13.0` 或更高" in runbook
    assert "专用 PowerShell 窗口" in runbook
    assert "第二个 PowerShell 窗口" in runbook
    assert "data/cmd_config.json" in runbook
    assert '"model_config"' in runbook
    assert '"extra_body"' in runbook
    assert "保存并重启 AstrBot" in runbook
    assert "不要显示或复制 `key`" in runbook


def test_acceptance_checks_the_precise_ten_round_eviction_boundary() -> None:
    acceptance = (ROOT / "docs/acceptance-checklist.md").read_text(encoding="utf-8")

    assert "FACT-01" in acceptance
    assert "FACT-12" in acceptance
    assert "第 11 轮" in acceptance
    assert "FACT-01" in acceptance and "FACT-02" in acceptance
    assert "第 12 轮" in acceptance
    assert "配置和会话历史" in acceptance
