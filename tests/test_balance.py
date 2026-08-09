import httpx
import pytest

from qq_deepseek_setup.balance import BalanceClient, BalanceError
from qq_deepseek_setup.settings import Settings


def make_settings() -> Settings:
    return Settings.from_mapping({"DEEPSEEK_API_KEY": "sk-test-secret"})


def test_balance_client_parses_public_balance_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/user/balance"
        assert request.headers["Authorization"] == "Bearer sk-test-secret"
        return httpx.Response(
            200,
            json={
                "is_available": True,
                "balance_infos": [
                    {
                        "currency": "CNY",
                        "total_balance": "10.00",
                        "granted_balance": "0.00",
                        "topped_up_balance": "10.00",
                    }
                ],
            },
        )

    status = BalanceClient(make_settings(), httpx.MockTransport(handler)).get()

    assert status.is_available is True
    assert status.to_public_dict()["balances"][0]["total"] == "10.00"


def test_balance_error_does_not_leak_the_key() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    with pytest.raises(BalanceError) as exc_info:
        BalanceClient(make_settings(), httpx.MockTransport(handler)).get()

    assert "sk-test-secret" not in str(exc_info.value)
    assert "401" in str(exc_info.value)
