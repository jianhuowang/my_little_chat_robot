import asyncio
import hashlib
import json

from plugins.chihaya_emotes import quota as quota_module
from plugins.chihaya_emotes.quota import QuotaDecision, RollingQuota
from plugins.chihaya_emotes.settings import EmoteSettings


def run(coro):
    return asyncio.run(coro)


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
    first = RollingQuota(path, EmoteSettings(), lambda: 1_000.0)
    assert run(first.reserve("hashed-session")) is QuotaDecision.ALLOWED
    assert "hashed-session" in path.read_text(encoding="utf-8")
    second = RollingQuota(path, EmoteSettings(), lambda: 1_001.0)
    assert run(second.reserve("hashed-session")) is QuotaDecision.COOLDOWN


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
