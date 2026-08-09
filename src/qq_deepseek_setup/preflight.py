from __future__ import annotations

import ipaddress
import json
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from .settings import Settings


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class TcpListener:
    address: str
    port: int


class ListenerQueryError(RuntimeError):
    pass


def windows_tcp_listeners() -> tuple[TcpListener, ...]:
    powershell = shutil.which("powershell")
    if powershell is None:
        raise ListenerQueryError("PowerShell is required to inspect TCP listeners")

    command = (
        "$ErrorActionPreference = 'Stop'; "
        "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false); "
        "Get-NetTCPConnection -State Listen -ErrorAction Stop | "
        "Where-Object { $_.LocalPort -in 6099, 6185, 6199 } | "
        "Select-Object LocalAddress, LocalPort | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ListenerQueryError("Unable to inspect TCP listeners") from exc
    if result.returncode != 0:
        raise ListenerQueryError("Unable to inspect TCP listeners")
    if not result.stdout.strip():
        return ()

    try:
        payload = json.loads(result.stdout)
        rows = payload if isinstance(payload, list) else [payload]
        if not all(isinstance(row, dict) for row in rows):
            raise ValueError
        return tuple(
            TcpListener(str(row["LocalAddress"]), int(row["LocalPort"]))
            for row in rows
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ListenerQueryError("Unable to inspect TCP listeners") from exc


def _is_loopback(address: str) -> bool:
    try:
        return ipaddress.ip_address(address.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def run_preflight(
    settings: Settings,
    which: Callable[[str], str | None] = shutil.which,
    listener_records: Callable[[], tuple[TcpListener, ...]] = windows_tcp_listeners,
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
    required_listeners = (
        ("astrbot-webui", 6185),
        ("onebot-reverse-ws", 6199),
        ("napcat-webui", 6099),
    )
    try:
        listeners = listener_records()
    except ListenerQueryError:
        for name, port in required_listeners:
            results.append(
                CheckResult(name, False, f"unable to inspect listeners on port {port}")
            )
        return tuple(results)

    for name, port in required_listeners:
        addresses = sorted(
            {listener.address for listener in listeners if listener.port == port}
        )
        unsafe = [address for address in addresses if not _is_loopback(address)]
        if unsafe:
            results.append(
                CheckResult(
                    name,
                    False,
                    f"non-loopback listener(s) on port {port}: {', '.join(unsafe)}",
                )
            )
        elif not addresses:
            results.append(CheckResult(name, False, f"no listener found on port {port}"))
        elif "127.0.0.1" not in addresses:
            results.append(
                CheckResult(
                    name,
                    False,
                    f"required listener 127.0.0.1:{port} not found; "
                    f"found: {', '.join(addresses) or 'none'}",
                )
            )
        else:
            results.append(
                CheckResult(
                    name,
                    True,
                    f"loopback listener(s) on port {port}: {', '.join(addresses)}",
                )
            )
    return tuple(results)
