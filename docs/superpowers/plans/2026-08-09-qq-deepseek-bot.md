# QQ DeepSeek Bot V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a secret-safe Windows deployment kit that runs AstrBot with NapCatQQ and the official DeepSeek V4 Flash API, with explicit low-cost settings and repeatable verification.

**Architecture:** NapCatQQ connects the QQ small account to AstrBot through a reverse OneBot v11 WebSocket at `ws://127.0.0.1:6199/ws`. AstrBot owns triggers, session history, rate limiting, and the LLM conversation; it calls `deepseek-v4-flash` through the official OpenAI-compatible endpoint. This repository provides configuration contracts, safe launch/check scripts, a balance client, tests, and runbooks, but does not proxy model traffic or automate QQ login.

**Tech Stack:** Windows PowerShell 5.1+, Python 3.12 managed by `uv`, pytest, httpx, python-dotenv, AstrBot CLI, NapCatQQ OneBot v11, DeepSeek API.

## Global Constraints

- Host operating system is Windows; all user-facing commands use PowerShell syntax.
- Use a dedicated QQ small account through NapCatQQ; QQ login remains a manual QR-code action.
- Use only `deepseek-v4-flash`; do not install Ollama or configure a fallback model.
- Set DeepSeek thinking to disabled with `{"thinking":{"type":"disabled"}}`.
- Cap a generated reply at 512 tokens.
- Keep at most 10 conversation rounds with `provider_settings.max_context_length=10` and discard one oldest round at a time with `provider_settings.dequeue_context_length=1`.
- Group chat requires an `@` mention or configured wake word; private chat responds without a wake prefix.
- Keep group members in one shared group context by leaving `platform_settings.unique_session` disabled.
- Set AstrBot rate limiting to 5 messages per 60 seconds with discard strategy.
- Ignore messages sent by the bot itself; disable proactive replies, web search, tools, image captioning, STT, and TTS.
- Keep real secrets in `.env`; commit only `.env.example`.
- Use a small manually topped-up DeepSeek balance; V1 has no local API gateway, hard daily cap, automatic renewal, or custom retry layer.
- Bind management and OneBot ports to localhost wherever supported; do not expose them to the public internet.

---

## File Structure

- `pyproject.toml`: Python runtime and test dependencies plus pytest configuration.
- `.gitignore`: excludes `.env`, virtual environments, caches, and generated AstrBot/NapCat runtime data.
- `.env.example`: names the required local variables without containing usable credentials.
- `src/qq_deepseek_setup/settings.py`: loads and validates local settings.
- `src/qq_deepseek_setup/balance.py`: queries the official DeepSeek balance endpoint.
- `src/qq_deepseek_setup/preflight.py`: checks dependencies, ports, and local configuration.
- `src/qq_deepseek_setup/cli.py`: exposes `preflight` and `balance` commands.
- `config/astrbot-v1-checklist.json`: machine-readable target values for WebUI configuration and review.
- `scripts/Initialize-AstrBot.ps1`: initializes the ignored AstrBot runtime directory.
- `scripts/Start-AstrBot.ps1`: loads `.env` into the current process and launches AstrBot without printing secrets.
- `scripts/Test-Prerequisites.ps1`: invokes the Python preflight command.
- `scripts/Get-DeepSeekBalance.ps1`: invokes the balance command.
- `tests/test_settings.py`: tests required settings and secret-safe failures.
- `tests/test_balance.py`: tests balance parsing and safe HTTP failures.
- `tests/test_preflight.py`: tests dependency and port checks.
- `tests/test_cli.py`: tests command exit behavior and secret-safe public output.
- `tests/test_repository_contract.py`: verifies secret exclusions and the committed configuration contract.
- `docs/setup-windows.md`: exact install, login, WebUI, and start instructions.
- `docs/acceptance-checklist.md`: end-to-end manual verification procedure.

---

### Task 1: Secret-safe settings contract

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `src/qq_deepseek_setup/__init__.py`
- Create: `src/qq_deepseek_setup/settings.py`
- Create: `tests/test_settings.py`

**Interfaces:**
- Consumes: a mapping with `DEEPSEEK_API_KEY`, optional `DEEPSEEK_BASE_URL`, and optional `ASTRBOT_RUNTIME_DIR`.
- Produces: `Settings.from_mapping(values: Mapping[str, str]) -> Settings` and `Settings.load(root: Path) -> Settings`.

- [ ] **Step 1: Create the package/test configuration and write the failing settings tests**

Create `pyproject.toml`:

```toml
[project]
name = "qq-deepseek-setup"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "httpx>=0.28,<1",
  "python-dotenv>=1.0,<2",
]

[dependency-groups]
dev = ["pytest>=8.3,<9"]

[project.scripts]
qq-deepseek-setup = "qq_deepseek_setup.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/qq_deepseek_setup"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

Create `.gitignore`:

```gitignore
.env
.venv/
__pycache__/
.pytest_cache/
*.py[cod]
runtime/
data/
logs/
napcat/
```

Create `.env.example`:

```dotenv
DEEPSEEK_API_KEY=replace-with-your-local-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
ASTRBOT_RUNTIME_DIR=runtime/astrbot
```

Create `src/qq_deepseek_setup/__init__.py` as an empty file and create `tests/test_settings.py`:

```python
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


def test_settings_error_never_contains_the_secret() -> None:
    secret = "sk-super-sensitive-value"

    with pytest.raises(ValueError) as exc_info:
        Settings.from_mapping(
            {"DEEPSEEK_API_KEY": secret, "DEEPSEEK_BASE_URL": "ftp://invalid"}
        )

    assert secret not in str(exc_info.value)
```

- [ ] **Step 2: Install dependencies and verify the test fails for the missing module**

Run:

```powershell
uv sync --dev
uv run pytest tests/test_settings.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'qq_deepseek_setup.settings'`.

- [ ] **Step 3: Implement the minimal settings loader**

Create `src/qq_deepseek_setup/settings.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

from dotenv import dotenv_values


PLACEHOLDER_KEYS = {"", "replace-with-your-local-key", "your-api-key"}


@dataclass(frozen=True)
class Settings:
    deepseek_api_key: str
    deepseek_base_url: str
    astrbot_runtime_dir: Path

    @classmethod
    def from_mapping(cls, values: Mapping[str, str | None]) -> "Settings":
        key = (values.get("DEEPSEEK_API_KEY") or "").strip()
        if key in PLACEHOLDER_KEYS:
            raise ValueError("DEEPSEEK_API_KEY is missing or still uses the example value")

        base_url = (values.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/")
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("DEEPSEEK_BASE_URL must be a valid HTTPS URL")

        runtime = Path(values.get("ASTRBOT_RUNTIME_DIR") or "runtime/astrbot")
        return cls(key, base_url, runtime)

    @classmethod
    def load(cls, root: Path) -> "Settings":
        return cls.from_mapping(dotenv_values(root / ".env"))

    @property
    def masked_key(self) -> str:
        return f"{self.deepseek_api_key[:4]}...{self.deepseek_api_key[-4:]}"
```

- [ ] **Step 4: Run the settings tests and the complete test suite**

Run:

```powershell
uv run pytest tests/test_settings.py -q
uv run pytest -q
```

Expected: `3 passed` for the focused test and all collected tests pass.

- [ ] **Step 5: Commit the settings contract**

```powershell
git add -- pyproject.toml .gitignore .env.example src/qq_deepseek_setup/__init__.py src/qq_deepseek_setup/settings.py tests/test_settings.py
git commit -m "feat: add secret-safe bot settings"
```

---

### Task 2: DeepSeek balance query

**Files:**
- Create: `src/qq_deepseek_setup/balance.py`
- Create: `tests/test_balance.py`

**Interfaces:**
- Consumes: `Settings.deepseek_api_key`, `Settings.deepseek_base_url`, and an optional `httpx.BaseTransport` for tests.
- Produces: `BalanceClient.get() -> BalanceStatus`; `BalanceStatus.to_public_dict() -> dict[str, object]` never exposes a key.

- [ ] **Step 1: Write the failing balance client tests**

Create `tests/test_balance.py`:

```python
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
```

- [ ] **Step 2: Run the balance tests and verify they fail because the module is missing**

```powershell
uv run pytest tests/test_balance.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'qq_deepseek_setup.balance'`.

- [ ] **Step 3: Implement the balance client**

Create `src/qq_deepseek_setup/balance.py`:

```python
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
        except (httpx.HTTPError, ValueError) as exc:
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else "network"
            raise BalanceError(f"DeepSeek balance query failed ({status})") from None

        infos = tuple(
            BalanceInfo(
                currency=str(item["currency"]),
                total=str(item["total_balance"]),
                granted=str(item["granted_balance"]),
                topped_up=str(item["topped_up_balance"]),
            )
            for item in payload.get("balance_infos", [])
        )
        return BalanceStatus(bool(payload.get("is_available")), infos)
```

- [ ] **Step 4: Run focused and full tests**

```powershell
uv run pytest tests/test_balance.py -q
uv run pytest -q
```

Expected: `2 passed` for the focused test and all tests pass.

- [ ] **Step 5: Commit the balance client**

```powershell
git add -- src/qq_deepseek_setup/balance.py tests/test_balance.py
git commit -m "feat: add safe DeepSeek balance query"
```

---

### Task 3: Dependency and port preflight

**Files:**
- Create: `src/qq_deepseek_setup/preflight.py`
- Create: `tests/test_preflight.py`

**Interfaces:**
- Consumes: `Settings`, `shutil.which`, and a socket probe supplied through constructor injection.
- Produces: `run_preflight(settings, which, port_is_listening) -> tuple[CheckResult, ...]`.

- [ ] **Step 1: Write the failing preflight tests**

Create `tests/test_preflight.py`:

```python
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
```

- [ ] **Step 2: Run the preflight tests and verify the missing-module failure**

```powershell
uv run pytest tests/test_preflight.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'qq_deepseek_setup.preflight'`.

- [ ] **Step 3: Implement deterministic preflight checks**

Create `src/qq_deepseek_setup/preflight.py`:

```python
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
    for name, port in (("astrbot-webui", 6185), ("onebot-reverse-ws", 6199), ("napcat-webui", 6099)):
        listening = port_is_listening("127.0.0.1", port)
        results.append(CheckResult(name, listening, f"127.0.0.1:{port}"))
    return tuple(results)
```

- [ ] **Step 4: Run focused and full tests**

```powershell
uv run pytest tests/test_preflight.py -q
uv run pytest -q
```

Expected: `2 passed` for the focused test and all tests pass.

- [ ] **Step 5: Commit the preflight domain logic**

```powershell
git add -- src/qq_deepseek_setup/preflight.py tests/test_preflight.py
git commit -m "feat: add bot deployment preflight checks"
```

---

### Task 4: CLI and Windows PowerShell wrappers

**Files:**
- Create: `src/qq_deepseek_setup/cli.py`
- Create: `tests/test_cli.py`
- Create: `scripts/Initialize-AstrBot.ps1`
- Create: `scripts/Start-AstrBot.ps1`
- Create: `scripts/Test-Prerequisites.ps1`
- Create: `scripts/Get-DeepSeekBalance.ps1`

**Interfaces:**
- Consumes: repository root, `.env`, `Settings`, `BalanceClient`, and `run_preflight`.
- Produces: `qq-deepseek-setup preflight` and `qq-deepseek-setup balance`; all failures use nonzero process exit codes.

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli.py`:

```python
import json

import pytest

from qq_deepseek_setup import cli
from qq_deepseek_setup.balance import BalanceInfo, BalanceStatus


def test_balance_command_prints_only_public_json(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=sk-test-secret\n", encoding="utf-8")
    monkeypatch.setattr(
        cli.BalanceClient,
        "get",
        lambda _self: BalanceStatus(True, (BalanceInfo("CNY", "5.00", "0", "5.00"),)),
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
```

- [ ] **Step 2: Run the CLI tests and verify the expected import failure**

```powershell
uv run pytest tests/test_cli.py -q
```

Expected: collection fails because `qq_deepseek_setup.cli` does not exist.

- [ ] **Step 3: Implement the CLI**

Create `src/qq_deepseek_setup/cli.py`:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .balance import BalanceClient, BalanceError
from .preflight import run_preflight
from .settings import Settings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qq-deepseek-setup")
    parser.add_argument("command", choices=("preflight", "balance"))
    args = parser.parse_args(argv)

    try:
        settings = Settings.load(Path.cwd())
        if args.command == "balance":
            print(json.dumps(BalanceClient(settings).get().to_public_dict(), ensure_ascii=False))
            return 0

        results = run_preflight(settings)
        for item in results:
            marker = "OK" if item.ok else "FAIL"
            print(f"[{marker}] {item.name}: {item.detail}")
        return 0 if all(item.ok for item in results) else 1
    except (ValueError, BalanceError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run CLI tests and verify public output**

```powershell
uv run pytest tests/test_cli.py -q
uv run pytest -q
```

Expected: `2 passed` for the focused test and all tests pass.

- [ ] **Step 5: Add short, inspectable PowerShell wrappers**

Create `scripts/Initialize-AstrBot.ps1`:

```powershell
param([string]$RuntimeDir = "runtime\astrbot")
$ErrorActionPreference = "Stop"
$resolvedRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$target = [System.IO.Path]::GetFullPath((Join-Path $resolvedRoot $RuntimeDir))
if (-not $target.StartsWith($resolvedRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "RuntimeDir must stay inside the repository"
}
New-Item -ItemType Directory -Path $target -Force | Out-Null
Push-Location $target
try {
    astrbot init
} finally {
    Pop-Location
}
```

Create `scripts/Start-AstrBot.ps1`:

```powershell
$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$envFile = Join-Path $repoRoot ".env"
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) { throw ".env is missing" }
Get-Content -LiteralPath $envFile -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]*)=(.*)$') {
        [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
    }
}
$runtimeDir = if ($env:ASTRBOT_RUNTIME_DIR) { $env:ASTRBOT_RUNTIME_DIR } else { "runtime\astrbot" }
$target = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $runtimeDir))
if (-not $target.StartsWith($repoRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "ASTRBOT_RUNTIME_DIR must stay inside the repository"
}
if (-not (Test-Path -LiteralPath $target -PathType Container)) { throw "AstrBot runtime is not initialized" }
Push-Location $target
try {
    astrbot run
} finally {
    Pop-Location
}
```

Create `scripts/Test-Prerequisites.ps1`:

```powershell
$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $repoRoot
try {
    uv run qq-deepseek-setup preflight
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $exitCode
```

Create `scripts/Get-DeepSeekBalance.ps1`:

```powershell
$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $repoRoot
try {
    uv run qq-deepseek-setup balance
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $exitCode
```

- [ ] **Step 6: Parse-check all PowerShell scripts and run all Python tests**

```powershell
$errors = $null
Get-ChildItem -LiteralPath scripts -Filter *.ps1 | ForEach-Object {
    [void][System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$null, [ref]$errors)
    if ($errors) { $errors; exit 1 }
}
uv run pytest -q
```

Expected: no parser errors and all tests pass.

- [ ] **Step 7: Commit CLI and Windows wrappers**

```powershell
git add -- src/qq_deepseek_setup/cli.py tests/test_cli.py scripts
git commit -m "feat: add Windows bot setup commands"
```

---

### Task 5: AstrBot configuration contract and Windows runbook

**Files:**
- Create: `config/astrbot-v1-checklist.json`
- Create: `tests/test_repository_contract.py`
- Create: `docs/setup-windows.md`
- Create: `docs/acceptance-checklist.md`
- Create: `README.md`

**Interfaces:**
- Consumes: the official AstrBot WebUI, NapCat WebUI, `.env`, and scripts from Task 4.
- Produces: a reviewable checklist with exact target values and a complete manual acceptance flow.

- [ ] **Step 1: Write the failing repository contract tests**

Create `tests/test_repository_contract.py`:

```python
import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_committed_policy_matches_v1_design() -> None:
    policy = json.loads((ROOT / "config/astrbot-v1-checklist.json").read_text(encoding="utf-8"))

    assert policy["model"]["id"] == "deepseek-v4-flash"
    assert policy["model"]["max_tokens"] == 512
    assert policy["model"]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert policy["model"]["max_context_length"] == 10
    assert policy["model"]["dequeue_context_length"] == 1
    assert policy["platform"]["unique_session"] is False
    assert policy["platform"]["group_requires_mention_or_wake"] is True
    assert policy["platform"]["friend_message_needs_wake_prefix"] is False
    assert policy["platform"]["rate_limit"] == {"time": 60, "count": 5, "strategy": "discard"}
    assert policy["platform"]["ignore_bot_self_message"] is True
    assert policy["features"] == {
        "active_reply": False,
        "image_caption": False,
        "stt": False,
        "tts": False,
        "tools": False,
        "web_search": False,
    }


def test_repository_ignores_real_env_file() -> None:
    ignore_lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert ".env" in ignore_lines
    assert "DEEPSEEK_API_KEY=replace-with-your-local-key" in (ROOT / ".env.example").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run the repository contract tests and verify the missing-file failure**

```powershell
uv run pytest tests/test_repository_contract.py -q
```

Expected: fails with `FileNotFoundError` for `config/astrbot-v1-checklist.json`.

- [ ] **Step 3: Add the machine-readable configuration checklist**

Create `config/astrbot-v1-checklist.json`:

```json
{
  "onebot": {
    "astrbot_host": "0.0.0.0",
    "astrbot_port": 6199,
    "napcat_reverse_ws_url": "ws://127.0.0.1:6199/ws",
    "token_must_match": true
  },
  "management": {
    "astrbot_webui_host": "127.0.0.1",
    "astrbot_webui_port": 6185,
    "napcat_webui_local_only": true,
    "napcat_webui_port": 6099
  },
  "model": {
    "provider": "DeepSeek official or OpenAI-compatible",
    "base_url": "https://api.deepseek.com/v1",
    "api_key_field": "$DEEPSEEK_API_KEY",
    "id": "deepseek-v4-flash",
    "max_tokens": 512,
    "max_context_length": 10,
    "dequeue_context_length": 1,
    "extra_body": {"thinking": {"type": "disabled"}}
  },
  "platform": {
    "unique_session": false,
    "group_requires_mention_or_wake": true,
    "friend_message_needs_wake_prefix": false,
    "ignore_bot_self_message": true,
    "rate_limit": {"time": 60, "count": 5, "strategy": "discard"}
  },
  "features": {
    "active_reply": false,
    "image_caption": false,
    "stt": false,
    "tts": false,
    "tools": false,
    "web_search": false
  }
}
```

- [ ] **Step 4: Write the Windows setup runbook**

Create `docs/setup-windows.md` with these exact sections and commands:

```markdown
# Windows 安装与配置

## 1. 准备 DeepSeek

1. 在 DeepSeek 开放平台创建 API Key，只充值可接受损失的小额余额。
2. 在项目根目录复制示例文件：

   ```powershell
   Copy-Item -LiteralPath .env.example -Destination .env
   notepad .env
   ```

3. 只在本机 `.env` 中替换 `DEEPSEEK_API_KEY`。

## 2. 安装 uv 和 AstrBot

在 PowerShell 中确认 `uv` 可用；若未安装，使用 Windows Package Manager：

```powershell
winget install --id astral-sh.uv -e
uv tool install astrbot --python 3.12
where.exe astrbot
astrbot --version
```

初始化运行目录：

```powershell
.\scripts\Initialize-AstrBot.ps1
```

## 3. 安装和登录 NapCatQQ

从 NapCatQQ 官方 Release 下载 Windows 版本，按照官方 Windows Shell 指南启动，并使用专门的 QQ 小号扫码。不要使用主 QQ 号。NapCat WebUI 默认端口是 `6099`。

## 4. 连接 OneBot v11

确认 AstrBot WebUI 只监听 `127.0.0.1:6185`，NapCat WebUI 也不对公网开放。在 AstrBot WebUI 创建 `OneBot v11` 机器人：启用，主机 `0.0.0.0`，端口 `6199`。若配置 Token，NapCat 两侧必须一致。

在 NapCat WebUI 选择“网络配置 → 新建 → WebSocket 客户端”，URL 填写 `ws://127.0.0.1:6199/ws`。AstrBot 控制台出现 `aiocqhttp(OneBot v11) 适配器已连接` 才算成功。

## 5. 配置 DeepSeek

启动 AstrBot 时使用 `.\scripts\Start-AstrBot.ps1`，使 `$DEEPSEEK_API_KEY` 仅进入当前进程。

在“服务提供商 → 新增”优先选择 DeepSeek；若当前版本没有 DeepSeek 卡片，则选择 OpenAI 兼容提供商。填写：API Base URL `https://api.deepseek.com/v1`，API Key `$DEEPSEEK_API_KEY`，模型 `deepseek-v4-flash`。

模型自定义参数：`max_tokens` 为 `512`，自定义请求体为 `{"thinking":{"type":"disabled"}}`。将最大上下文轮数 `max_context_length` 设为 `10`，每次淘汰轮数 `dequeue_context_length` 设为 `1`。关闭流式输出和所有工具。

## 6. 配置低成本规则

按照 `config/astrbot-v1-checklist.json` 设置：群聊需要 @ 或唤醒词，私聊无需唤醒前缀，`unique_session=false`，60 秒最多 5 条且超出丢弃，忽略机器人自身消息；关闭主动回复、图片描述、STT、TTS、Web 搜索和工具。第一版不安装额外的非文本消息插件，图片、语音、视频和文件按 AstrBot/NapCat 默认方式忽略或提示不支持，不应触发额外模型调用。需要排除某个私聊联系人时，在 AstrBot 自定义规则中对其关闭消息处理。

使用 `/sid` 获取管理员 UID，在 WebUI 添加管理员。使用 `/reset` 清空当前会话，使用 `/stats` 查看当前会话 Token。

## 7. 检查

```powershell
.\scripts\Test-Prerequisites.ps1
.\scripts\Get-DeepSeekBalance.ps1
```
```

Create `docs/acceptance-checklist.md` with a checkbox for each test below and the stated expected result:

1. `/sid`: returns the current session ID; adding that ID as an administrator enables admin-only group commands.
2. `/stats`: returns current-session token statistics without exposing the API key.
3. `/reset`: clears the current session; a follow-up question cannot use facts that existed only before the reset.
4. Group trigger: an ordinary unmentioned message gets no reply; the same text with an `@` mention gets one reply.
5. Session isolation: a fact told in private chat A is unavailable in private chat B and in a group; facts are shared among members inside the same group because `unique_session=false`.
6. Context bound: after more than 10 completed rounds, inspect `/stats` and behavior to confirm old context is evicted rather than growing without limit.
7. Non-text input: an image, voice message, video, or file is ignored or receives AstrBot's built-in unsupported response and does not make a DeepSeek request.
8. Invalid key: temporarily use an invalid API key, observe one visible failure without an endless retry loop or secret disclosure, then restore the key.
9. Reconnect: restart NapCat, confirm AstrBot logs a new OneBot connection, and confirm one private and one mentioned group message work again.

- [ ] **Step 5: Add a concise project entry point**

Create `README.md`:

```markdown
# QQ DeepSeek Bot

Windows 上的低成本 QQ 对话机器人部署包：NapCatQQ + AstrBot + DeepSeek V4 Flash。

1. 阅读 [Windows 安装与配置](docs/setup-windows.md)。
2. 按照 [配置检查表](config/astrbot-v1-checklist.json) 配置 AstrBot。
3. 使用 [验收清单](docs/acceptance-checklist.md) 验证私聊、群聊、上下文和错误处理。

真实 API Key 只能放在未提交的 `.env` 中。项目不会自动登录 QQ，也不会自动充值或续费。
```

- [ ] **Step 6: Run contract tests, all tests, diff checks, and secret scan**

```powershell
uv run pytest tests/test_repository_contract.py -q
uv run pytest -q
git diff --check
$candidateFiles = git ls-files --cached --others --exclude-standard
Select-String -Path $candidateFiles -Pattern 'sk-[A-Za-z0-9]{12,}' -Encoding UTF8
```

Expected: repository contract passes, the full suite passes, `git diff --check` exits 0, and the secret scan returns no matches.

- [ ] **Step 7: Commit documentation and configuration contract**

```powershell
git add -- README.md config docs/setup-windows.md docs/acceptance-checklist.md tests/test_repository_contract.py
git commit -m "docs: add QQ DeepSeek deployment runbook"
```

---

### Task 6: Fresh verification and local handoff

**Files:**
- Modify only if verification reveals a defect in files created by Tasks 1-5.

**Interfaces:**
- Consumes: the entire repository and an optional user-created `.env`.
- Produces: verified automated results and a clearly separated list of manual actions requiring the user's QQ scan and DeepSeek key.

- [ ] **Step 1: Verify repository state and automated tests from a clean shell**

```powershell
git status --short
uv sync --dev
uv run pytest -q
git diff --check
```

Expected: clean status before any local `.env`, dependency sync succeeds, all tests pass, and diff check exits 0.

- [ ] **Step 2: Verify PowerShell syntax independently**

```powershell
$parseErrors = @()
Get-ChildItem -LiteralPath scripts -Filter *.ps1 | ForEach-Object {
    $tokens = $null
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$tokens, [ref]$errors)
    $parseErrors += $errors
}
if ($parseErrors.Count -gt 0) { $parseErrors; exit 1 }
```

Expected: exits 0 with no parser errors.

- [ ] **Step 3: Verify the sample configuration fails safely before a real key is added**

```powershell
Copy-Item -LiteralPath .env.example -Destination .env
try {
    uv run qq-deepseek-setup balance
    if ($LASTEXITCODE -eq 0) { throw "Placeholder key unexpectedly passed validation" }
} finally {
    Remove-Item -LiteralPath .env
}
```

Expected: command exits nonzero with a placeholder-key message and does not print the placeholder value as a credential.

- [ ] **Step 4: Stop at the external-login boundary and hand off required user actions**

Do not create a DeepSeek key, top up an account, or scan QQ on behalf of the user. Present these remaining manual actions:

1. User creates `.env` locally and inserts the key.
2. User installs/starts NapCat and scans the dedicated QQ small account.
3. User starts AstrBot and completes WebUI settings using the committed checklist.
4. User runs balance, private chat, group mention, isolation, and reconnect acceptance checks.

- [ ] **Step 5: Handle verification-driven corrections without a generic commit**

If no correction was required, do not create an empty commit. If verification finds a defect, return to the task that owns the affected file, add or update its focused regression test, make the smallest correction, rerun that task's focused checks and the complete verification suite, and use that task's explicit file list when staging the correction.
