from pathlib import Path

import pytest

from qq_deepseek_setup.settings import Settings


def test_settings_require_a_non_placeholder_api_key() -> None:
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        Settings.from_mapping({"DEEPSEEK_API_KEY": "replace-with-your-local-key"})


def test_settings_apply_safe_defaults() -> None:
    settings = Settings.from_mapping({"DEEPSEEK_API_KEY": "sk-test-secret"})

    assert settings.deepseek_base_url == "https://api.deepseek.com"
    assert settings.astrbot_runtime_dir == Path("runtime/astrbot")
    assert settings.masked_key == "sk-t...cret"


def test_settings_never_reveals_a_short_key_when_masked() -> None:
    secret = "short"

    settings = Settings.from_mapping({"DEEPSEEK_API_KEY": secret})

    assert settings.masked_key == "****"
    assert secret not in settings.masked_key


def test_settings_error_never_contains_the_secret() -> None:
    secret = "sk-super-sensitive-value"

    with pytest.raises(ValueError) as exc_info:
        Settings.from_mapping(
            {"DEEPSEEK_API_KEY": secret, "DEEPSEEK_BASE_URL": "ftp://invalid"}
        )

    assert secret not in str(exc_info.value)


def test_settings_rejects_a_malformed_https_port() -> None:
    with pytest.raises(ValueError, match="DEEPSEEK_BASE_URL"):
        Settings.from_mapping(
            {
                "DEEPSEEK_API_KEY": "sk-test-secret",
                "DEEPSEEK_BASE_URL": "https://api.deepseek.com:not-a-port",
            }
        )


def test_settings_loads_values_from_the_root_env_file(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "DEEPSEEK_API_KEY=sk-loaded-secret\nASTRBOT_RUNTIME_DIR=custom/runtime\n",
        encoding="utf-8",
    )

    settings = Settings.load(tmp_path)

    assert settings.deepseek_api_key == "sk-loaded-secret"
    assert settings.astrbot_runtime_dir == Path("custom/runtime")
