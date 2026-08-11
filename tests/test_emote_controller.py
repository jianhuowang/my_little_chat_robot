import asyncio
from pathlib import Path
from random import Random

import pytest

from plugins.chihaya_emotes.controller import EmoteController
from plugins.chihaya_emotes.image_pool import ImagePool
from plugins.chihaya_emotes.quota import RollingQuota
from plugins.chihaya_emotes.settings import EmoteSettings


def run(coro):
    return asyncio.run(coro)


class FixedRandom(Random):
    def __init__(self, probability: float = 0.0) -> None:
        super().__init__(0)
        self.probability = probability

    def random(self) -> float:
        return self.probability


def make_controller(
    tmp_path: Path,
    *,
    probability: float = 0.0,
    with_image: bool = True,
) -> EmoteController:
    image_root = tmp_path / "images"
    image_root.mkdir()
    if with_image:
        (image_root / "emote.png").write_bytes(b"emote")
    settings = EmoteSettings(
        chat_probability=0.20,
        session_cooldown_seconds=300,
        session_hourly_limit=1,
        global_hourly_limit=10,
    )
    pool = ImagePool(image_root, Random(0))
    pool.refresh()
    quota = RollingQuota(tmp_path / "quota-state.json", settings, lambda: 1_000.0)
    return EmoteController(pool, quota, settings, FixedRandom(probability))


@pytest.fixture
def controller(tmp_path) -> EmoteController:
    return make_controller(tmp_path)


@pytest.fixture
def controller_with_empty_pool(tmp_path) -> EmoteController:
    return make_controller(tmp_path, with_image=False)


def test_direct_request_stops_llm_and_returns_image(controller) -> None:
    reply = run(controller.direct("group", "求你来只千早爱音", "umo-1", False))
    assert reply is not None
    assert reply.stop_llm is True
    assert reply.image is not None
    assert reply.text is None


def test_direct_limit_returns_local_joke(controller) -> None:
    first = run(controller.direct("private", "来只千早爱音", "umo-1", False))
    second = run(controller.direct("private", "来只千早爱音", "umo-1", False))
    assert first is not None
    assert first.image is not None
    assert second is not None
    assert second.image is None
    assert second.text in controller.limit_messages


def test_passive_probability_and_direct_request_share_quota(controller) -> None:
    assert run(controller.passive("umo-1")) is not None
    blocked = run(controller.direct("private", "来只千早爱音", "umo-1", False))
    assert blocked is not None
    assert blocked.image is None


def test_passive_failure_is_silent(controller_with_empty_pool) -> None:
    assert run(controller_with_empty_pool.passive("umo-1")) is None


@pytest.mark.parametrize(
    ("sample", "is_sent"),
    [(0.199999, True), (0.20, False)],
    ids=["just-below", "equal"],
)
def test_passive_probability_uses_strict_less_than_boundary(
    tmp_path, sample, is_sent
) -> None:
    controller = make_controller(tmp_path, probability=sample)

    assert (run(controller.passive("umo-1")) is not None) is is_sent


def test_empty_pool_direct_returns_approved_text(controller_with_empty_pool) -> None:
    reply = run(
        controller_with_empty_pool.direct(
            "private", "来只千早爱音", "umo-1", False
        )
    )

    assert reply is not None
    assert reply.image is None
    assert reply.text == "今天一只都没跑出来，图片库存好像空了"
    assert reply.stop_llm is True


def test_direct_state_write_failure_returns_approved_text(
    controller, monkeypatch
) -> None:
    def fail_save(_state) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr(controller.quota, "_save", fail_save)

    reply = run(controller.direct("private", "来只千早爱音", "umo-1", False))

    assert reply is not None
    assert reply.image is None
    assert reply.text == "今天的爱音库存记账失败了，先不乱发"


def test_passive_state_write_failure_is_silent(controller, monkeypatch) -> None:
    def fail_save(_state) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr(controller.quota, "_save", fail_save)

    assert run(controller.passive("umo-1")) is None


def test_disappearing_selected_file_is_retried_before_reserving_quota(
    controller, monkeypatch
) -> None:
    original_choose = controller.pool.choose
    removed = [False]

    def choose_then_remove(session_key: str):
        selected = original_choose(session_key)
        if selected is not None and not removed[0]:
            selected.unlink()
            removed[0] = True
        return selected

    monkeypatch.setattr(controller.pool, "choose", choose_then_remove)

    missing = run(controller.direct("private", "来只千早爱音", "umo-1", False))
    assert missing is not None
    assert missing.image is None
    assert missing.text == "今天一只都没跑出来，图片库存好像空了"

    replacement = controller.pool.root / "replacement.png"
    replacement.write_bytes(b"replacement")
    available = run(controller.direct("private", "来只千早爱音", "umo-1", False))
    assert available is not None
    assert available.image == replacement.resolve()


def test_direct_ignores_non_requests_and_self_messages(controller) -> None:
    assert run(controller.direct("private", "普通消息", "umo-1", False)) is None
    assert run(controller.direct("group", "来只千早爱音", "umo-1", True)) is None
