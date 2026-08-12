from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .balance import BalanceClient, BalanceError
from .emote_assets import prepare_emotes
from .persona import PersonaRenderError, render_persona
from .preflight import run_preflight
from .settings import Settings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qq-deepseek-setup")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight")
    commands.add_parser("balance")
    commands.add_parser("render-persona")
    install = commands.add_parser("install-emotes")
    install.add_argument("--source", action="append", type=Path, required=True)
    install.add_argument("--destination", type=Path, required=True)
    install.add_argument("--allowed-root", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        if args.command == "install-emotes":
            try:
                result = prepare_emotes(
                    args.source, args.destination, args.allowed_root
                )
            except OSError:
                print("ERROR: unable to install emotes due to a filesystem error")
                return 2
            print(json.dumps(result.to_public_dict(), ensure_ascii=False))
            return 0

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
