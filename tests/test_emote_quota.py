import asyncio
import hashlib
import json

import pytest

from plugins.chihaya_emotes import quota as quota_module
from plugins.chihaya_emotes.quota import QuotaDecision, RollingQuota
from plugins.chihaya_emotes.settings import EmoteSettings


SESSION_KEY = "a" * 64
NEXT_SESSION_KEY = "b" * 64


def run(coro):
    return asyncio.run(coro)


def valid_state(*stamps: float) -> dict:
    events = list(stamps)
    return {
        "version": 1,
        "global_events": events,
        "sessions": {SESSION_KEY: events},
        "last_sent": {SESSION_KEY: max(events)},
    }


def assert_state_is_quarantined_and_replaced(tmp_path, invalid_state) -> None:
    path = tmp_path / "quota-state.json"
    path.write_text(json.dumps(invalid_state), encoding="utf-8")

    quota = RollingQuota(path, EmoteSettings(), lambda: 1_000.0)

    assert run(quota.reserve(NEXT_SESSION_KEY)) is QuotaDecision.ALLOWED
    assert len(list(tmp_path.glob("quota-state.corrupt-*.json"))) == 1
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["global_events"] == [1_000.0]
    assert payload["sessions"] == {NEXT_SESSION_KEY: [1_000.0]}
    assert payload["last_sent"] == {NEXT_SESSION_KEY: 1_000.0}


def test_cooldown_and_rolling_expiry(tmp_path) -> None:
    now = [1_000.0]
    quota = RollingQuota(tmp_path / "quota-state.json", EmoteSettings(), lambda: now[0])
    assert run(quota.reserve("a")) is QuotaDecision.ALLOWED
    assert run(quota.reserve("a")) is QuotaDecision.COOLDOWN
    now[0] += 300
    assert run(quota.reserve("a")) is QuotaDecision.ALLOWED
    now[0] += 300
    assert run(quota.reserve("a")) is QuotaDecision.ALLOWED
    now[0] += 300
    assert run(quota.reserve("a")) is QuotaDecision.SESSION_LIMIT
    now[0] = 4_600.0
    assert run(quota.reserve("a")) is QuotaDecision.ALLOWED


def test_probability_gate_does_not_consume_quota(tmp_path) -> None:
    quota = RollingQuota(tmp_path / "quota-state.json", EmoteSettings(), lambda: 1_000.0)
    assert run(quota.reserve("a", gate=lambda: False)) is QuotaDecision.PROBABILITY
    assert run(quota.reserve("a")) is QuotaDecision.ALLOWED


def test_restart_restores_state_without_plain_session_id(tmp_path) -> None:
    path = tmp_path / "quota-state.json"
    session_key = hashlib.sha256(b"private-session").hexdigest()
    first = RollingQuota(path, EmoteSettings(), lambda: 1_000.0)
    assert run(first.reserve(session_key)) is QuotaDecision.ALLOWED
    assert session_key in path.read_text(encoding="utf-8")
    second = RollingQuota(path, EmoteSettings(), lambda: 1_001.0)
    assert run(second.reserve(session_key)) is QuotaDecision.COOLDOWN


def test_concurrent_sessions_never_exceed_global_limit(tmp_path) -> None:
    settings = EmoteSettings(session_cooldown_seconds=1, session_hourly_limit=10)
    quota = RollingQuota(tmp_path / "quota-state.json", settings, lambda: 1_000.0)

    async def reserve_all():
        return await asyncio.gather(
            *(quota.reserve(f"s{index}") for index in range(20))
        )

    results = run(reserve_all())
    assert results.count(QuotaDecision.ALLOWED) == 10
    assert results.count(QuotaDecision.GLOBAL_LIMIT) == 10


def test_corrupt_state_is_quarantined(tmp_path) -> None:
    path = tmp_path / "quota-state.json"
    path.write_text("not-json", encoding="utf-8")
    quota = RollingQuota(path, EmoteSettings(), lambda: 1_000.0)
    assert run(quota.reserve("a")) is QuotaDecision.ALLOWED
    assert len(list(tmp_path.glob("quota-state.corrupt-*.json"))) == 1
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1


@pytest.mark.parametrize(
    "invalid_state",
    [
        [],
        {
            "version": 1,
            "global_events": [],
            "sessions": [],
            "last_sent": {},
        },
    ],
    ids=["root-array", "sessions-array"],
)
def test_invalid_state_structure_is_quarantined_and_recovers(
    tmp_path, invalid_state
) -> None:
    path = tmp_path / "quota-state.json"
    path.write_text(json.dumps(invalid_state), encoding="utf-8")

    quota = RollingQuota(path, EmoteSettings(), lambda: 1_000.0)

    assert run(quota.reserve("a")) is QuotaDecision.ALLOWED
    assert len(list(tmp_path.glob("quota-state.corrupt-*.json"))) == 1
    assert json.loads(path.read_text(encoding="utf-8"))["sessions"] == {
        "a": [1_000.0]
    }


@pytest.mark.parametrize(
    "invalid_stamp",
    [float("nan"), float("inf"), True],
    ids=["nan", "infinity", "boolean"],
)
def test_non_finite_or_boolean_timestamp_quarantines_whole_state(
    tmp_path, invalid_stamp
) -> None:
    assert_state_is_quarantined_and_replaced(tmp_path, valid_state(invalid_stamp))


@pytest.mark.parametrize(
    "invalid_stamp",
    [-1.0, 1_000.001],
    ids=["negative", "future"],
)
def test_out_of_range_timestamp_quarantines_whole_state(
    tmp_path, invalid_stamp
) -> None:
    assert_state_is_quarantined_and_replaced(tmp_path, valid_state(invalid_stamp))


@pytest.mark.parametrize(
    "invalid_key",
    ["A" * 64, "a" * 63, "g" * 64],
    ids=["uppercase", "wrong-length", "non-hex"],
)
def test_invalid_session_or_last_sent_key_quarantines_whole_state(
    tmp_path, invalid_key
) -> None:
    invalid_state = valid_state(900.0)
    invalid_state["sessions"] = {invalid_key: [900.0]}
    invalid_state["last_sent"] = {invalid_key: 900.0}

    assert_state_is_quarantined_and_replaced(tmp_path, invalid_state)


def test_global_events_multiset_mismatch_quarantines_whole_state(tmp_path) -> None:
    invalid_state = valid_state(800.0, 900.0)
    invalid_state["global_events"] = [800.0, 800.0]

    assert_state_is_quarantined_and_replaced(tmp_path, invalid_state)


@pytest.mark.parametrize(
    "invalid_state",
    [
        {
            "version": 1,
            "global_events": [],
            "sessions": {SESSION_KEY: []},
            "last_sent": {SESSION_KEY: 900.0},
        },
        {
            "version": 1,
            "global_events": [900.0],
            "sessions": {SESSION_KEY: [900.0]},
            "last_sent": {NEXT_SESSION_KEY: 900.0},
        },
        {
            "version": 1,
            "global_events": [800.0, 900.0],
            "sessions": {SESSION_KEY: [800.0, 900.0]},
            "last_sent": {SESSION_KEY: 800.0},
        },
    ],
    ids=["empty-session", "last-sent-key-mismatch", "last-sent-not-maximum"],
)
def test_inconsistent_session_metadata_quarantines_whole_state(
    tmp_path, invalid_state
) -> None:
    assert_state_is_quarantined_and_replaced(tmp_path, invalid_state)


def test_third_session_reservation_is_allowed_at_exact_limit(tmp_path) -> None:
    now = [1_000.0]
    quota = RollingQuota(tmp_path / "quota-state.json", EmoteSettings(), lambda: now[0])

    for _ in range(3):
        assert run(quota.reserve("a")) is QuotaDecision.ALLOWED
        now[0] += 300

    assert run(quota.reserve("a")) is QuotaDecision.SESSION_LIMIT


def test_exact_global_tenth_reservation_is_allowed(tmp_path) -> None:
    quota = RollingQuota(tmp_path / "quota-state.json", EmoteSettings(), lambda: 1_000.0)

    for index in range(10):
        assert run(quota.reserve(f"s{index}")) is QuotaDecision.ALLOWED

    assert run(quota.reserve("s10")) is QuotaDecision.GLOBAL_LIMIT


def test_atomic_write_failure_does_not_change_in_memory_counts(
    tmp_path, monkeypatch
) -> None:
    now = [1_000.0]
    quota = RollingQuota(tmp_path / "quota-state.json", EmoteSettings(), lambda: now[0])
    assert run(quota.reserve("a")) is QuotaDecision.ALLOWED
    now[0] += 300
    original_replace = quota_module.os.replace

    def fail_replace(_source, _destination) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr(quota_module.os, "replace", fail_replace)
    assert run(quota.reserve("a")) is QuotaDecision.STATE_ERROR
    persisted = json.loads((tmp_path / "quota-state.json").read_text(encoding="utf-8"))
    assert persisted["sessions"] == {"a": [1_000.0]}

    monkeypatch.setattr(quota_module.os, "replace", original_replace)
    assert run(quota.reserve("a")) is QuotaDecision.ALLOWED
    now[0] += 300
    assert run(quota.reserve("a")) is QuotaDecision.ALLOWED
    now[0] += 300
    assert run(quota.reserve("a")) is QuotaDecision.SESSION_LIMIT


def test_persisted_json_contains_only_timestamps_and_hashed_session_keys(
    tmp_path,
) -> None:
    raw_session_id = "aiocqhttp:GroupMessage:private-value"
    session_key = hashlib.sha256(raw_session_id.encode("utf-8")).hexdigest()
    path = tmp_path / "quota-state.json"
    quota = RollingQuota(path, EmoteSettings(), lambda: 1_000.0)

    assert run(quota.reserve(session_key)) is QuotaDecision.ALLOWED

    text = path.read_text(encoding="utf-8")
    payload = json.loads(text)
    assert raw_session_id not in text
    assert set(payload) == {"version", "global_events", "sessions", "last_sent"}
    assert payload["version"] == 1
    assert payload["global_events"] == [1_000.0]
    assert payload["sessions"] == {session_key: [1_000.0]}
    assert payload["last_sent"] == {session_key: 1_000.0}
