from qq_deepseek_setup.preflight import run_preflight
from qq_deepseek_setup.settings import Settings


def settings(runtime_dir: str = "runtime/astrbot") -> Settings:
    return Settings.from_mapping(
        {
            "DEEPSEEK_API_KEY": "sk-test-secret",
            "ASTRBOT_RUNTIME_DIR": runtime_dir,
        }
    )


def test_preflight_reports_missing_astrbot() -> None:
    results = run_preflight(
        settings(),
        which=lambda _: None,
        port_is_listening=lambda _host, _port: False,
    )

    astrbot = next(item for item in results if item.name == "astrbot")
    assert astrbot.ok is False
    assert "not found" in astrbot.detail


def test_preflight_recognizes_running_local_services(tmp_path) -> None:
    runtime_dir = tmp_path / "astrbot"
    runtime_dir.mkdir()
    results = run_preflight(
        settings(str(runtime_dir)),
        which=lambda command: f"C:/tools/{command}.exe",
        port_is_listening=lambda _host, port: port in {6185, 6199, 6099},
    )

    assert all(item.ok for item in results)
