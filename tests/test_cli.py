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


def test_install_emotes_missing_source_returns_two_without_listing_contents(
    capsys, tmp_path
) -> None:
    missing = tmp_path / "private-source-name"
    destination = tmp_path / "runtime" / "emotes"

    exit_code = cli.main(
        [
            "install-emotes",
            "--source",
            str(missing),
            "--destination",
            str(destination),
            "--allowed-root",
            str(tmp_path / "runtime"),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 2
    assert output.startswith("ERROR: source directory does not exist")
    assert "secret" not in output.lower()


def test_install_emotes_prints_only_public_summary(monkeypatch, capsys, tmp_path) -> None:
    from qq_deepseek_setup.emote_assets import AssetSummary

    source = tmp_path / "private-source-name"
    destination = tmp_path / "runtime" / "emotes"
    allowed_root = tmp_path / "runtime"
    source.mkdir()
    expected = AssetSummary(3, 2, 1, 0, 1, destination)
    received = {}

    def fake_prepare(source_dirs, selected_destination, selected_root):
        received["args"] = (source_dirs, selected_destination, selected_root)
        return expected

    monkeypatch.setattr(cli, "prepare_emotes", fake_prepare, raising=False)

    exit_code = cli.main(
        [
            "install-emotes",
            "--source",
            str(source),
            "--destination",
            str(destination),
            "--allowed-root",
            str(allowed_root),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert received["args"] == ([source], destination, allowed_root)
    assert json.loads(output) == expected.to_public_dict()
    assert source.name not in output


def test_install_emotes_filesystem_failure_returns_fixed_public_error(
    monkeypatch, capsys, tmp_path
) -> None:
    private_path = tmp_path / "private-source-name" / "secret.png"

    def fail_prepare(_source_dirs, _destination, _allowed_root):
        raise OSError(f"access denied: {private_path}")

    monkeypatch.setattr(cli, "prepare_emotes", fail_prepare)

    exit_code = cli.main(
        [
            "install-emotes",
            "--source",
            str(tmp_path / "source"),
            "--destination",
            str(tmp_path / "destination"),
            "--allowed-root",
            str(tmp_path),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 2
    assert output == "ERROR: unable to install emotes due to a filesystem error\n"
    assert str(private_path) not in output
    assert "access denied" not in output


@pytest.mark.parametrize("command", ["preflight", "balance", "render-persona"])
def test_existing_commands_reject_install_emote_options(command: str) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main([command, "--source", "unexpected"])

    assert exc_info.value.code == 2
