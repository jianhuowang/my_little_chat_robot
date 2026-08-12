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
