# Final Review Fix Report

- Date: 2026-08-09
- Branch: `codex/qq-deepseek-v1`
- Starting commit: `c1508e5`
Correction commit message: `fix: resolve final deployment review`

## Outcome

All four Important and both Minor findings in `final-review-fix-brief.md` were resolved in one correction wave. No AstrBot or NapCat service was installed or started, no QQ login or QR scan occurred, no API key was created or used, and DeepSeek was not called.

## Files changed

- `config/astrbot-v1-checklist.json`
- `docs/acceptance-checklist.md`
- `docs/setup-windows.md`
- `docs/superpowers/plans/2026-08-09-qq-deepseek-bot.md`
- `docs/superpowers/specs/2026-08-09-qq-deepseek-bot-design.md`
- `scripts/Initialize-AstrBot.ps1`
- `src/qq_deepseek_setup/balance.py`
- `src/qq_deepseek_setup/preflight.py`
- `tests/test_balance.py`
- `tests/test_powershell_wrappers.py`
- `tests/test_preflight.py`
- `tests/test_repository_contract.py`
- `.superpowers/sdd/final-review-fix-report.md`

## Finding-by-finding resolution

1. Local-only network posture
   - AstrBot OneBot is specified as `127.0.0.1:6199`.
   - AstrBot WebUI is specified as `127.0.0.1:6185`.
   - NapCat WebUI is specified as `127.0.0.1:6099`.
   - NapCat reverse WebSocket remains `ws://127.0.0.1:6199/ws`.
   - Preflight now inventories actual Windows TCP listeners through `Get-NetTCPConnection`. For each required port it fails missing, wildcard, invalid, or non-loopback addresses. Listener records are dependency-injected for deterministic tests, so tests open no sockets and require no services.

2. First-run order
   - After initialization, the runbook binds the AstrBot dashboard in `data/cmd_config.json`, launches `Start-AstrBot.ps1` in a dedicated window, leaves it running, and moves WebUI configuration/preflight/balance work to a second PowerShell window.

3. Reproducible AstrBot/DeepSeek configuration
   - AstrBot `>=4.13.0` is required for `$DEEPSEEK_API_KEY` expansion.
   - The checklist and runbook contain the exact selected `provider[].model_config` values for `deepseek-v4-flash`, `max_tokens=512`, and `extra_body.thinking.type=disabled`.
   - The runbook identifies the provider by its WebUI ID and Base URL, requires save/restart, and gives a key-safe read-only persistence check.
   - Base URL `https://api.deepseek.com/v1`, 10 context rounds, dequeue 1, text-only/no tools/no search/no multimodal, one enabled chat provider, and no fallback are preserved.

4. Balance schema safety
   - Successful responses now require a JSON object, boolean `is_available`, list `balance_infos`, object entries, string `currency`, and string-or-number balance values.
   - Malformed successful responses are converted inside the protected boundary to `DeepSeek balance query failed (invalid response)` with exception chaining suppressed and no key material.

5. Runtime initialization consistency
   - `Initialize-AstrBot.ps1` reads `ASTRBOT_RUNTIME_DIR` from the repository `.env` when `-RuntimeDir` is absent.
   - An explicitly supplied `-RuntimeDir` wins.
   - Existing repository-containment checks, pre/post-create reparse-point checks, and exact native exit propagation remain covered.

6. Context acceptance precision
   - The checklist now uses 12 distinctive random `FACT-01` through `FACT-12` rounds.
   - It checks the exact first-oldest eviction at round 11 and next-oldest eviction at round 12, with `/stats`, persisted configuration, and conversation history explicitly secondary.

## TDD evidence

### Balance payload validation

- RED: focused balance suite produced `8 failed, 2 passed`. Failures demonstrated `AttributeError`, `TypeError`, and `KeyError` escaping for malformed objects and permissive coercion for invalid fields.
- GREEN: focused balance suite produced `10 passed`.

### Listener validation and native inventory parsing

- RED 1: focused preflight collection failed because the wished-for `TcpListener` API did not exist.
- RED 2: the isolated native-inventory parser test failed with the intentional `NotImplementedError` stub.
- GREEN: focused preflight suite produced `6 passed`, including `0.0.0.0`, `::`, and a LAN address rejection plus synthetic PowerShell JSON parsing.

### Initialize-AstrBot runtime selection

- RED: focused wrapper suite produced `1 failed, 5 passed`; the fake AstrBot process recorded the hard-coded default cwd instead of the `.env` runtime.
- GREEN: focused wrapper suite produced `6 passed`, covering `.env` default, explicit override, reparse-point rejection, and exact child exit codes.

### Repository contracts and documentation

- RED: focused contract suite produced `4 failed, 2 passed` for wildcard OneBot binding, absent minimum version/model config, incorrect first-run order, and imprecise context acceptance.
- GREEN: focused contract suite produced `6 passed`.

## Fresh verification

Executed from the repository root with the existing locked `.venv` Python 3.12 environment:

| Verification | Result |
|---|---|
| `python -m pytest tests/test_balance.py -q` | `10 passed` |
| `python -m pytest tests/test_preflight.py -q` | `6 passed` |
| `python -m pytest tests/test_powershell_wrappers.py -q` | `6 passed` |
| `python -m pytest tests/test_repository_contract.py -q` | `6 passed` |
| `python -m pytest -q` | `36 passed` |
| Parse every `scripts/*.ps1` with `System.Management.Automation.Language.Parser` | 4 scripts, 0 errors |
| `git diff --check` | exit 0 |
| `git ls-files --cached --others --exclude-standard` plus secret regex scan | 0 matches |
| Direct read-only native listener inventory | exit 0, empty tuple because no required service was running |

## Official source verification

Only current primary documentation was used for configuration decisions:

- <https://docs.astrbot.app/en/platform/aiocqhttp.html>
- <https://docs.astrbot.app/en/providers/start.html>
- <https://docs.astrbot.app/en/config/model-config.html>
- <https://docs.astrbot.app/en/dev/astrbot-config.html>
- <https://napneko.github.io/config/basic>
- <https://api-docs.deepseek.com/guides/thinking_mode/>

The originally supplied nested AstrBot/NapCat URL returned 404; the current official OneBot page is `https://docs.astrbot.app/en/platform/aiocqhttp.html`.

## Self-review

- Confirmed all three required hosts and ports match across checklist, design, plan, runbook, acceptance, and repository tests.
- Confirmed only tests contain wildcard/non-loopback sample addresses, where they are rejection fixtures.
- Confirmed balance parsing occurs inside the `try` caught by the public generic error conversion.
- Confirmed listener acquisition errors fail all listener checks without exposing PowerShell stderr or producing a traceback through the CLI.
- Confirmed initialization still rejects repository escape and reparse traversal before and after directory creation.
- Confirmed the persisted model example uses `provider[].model_config`, not a stale top-level custom-body field.
- Confirmed the runbook's persistence command outputs `model_config`, Base URL, and only a boolean-style key-reference status.
- Confirmed no unrelated refactor, service mutation, login, key use, or API call was introduced.

## Concerns and manual boundary

- `uv.exe` is not available on this host's `PATH`, so literal `uv run ...` verification could not be executed. The already-present ignored `.venv` is Python 3.12.11 with the locked declared dependencies and ran every required pytest command successfully. The deployment runbook still requires the user to install/verify `uv` as designed.
- Live AstrBot/NapCat binding, WebUI persistence, QQ messaging, DeepSeek balance, invalid-key behavior, reconnection, and 12-round context behavior remain manual acceptance items. They were intentionally not exercised because the task forbids installing/starting/logging into external services, scanning QQ, using a key, or calling DeepSeek.
