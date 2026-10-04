"""Tests for loading and validating the configuration file."""

import re
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from mimedy.config import Config, default_config_path, load_config
from mimedy.errors import ConfigError

# --- Loading -------------------------------------------------------------------


def test_valid_config_is_loaded(write_config: Callable[[str], Path]) -> None:
    path = write_config(
        """
        hidden: Dotfiles
        large_files:
          threshold_mb: 500
        extensions:
          .csv: Data
        """
    )

    config = load_config(path)

    assert config.hidden == "Dotfiles"
    assert config.large_files.threshold_mb == 500
    assert config.large_files.target_dir == "Large"  # default kept
    assert config.extensions == {".csv": "Data"}


# --- Unknown keys --------------------------------------------------------------


def test_unknown_key_suggests_the_right_one(
    write_config: Callable[[str], Path],
) -> None:
    path = write_config("extentions:\n  .csv: Data\n")

    with pytest.raises(ConfigError, match="did you mean 'extensions'"):
        load_config(path)


# --- Value types ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("yes", "must be a number, got bool"),
        ("0", "must be a positive number"),
        ("-5", "must be a positive number"),
    ],
)
def test_invalid_threshold_is_rejected(
    write_config: Callable[[str], Path], value: str, message: str
) -> None:
    path = write_config(f"large_files:\n threshold_mb: {value}\n")

    with pytest.raises(ConfigError, match=message):
        load_config(path)


def test_non_string_destination_is_rejected(
    write_config: Callable[[str], Path],
) -> None:
    path = write_config("hidden: 42\n")

    with pytest.raises(ConfigError, match="'hidden' must be a string, got int"):
        load_config(path)


# --- Destinations --------------------------------------------------------------


@pytest.mark.parametrize(
    "destination", ["/absolute/path", "../Data", "Data/../../x", "~/Data"]
)
def test_destinations_outside_the_folder_are_rejected(
    write_config: Callable[[str], Path], destination: str
) -> None:
    path = write_config(f"hidden: '{destination}'\n")

    with pytest.raises(ConfigError, match=r"must stay inside|relative folder name"):
        load_config(path)


# --- Extensions ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("written", "normalized"),
    [
        (".csv", ".csv"),
        (".CSV", ".csv"),
        ("csv", ".csv"),
        ("JPG", ".jpg"),
    ],
)
def test_extensions_are_normalized(
    write_config: Callable[[str], Path], written: str, normalized: str
) -> None:
    path = write_config(f"extensions:\n  {written}: Data\n")

    config = load_config(path)

    assert config.extensions == {normalized: "Data"}


def test_conflicting_extensions_are_rejected(
    write_config: Callable[[str], Path],
) -> None:
    path = write_config(
        """
        extensions:
          .JPG: Photos
          .jpg: Images
        """
    )

    with pytest.raises(
        ConfigError,
        match=re.escape(
            "'.JPG' and '.jpg' are the same rule but go to different folders"
        ),
    ):
        load_config(path)


def test_duplicate_extensions_to_same_folder_are_merged(
    write_config: Callable[[str], Path],
) -> None:
    path = write_config(
        """
        extensions:
          .JPG: Photos
          .jpg: Photos
        """
    )

    config = load_config(path)
    assert config.extensions == {".jpg": "Photos"}


# --- MIME types ----------------------------------------------------------------


def test_mimetypes_are_lowercased(write_config: Callable[[str], Path]) -> None:
    path = write_config(
        """
        mimetypes:
            APPLICATION/PDF: Documents
            IMAGE/JPEG: Photos
            IMAGE/PNG: Images
        """
    )

    config = load_config(path)
    assert config.mimetypes == {
        "application/pdf": "Documents",
        "image/jpeg": "Photos",
        "image/png": "Images",
    }


# --- Error reporting -----------------------------------------------------------


def test_all_errors_are_reported_at_once(write_config: Callable[[str], Path]) -> None:
    path = write_config(
        """
        hidden: 42
        large_files:
            threshold_mb: 0
            target_dir: 42
        extensions:
          .JPG: Photos
          .jpg: Images
          .pdf: 42
        mimetypes:
            APPLICATION/PDF: 42
            image/jpeg: Photos
            IMAGE/PNG: Images
        """
    )

    with pytest.raises(ConfigError) as exc_info:
        load_config(path)

    lines = str(exc_info.value).splitlines()[1:]  # skip "Invalid config in <path>:"
    assert lines == [
        "  - 'hidden' must be a string, got int",
        "  - In 'extensions':",
        "    - '.JPG' and '.jpg' are the same rule but go to different folders",
        "    - '.pdf' must be a string, got int",
        "  - In 'mimetypes':",
        "    - 'APPLICATION/PDF' must be a string, got int",
        "  - In 'large_files':",
        "    - 'threshold_mb' must be a positive number",
        "    - 'target_dir' must be a string, got int",
    ]


# --- Config file location -------------------------------------------------------
# monkeypatch changes environment variables (setenv, delenv) or attributes
# (setattr) for one test only, and restores them afterwards.


def test_default_config_path_uses_xdg_config_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    xdg_path = tmp_path / "xdg-config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_path))
    assert default_config_path() == xdg_path / "mimedy/config.yaml"


def test_default_config_path_ignores_relative_xdg_config_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    xdg_path = "xdg-config"
    monkeypatch.setenv("XDG_CONFIG_HOME", xdg_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_config_path() == tmp_path / ".config/mimedy/config.yaml"


def test_default_config_path_falls_back_to_home_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_config_path() == tmp_path / ".config/mimedy/config.yaml"


def test_default_config_path_uses_appdata_on_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    win_path = tmp_path / "win-config"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(win_path))
    assert default_config_path() == win_path / "mimedy/config.yaml"


def test_missing_explicit_config_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    with pytest.raises(ConfigError, match="Config file not found"):
        load_config(path)


def test_missing_default_config_gives_defaults() -> None:
    assert load_config() == Config()


def test_default_config_is_loaded_when_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    xdg_path = tmp_path / "xdg-config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_path))
    path = xdg_path / "mimedy/config.yaml"
    path.parent.mkdir(parents=True)
    path.write_text("extensions:\n  .csv: Data\n")
    assert load_config() == Config(extensions={".csv": "Data"})
