import pytest

from qq_deepseek_setup import preflight
from qq_deepseek_setup.preflight import TcpListener, run_preflight
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
        listener_records=lambda: (),
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
        listener_records=lambda: (
            TcpListener("127.0.0.1", 6099),
            TcpListener("127.0.0.1", 6185),
            TcpListener("127.0.0.1", 6199),
        ),
    )

    assert all(item.ok for item in results)


@pytest.mark.parametrize("unsafe_address", ("0.0.0.0", "::", "192.168.1.25"))
def test_preflight_rejects_wildcard_or_non_loopback_listener(
    tmp_path, unsafe_address: str
) -> None:
    runtime_dir = tmp_path / "astrbot"
    runtime_dir.mkdir()
    results = run_preflight(
        settings(str(runtime_dir)),
        which=lambda command: f"C:/tools/{command}.exe",
        listener_records=lambda: (
            TcpListener("127.0.0.1", 6099),
            TcpListener("127.0.0.1", 6185),
            TcpListener("127.0.0.1", 6199),
            TcpListener(unsafe_address, 6199),
        ),
    )

    onebot = next(item for item in results if item.name == "onebot-reverse-ws")
    assert onebot.ok is False
    assert unsafe_address in onebot.detail
    assert "non-loopback" in onebot.detail


@pytest.mark.parametrize("insufficient_address", ("::1", "127.0.0.2"))
def test_preflight_requires_literal_ipv4_loopback_listener(
    tmp_path, insufficient_address: str
) -> None:
    runtime_dir = tmp_path / "astrbot"
    runtime_dir.mkdir()
    results = run_preflight(
        settings(str(runtime_dir)),
        which=lambda command: f"C:/tools/{command}.exe",
        listener_records=lambda: (
            TcpListener("127.0.0.1", 6099),
            TcpListener("127.0.0.1", 6185),
            TcpListener(insufficient_address, 6199),
        ),
    )

    onebot = next(item for item in results if item.name == "onebot-reverse-ws")
    assert onebot.ok is False
    assert "127.0.0.1" in onebot.detail


def test_preflight_allows_ipv4_and_ipv6_loopback_listeners_together(tmp_path) -> None:
    runtime_dir = tmp_path / "astrbot"
    runtime_dir.mkdir()
    results = run_preflight(
        settings(str(runtime_dir)),
        which=lambda command: f"C:/tools/{command}.exe",
        listener_records=lambda: (
            TcpListener("127.0.0.1", 6099),
            TcpListener("127.0.0.1", 6185),
            TcpListener("127.0.0.1", 6199),
            TcpListener("::1", 6199),
        ),
    )

    assert all(item.ok for item in results)


def test_windows_tcp_listeners_parses_native_listener_inventory(monkeypatch) -> None:
    class Result:
        returncode = 0
        stdout = (
            '[{"LocalAddress":"127.0.0.1","LocalPort":6185},'
            '{"LocalAddress":"0.0.0.0","LocalPort":6199}]'
        )

    monkeypatch.setattr(preflight.shutil, "which", lambda _: "powershell.exe")
    monkeypatch.setattr(preflight.subprocess, "run", lambda *args, **kwargs: Result())

    assert preflight.windows_tcp_listeners() == (
        TcpListener("127.0.0.1", 6185),
        TcpListener("0.0.0.0", 6199),
    )
