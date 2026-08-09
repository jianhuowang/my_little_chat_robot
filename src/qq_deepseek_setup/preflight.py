from __future__ import annotations

import shutil
import socket
from collections.abc import Callable
from dataclasses import dataclass

from .settings import Settings


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def socket_port_is_listening(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def run_preflight(
    settings: Settings,
    which: Callable[[str], str | None] = shutil.which,
    port_is_listening: Callable[[str, int], bool] = socket_port_is_listening,
) -> tuple[CheckResult, ...]:
    astrbot_path = which("astrbot")
    results = [
        CheckResult(
            "astrbot",
            astrbot_path is not None,
            astrbot_path or "astrbot executable not found",
        ),
        CheckResult(
            "runtime",
            settings.astrbot_runtime_dir.exists(),
            str(settings.astrbot_runtime_dir),
        ),
    ]
    for name, port in (
        ("astrbot-webui", 6185),
        ("onebot-reverse-ws", 6199),
        ("napcat-webui", 6099),
    ):
        listening = port_is_listening("127.0.0.1", port)
        results.append(CheckResult(name, listening, f"127.0.0.1:{port}"))
    return tuple(results)
