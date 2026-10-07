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
        path.write_text(text, encoding="utf-8")
        return path

    return write


@pytest.fixture(autouse=True)
def isolate_user_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Never read the developer's real ~/.config/mimedy/config.yaml in tests.

    autouse=True applies this fixture to every test without asking for it.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
