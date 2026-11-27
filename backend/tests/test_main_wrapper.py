"""The root main.py maps --input/--output to the positional arguments of the CLI."""

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("root_main", Path(__file__).resolve().parents[2] / "main.py")
assert _spec is not None and _spec.loader is not None
root_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(root_main)


def test_named_arguments_become_positional():
    to_args = root_main.to_cli_args
    assert to_args(["--input", "doc.md", "--output", "out.md"]) == ["doc.md", "out.md"]
    assert to_args(["--output=out.md", "--input=doc.md", "--cache-only"]) == [
        "doc.md",
        "--cache-only",
        "out.md",
    ]
    assert to_args(["doc.md", "out.md", "-m", "openai:x"]) == ["doc.md", "out.md", "-m", "openai:x"]
    assert to_args(["doc.md", "--output", "out.md"]) == ["doc.md", "out.md"]


def test_missing_path_is_reported():
    with pytest.raises(SystemExit):
        root_main.to_cli_args(["--input"])
