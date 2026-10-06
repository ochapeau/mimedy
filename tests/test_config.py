"""Tests for loading and validating the configuration file."""

import re
import sys
from collections.abc import Callable
from dataclasses import fields
from importlib.resources import files
from pathlib import Path

import pytest

from mimedy.config import (
    CONFIG_READERS,
    LARGE_FILES_READERS,
    Config,
    LargeFilesConfig,
    default_config_path,
    load_config,
)
from mimedy.errors import ConfigError

# --- Loading -------------------------------------------------------------------


def test_valid_config_is_loaded(write_config: Callable[..., Path]) -> None:
    config_path = write_config(
        """
        hidden: Dotfiles
        large_files:
          threshold_mb: 500
        extensions:
          .csv: Data
        """
    )

    config = load_config(config_path)

    assert config.hidden == "Dotfiles"
    assert config.large_files.threshold_mb == 500
    assert config.large_files.target_dir == "Large"  # default kept
    assert config.extensions == {".csv": "Data"}


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("hidden: [", "Invalid YAML in"),
        ("- ignore_system_files\n- hidden\n", "expected a mapping of settings"),
    ],
)
def test_unreadable_yaml_is_rejected(
    write_config: Callable[..., Path], text: str, message: str
) -> None:
    config_path = write_config(text)

    with pytest.raises(ConfigError, match=message):
        load_config(config_path)


def test_unreadable_config_file_is_rejected(tmp_path: Path) -> None:
    # Pass a folder as the config file: opening it raises IsADirectoryError,
    # an OSError, which read_yaml reports as "Cannot read <path>"
    with pytest.raises(ConfigError, match=f"Cannot read {tmp_path}"):
        load_config(tmp_path)


# --- Unknown keys --------------------------------------------------------------


def test_unknown_key_without_close_match_has_no_suggestion(
    write_config: Callable[..., Path],
) -> None:
    config_path = write_config("zzz: 1\n")

    with pytest.raises(ConfigError) as exc_info:
        load_config(config_path)

    message = str(exc_info.value)
    assert "Unknown key 'zzz'" in message
    assert "did you mean" not in message  # nothing close to 'zzz'


def test_unknown_key_suggests_the_right_one(
    write_config: Callable[..., Path],
) -> None:
    config_path = write_config("extentions:\n  .csv: Data\n")

    with pytest.raises(ConfigError, match="did you mean 'extensions'"):
        load_config(config_path)


@pytest.mark.parametrize(
    ("config_class", "readers"),
    [(Config, CONFIG_READERS), (LargeFilesConfig, LARGE_FILES_READERS)],
)
def test_every_field_has_a_reader(
    config_class: type, readers: dict[str, object]
) -> None:
    # A new field without a reader would be accepted, then silently ignored
    assert {f.name for f in fields(config_class)} == readers.keys()


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
    write_config: Callable[..., Path], value: str, message: str
) -> None:
    config_path = write_config(f"large_files:\n  threshold_mb: {value}\n")

    with pytest.raises(ConfigError, match=message):
        load_config(config_path)


def test_non_string_destination_is_rejected(
    write_config: Callable[..., Path],
) -> None:
    config_path = write_config("hidden: 42\n")

    with pytest.raises(ConfigError, match="'hidden' must be a string, got int"):
        load_config(config_path)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        # Not a number
        ("large_files:\n  threshold_mb: abc\n", "must be a positive number, got str"),
        # Empty destination
        ("hidden: ''\n", "'hidden' must not be empty"),
        # A list or a number instead of a mapping
        ("extensions: [.csv]\n", "'extensions' must be a mapping, got list"),
        ("large_files: 5\n", "'large_files' must be a mapping, got int"),
    ],
)
def test_wrong_value_types_are_rejected(
    write_config: Callable[..., Path], text: str, message: str
) -> None:
    config_path = write_config(text)

    with pytest.raises(ConfigError, match=re.escape(message)):
        load_config(config_path)


# --- Ignore --------------------------------------------------------------------


def test_ignore_defaults() -> None:
    config = load_config()

    assert config.ignore_system_files is True
    assert config.ignore == ()


def test_ignore_settings_are_loaded(write_config: Callable[..., Path]) -> None:
    config_path = write_config(
        """
        ignore_system_files: false
        ignore:
        - "*.PART"
        - "*.crdownload"
        """
    )

    config = load_config(config_path)

    assert config.ignore_system_files is False
    assert config.ignore == ("*.part", "*.crdownload")


@pytest.mark.parametrize("value", ["'true'", "1"])
def test_invalid_ignore_system_files_is_rejected(
    write_config: Callable[..., Path], value: str
) -> None:
    config_path = write_config(f"ignore_system_files: {value}\n")

    with pytest.raises(ConfigError, match="must be true or false, got"):
        load_config(config_path)


def test_ignore_must_be_a_list(write_config: Callable[..., Path]) -> None:
    config_path = write_config("ignore: '*.part'\n")

    with pytest.raises(ConfigError, match="must be a list, got str"):
        load_config(config_path)


@pytest.mark.parametrize(
    ("item", "message"),
    [
        ("''", "must not be empty"),  # empty string
        ("'   '", "must not be empty"),  # only spaces
        ("42", "must be a string, got int"),  # not a string
        ("", "must be a string, got NoneType"),  # "- " alone: YAML reads None
    ],
)
def test_invalid_ignore_patterns_are_rejected(
    write_config: Callable[..., Path], item: str, message: str
) -> None:
    config_path = write_config(f"ignore:\n  - {item}\n")

    with pytest.raises(ConfigError, match=message):
        load_config(config_path)


# --- Destinations --------------------------------------------------------------


@pytest.mark.parametrize(
    "destination", ["/absolute/path", "../Data", "Data/../../x", "~/Data"]
)
def test_destinations_outside_the_folder_are_rejected(
    write_config: Callable[..., Path], destination: str
) -> None:
    config_path = write_config(f"hidden: '{destination}'\n")

    with pytest.raises(ConfigError, match=r"must stay inside|relative folder name"):
        load_config(config_path)


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
    write_config: Callable[..., Path], written: str, normalized: str
) -> None:
    config_path = write_config(f"extensions:\n  {written}: Data\n")

    config = load_config(config_path)

    assert config.extensions == {normalized: "Data"}


@pytest.mark.parametrize(
    ("key", "message"),
    [
        ("42", "42 must be a string, got int"),  # YAML reads an int key
        ("'.'", "'.' is not a valid extension"),  # a dot alone: empty extension
    ],
)
def test_invalid_extension_keys_are_rejected(
    write_config: Callable[..., Path], key: str, message: str
) -> None:
    config_path = write_config(f"extensions:\n  {key}: Data\n")

    with pytest.raises(ConfigError, match=re.escape(message)):
        load_config(config_path)


def test_conflicting_extensions_are_rejected(
    write_config: Callable[..., Path],
) -> None:
    config_path = write_config(
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
        load_config(config_path)


def test_duplicate_extensions_to_same_folder_are_merged(
    write_config: Callable[..., Path],
) -> None:
    config_path = write_config(
        """
        extensions:
          .JPG: Photos
          .jpg: Photos
        """
    )

    config = load_config(config_path)

    assert config.extensions == {".jpg": "Photos"}


# --- MIME types ----------------------------------------------------------------


def test_mimetypes_are_lowercased(write_config: Callable[..., Path]) -> None:
    config_path = write_config(
        """
        mimetypes:
            APPLICATION/PDF: Documents
            IMAGE/JPEG: Photos
            IMAGE/PNG: Images
        """
    )

    config = load_config(config_path)

    assert config.mimetypes == {
        "application/pdf": "Documents",
        "image/jpeg": "Photos",
        "image/png": "Images",
    }


# --- Error reporting -----------------------------------------------------------


def test_all_errors_are_reported_at_once(write_config: Callable[..., Path]) -> None:
    config_path = write_config(
        """
        ignore_system_files: "yes"
        ignore:
          - "*.part"
          - ""
          - 42
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
        load_config(config_path)

    lines = str(exc_info.value).splitlines()[1:]  # skip "Invalid config in <path>:"
    assert lines == [
        "  - 'ignore_system_files' must be true or false, got str",
        "  - In 'ignore':",
        "    - item 2 must not be empty",
        "    - item 3 must be a string, got int",
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
    monkeypatch.setenv("XDG_CONFIG_HOME", "xdg-config")
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
    appdata_path = tmp_path / "appdata"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(appdata_path))
    assert default_config_path() == appdata_path / "mimedy/config.yaml"


def test_missing_explicit_config_is_an_error(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"

    with pytest.raises(ConfigError, match="Config file not found"):
        load_config(config_path)


def test_missing_default_config_gives_defaults() -> None:
    assert load_config() == Config()


def test_default_config_is_loaded_when_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    xdg_path = tmp_path / "xdg-config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_path))
    config_path = xdg_path / "mimedy/config.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("extensions:\n  .csv: Data\n")
    assert load_config() == Config(extensions={".csv": "Data"})


# --- Shipped example ------------------------------------------------------------


def test_shipped_example_config_is_valid() -> None:
    # --init-config copies this file: it must always load without errors
    config_path = Path(str(files("mimedy") / "config.example.yaml"))

    config = load_config(config_path)

    assert config != Config()  # the example really sets rules
