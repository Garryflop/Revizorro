"""Prompt files (Russian) and their combined version hash."""

from __future__ import annotations

import hashlib
from functools import cache
from importlib.resources import files
from string import Template

_PKG = files(__package__ or "revizorro.prompts")
NAMES = (
    "common",
    "segmenter",
    "reviewer",
    "test_designer",
    "consistency",
    "completeness",
    "api_contract",
    "critic",
    "clarifier",
    "resolver",
    "rechecker",
    "summarizer",
)


@cache
def raw(name: str) -> str:
    return _PKG.joinpath(f"{name}.md").read_text(encoding="utf-8")


def instructions(name: str, **params: str) -> str:
    """Common preamble + task prompt with $placeholders filled."""
    return raw("common") + "\n\n" + Template(raw(name)).safe_substitute(**params)


@cache
def version() -> str:
    digest = hashlib.sha256()
    for name in NAMES:
        digest.update(raw(name).encode("utf-8"))
    return digest.hexdigest()[:10]
