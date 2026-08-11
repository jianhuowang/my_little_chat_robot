from dataclasses import dataclass
from pathlib import Path
from random import Random

from .image_pool import ImagePool
from .quota import QuotaDecision, RollingQuota
from .settings import EmoteSettings
from .trigger import hash_session, matches_request


LIMIT_MESSAGES = (
    "没有啦，每小时只有三只",
    "每小时只有 3600s，你先省着点",
    "本小时爱音浓度已经超标",
    "三只已经越狱完了，下个整点再来",
    "库存 0 只，尊严也不多",
)


@dataclass(frozen=True)
class DirectReply:
    image: Path | None = None
    text: str | None = None
    stop_llm: bool = True


class EmoteController:
    def __init__(
        self,
        pool: ImagePool,
        quota: RollingQuota,
        settings: EmoteSettings,
        rng: Random,
    ) -> None:
        self.pool = pool
        self.quota = quota
        self.settings = settings
        self.rng = rng
        self.limit_messages = LIMIT_MESSAGES

    async def direct(
        self,
        message_type: str,
        text: str,
        umo: str,
        is_self: bool,
    ) -> DirectReply | None:
        if not matches_request(message_type, text, is_self=is_self):
            return None
        session_key = hash_session(umo)
        image = self._choose_existing(session_key)
        if image is None:
            return DirectReply(text="今天一只都没跑出来，图片库存好像空了")
        decision = await self.quota.reserve(session_key)
        if decision is QuotaDecision.ALLOWED:
            return DirectReply(image=image)
        if decision is QuotaDecision.STATE_ERROR:
            return DirectReply(text="今天的爱音库存记账失败了，先不乱发")
        return DirectReply(text=self.rng.choice(self.limit_messages))

    async def passive(self, umo: str) -> Path | None:
        session_key = hash_session(umo)
        image = self._choose_existing(session_key)
        if image is None:
            return None
        decision = await self.quota.reserve(
            session_key,
            gate=lambda: self.rng.random() < self.settings.chat_probability,
        )
        return image if decision is QuotaDecision.ALLOWED else None

    def _choose_existing(self, session_key: str) -> Path | None:
        image = self.pool.choose(session_key)
        if image is None:
            return None
        if image.is_file():
            return image

        self.pool.discard(image)
        if self.pool.refresh() == 0:
            return None
        replacement = self.pool.choose(session_key)
        if replacement is None or not replacement.is_file():
            if replacement is not None:
                self.pool.discard(replacement)
            return None
        return replacement
