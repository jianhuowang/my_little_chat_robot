import json

import pytest

from qq_deepseek_setup import cli
from qq_deepseek_setup.balance import BalanceInfo, BalanceStatus


def test_balance_command_prints_only_public_json(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "DEEPSEEK_API_KEY=sk-test-secret\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        cli.BalanceClient,
        "get",
        lambda _self: BalanceStatus(
            True, (BalanceInfo("CNY", "5.00", "0", "5.00"),)
        ),
    )

    exit_code = cli.main(["balance"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert json.loads(output)["balances"][0]["total"] == "5.00"
    assert "sk-test-secret" not in output


def test_unknown_command_returns_nonzero() -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["unknown"])

    assert exc_info.value.code != 0
