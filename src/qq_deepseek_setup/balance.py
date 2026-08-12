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


def _balance_value(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    raise ValueError("invalid balance value")


def _parse_balance_payload(payload: object) -> BalanceStatus:
    if not isinstance(payload, dict):
        raise ValueError("invalid balance response")

    is_available = payload.get("is_available")
    balance_infos = payload.get("balance_infos")
    if not isinstance(is_available, bool) or not isinstance(balance_infos, list):
        raise ValueError("invalid balance response")

    infos = []
    for item in balance_infos:
        if not isinstance(item, dict) or not isinstance(item.get("currency"), str):
            raise ValueError("invalid balance response")
        infos.append(
            BalanceInfo(
                currency=item["currency"],
                total=_balance_value(item.get("total_balance")),
                granted=_balance_value(item.get("granted_balance")),
                topped_up=_balance_value(item.get("topped_up_balance")),
            )
        )
    return BalanceStatus(is_available, tuple(infos))


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
                return _parse_balance_payload(payload)
        except httpx.HTTPStatusError as exc:
            raise BalanceError(
                f"DeepSeek balance query failed ({exc.response.status_code})"
            ) from None
        except httpx.HTTPError:
            raise BalanceError("DeepSeek balance query failed (network)") from None
        except ValueError:
            raise BalanceError("DeepSeek balance query failed (invalid response)") from None
