"""Fixtures shared by every test file (pytest loads this file automatically)."""

from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture
def make_file(tmp_path: Path) -> Callable[..., Path]:
    """Return a function that creates a file of a given name and size.

    The name may include folders ("PDF/a.pdf"): they are created as needed.
    """

    def make(name: str, size: int = 10) -> Path:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * size)
        return path

    return make


@pytest.fixture
def write_config(tmp_path: Path) -> Callable[..., Path]:
    """Return a function that writes YAML text to tmp_path/config.yaml."""

    def write(text: str = "") -> Path:
        path = tmp_path / "config.yaml"
        path.write_text(text)
        return path

    return write
