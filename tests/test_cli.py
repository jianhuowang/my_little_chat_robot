import json
from pathlib import Path

import pytest

from qq_deepseek_setup import cli
from qq_deepseek_setup.balance import BalanceInfo, BalanceStatus
from qq_deepseek_setup.persona import PersonaRenderResult


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


def test_render_persona_command_does_not_require_env(
    monkeypatch, capsys, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "runtime" / "persona" / "astrbot-persona.txt"
    monkeypatch.setattr(
        cli,
        "render_persona",
        lambda root: PersonaRenderResult(output, 15, 0, "abc123"),
        raising=False,
    )

    exit_code = cli.main(["render-persona"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload == {
        "output_path": str(output),
        "active_count": 15,
        "expired_count": 0,
        "sha256": "abc123",
    }
    assert not (tmp_path / ".env").exists()


def test_render_persona_error_returns_two(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)

    def fail(_root: Path):
        raise cli.PersonaRenderError("invalid meme lexicon")

    monkeypatch.setattr(cli, "render_persona", fail, raising=False)

    assert cli.main(["render-persona"]) == 2
    assert capsys.readouterr().out.strip() == "ERROR: invalid meme lexicon"
