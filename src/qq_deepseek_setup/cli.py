from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .balance import BalanceClient, BalanceError
from .persona import PersonaRenderError, render_persona
from .preflight import run_preflight
from .settings import Settings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qq-deepseek-setup")
    parser.add_argument(
        "command", choices=("preflight", "balance", "render-persona")
    )
    args = parser.parse_args(argv)

    try:
        if args.command == "render-persona":
            result = render_persona(Path.cwd())
            print(json.dumps(result.to_public_dict(), ensure_ascii=False))
            return 0

        settings = Settings.load(Path.cwd())
        if args.command == "balance":
            print(
                json.dumps(
                    BalanceClient(settings).get().to_public_dict(), ensure_ascii=False
                )
            )
            return 0

        results = run_preflight(settings)
        for item in results:
            marker = "OK" if item.ok else "FAIL"
            print(f"[{marker}] {item.name}: {item.detail}")
        return 0 if all(item.ok for item in results) else 1
    except (ValueError, BalanceError, PersonaRenderError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
