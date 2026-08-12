import json
import re
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
    context_check = acceptance.split("- [ ] **上下文边界**：", 1)[1].split(
        "\n- [ ]", 1
    )[0]

    steps = {
        int(number): text
        for number, text in re.findall(r"^  (\d+)\. (.+)$", context_check, re.MULTILINE)
    }
    facts = lambda step: set(re.findall(r"FACT-\d{2}", steps[step]))

    assert set(steps) == set(range(1, 7))
    assert "第 1–10 轮" in steps[2]
    assert {"FACT-01", "FACT-10"} <= facts(2)
    assert "只确认已记录" in steps[2]
    assert "不得复述任何 FACT 编号或事实值" in steps[2]
    assert facts(3) == {"FACT-01", "FACT-11"}
    assert "只询问" in steps[3]
    assert "不能回答" in steps[3]
    assert facts(4) == {"FACT-02", "FACT-03", "FACT-12"}
    assert "只询问" in steps[4]
    assert "应淘汰项" in steps[4]
    assert "应保留的对照项" in steps[4]
    assert facts(5) == {"FACT-01", "FACT-02", "FACT-03"}
    assert "第 11 轮不能回答" in steps[5]
    assert "第 12 轮不能回答" in steps[5]
    assert "必须正确回答保留的对照项" in steps[5]
    assert "只列出当前上下文中仍存在的 FACT 编号" not in context_check
    assert "模型行为作为主证据" in steps[6]
    assert "配置和会话历史只能作为佐证" in steps[6]


def test_persona_sources_and_runtime_boundary_are_committed() -> None:
    base = (ROOT / "config/persona-base.txt").read_text(encoding="utf-8")
    lexicon = json.loads(
        (ROOT / "config/meme-lexicon.json").read_text(encoding="utf-8")
    )
    ignore_lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "直接扮演千早爱音" in base
    assert "日常回复默认控制在 1–3 句" in base
    assert "优先自然使用一个热梗" in base
    assert "不得把未被对方明确表达" in base
    assert "最多提出一个自然的追问" in base
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
    assert "直接扮演千早爱音" in runbook
    assert "只有被直接询问身份时才说明自己是 AI" not in runbook


def test_acceptance_covers_roleplay_style_and_serious_topic_boundaries() -> None:
    acceptance = (ROOT / "docs/acceptance-checklist.md").read_text(encoding="utf-8")
    runbook = (ROOT / "docs/setup-windows.md").read_text(encoding="utf-8")

    assert "千早爱音角色人格" in acceptance
    assert "默认 1–3 句" in acceptance
    assert "不得擅自分析对方心理" in acceptance
    assert "严肃求助不玩梗" in acceptance

    required_emote_contract = (
        "来只千早爱音",
        "无需 @",
        "20%",
        "300 秒",
        "每会话 `3`",
        "全局 `10`",
        "3600 秒",
        "共享额度",
        "不调用 DeepSeek",
        "运行时图片",
        "Git 忽略",
        "重启后仍保留",
    )
    for document in (runbook, acceptance):
        for contract_item in required_emote_contract:
            assert contract_item in document
