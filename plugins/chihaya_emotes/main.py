from pathlib import Path
from random import Random

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .controller import EmoteController
from .image_pool import ImagePool
from .quota import RollingQuota
from .settings import EmoteSettings
from .trigger import matches_request


class ChihayaEmotes(Star):
    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        if not isinstance(config, AstrBotConfig):
            raise TypeError("config must be an AstrBotConfig")

        settings = EmoteSettings.from_mapping(config, warn=logger.warning)
        rng = Random()
        image_root = Path(__file__).resolve().parent / "emotes"
        image_pool = ImagePool(image_root, rng)
        image_pool.refresh()
        quota = RollingQuota(image_root.parent / "quota-state.json", settings)
        self.controller = EmoteController(image_pool, quota, settings, rng)

    @filter.event_message_type(filter.EventMessageType.ALL, priority=1000)
    async def on_message(self, event: AstrMessageEvent):
        if event.get_platform_name() not in {"aiocqhttp", "webchat"}:
            return
        kind = "private" if event.is_private_chat() else "group"
        is_self = event.get_sender_id() == event.get_self_id()
        if not matches_request(kind, event.message_str, is_self=is_self):
            return
        event.should_call_llm(False)
        try:
            reply = await self.controller.direct(
                kind,
                event.message_str,
                event.unified_msg_origin,
                is_self,
            )
        except Exception:
            logger.exception("Chihaya emote direct request failed", exc_info=False)
            yield event.plain_result(
                "今天的爱音好像卡在门口了，晚点再来"
            ).stop_event()
            return
        if reply is None:
            yield event.plain_result("今天先不发图啦").stop_event()
            return
        if reply.image is not None:
            yield event.image_result(str(reply.image)).stop_event()
        else:
            yield event.plain_result(reply.text or "今天先不发图啦").stop_event()

    @filter.on_decorating_result()
    async def decorate_result(self, event: AstrMessageEvent) -> None:
        if event.get_platform_name() not in {"aiocqhttp", "webchat"}:
            return
        result = event.get_result()
        if result is None or not result.chain or not result.is_llm_result():
            return
        if result.async_stream is not None:
            return
        try:
            image = await self.controller.passive(event.unified_msg_origin)
        except Exception:
            logger.exception("Chihaya emote decoration failed", exc_info=False)
            return
        if image is not None:
            result.chain.append(Comp.Image.fromFileSystem(str(image)))
