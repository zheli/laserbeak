from __future__ import annotations

import sys

from typer.main import get_command

from .cli import KNOWN_COMMANDS, app
from .cli_args import resolve_cli_invocation


def main() -> None:
    raw_args = sys.argv[1:]
    normalized_args = raw_args[1:] if raw_args[:1] == ["--"] else raw_args
    invocation = resolve_cli_invocation(normalized_args, KNOWN_COMMANDS)

    command = get_command(app)
    if invocation["show_help"]:
        command.main(args=["--help"], prog_name="bird")
        return

    if invocation["argv"]:
        command.main(args=invocation["argv"], prog_name="bird")
        return

    command.main(args=normalized_args, prog_name="bird")


if __name__ == "__main__":
    main()
