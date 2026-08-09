from __future__ import annotations

from dataclasses import dataclass

import httpx

from .settings import Settings


class BalanceError(RuntimeError):
    pass


@dataclass(frozen=True)
class BalanceInfo:
    currency: str
    total: str
    granted: str
    topped_up: str


@dataclass(frozen=True)
class BalanceStatus:
    is_available: bool
    balances: tuple[BalanceInfo, ...]

    def to_public_dict(self) -> dict[str, object]:
        return {
            "is_available": self.is_available,
            "balances": [
                {
                    "currency": item.currency,
                    "total": item.total,
                    "granted": item.granted,
                    "topped_up": item.topped_up,
                }
                for item in self.balances
            ],
        }


class BalanceClient:
    def __init__(
        self, settings: Settings, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.settings = settings
        self.transport = transport

    def get(self) -> BalanceStatus:
        try:
            with httpx.Client(
                base_url=self.settings.deepseek_base_url,
                headers={"Authorization": f"Bearer {self.settings.deepseek_api_key}"},
                timeout=15,
                transport=self.transport,
            ) as client:
                response = client.get("/user/balance")
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            status = (
                exc.response.status_code
                if isinstance(exc, httpx.HTTPStatusError)
                else "network"
            )
            raise BalanceError(f"DeepSeek balance query failed ({status})") from None

        infos = tuple(
            BalanceInfo(
                currency=str(item["currency"]),
                total=str(item["total_balance"]),
                granted=str(item["granted_balance"]),
                topped_up=str(item["topped_up_balance"]),
            )
            for item in payload.get("balance_infos", [])
        )
        return BalanceStatus(bool(payload.get("is_available")), infos)
