"""Run the agent: python main.py --input <requirements file> --output <report file>.

A thin wrapper around the `revizorro` command (backend/src/revizorro/cli.py).
Positional arguments work too, and every other flag is passed through unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the package importable even when it was not installed with pip.
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend" / "src"))


def to_cli_args(argv: list[str]) -> list[str]:
    """Turn --input / --output into the two positional arguments the CLI expects."""
    named: dict[str, str] = {}
    rest: list[str] = []
    i = 0
    while i < len(argv):
        name, eq, value = argv[i].partition("=")
        if name in ("--input", "--output"):
            if not eq:
                i += 1
                if i >= len(argv):
                    raise SystemExit(f"После {name} нужен путь к файлу")
                value = argv[i]
            named[name] = value
        else:
            rest.append(argv[i])
        i += 1
    # The input goes first and the output last; options may sit between them.
    return [
        *([named["--input"]] if "--input" in named else []),
        *rest,
        *([named["--output"]] if "--output" in named else []),
    ]


def main() -> None:
    from revizorro.cli import app

    app(args=to_cli_args(sys.argv[1:]), prog_name="python main.py")


if __name__ == "__main__":
    main()
