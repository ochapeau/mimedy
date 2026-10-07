"""Configuration loading and validation.

Dataclasses do not check types at runtime: building a Config directly from
unchecked data would accept anything. Always go through load_config(), which
validates every value before building the dataclasses.
"""

import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from difflib import get_close_matches
from functools import partial
from pathlib import Path, PurePath

import yaml

from mimedy.errors import ConfigError

logger = logging.getLogger("mimedy.config")

# Every reader takes (value, key, errors): it returns the checked value, or
# None after adding to errors what is wrong
Reader = Callable[[object, str, list[str]], object]


@dataclass(frozen=True, kw_only=True)
class LargeFilesConfig:
    """Where files bigger than threshold_mb (decimal MB) are moved."""

    threshold_mb: float = 100
    target_dir: str = "Large"


@dataclass(frozen=True, kw_only=True)
class Config:
    """The validated configuration, as returned by load_config().

    The rest of the program can rely on these guarantees:

    - every destination folder is a non-empty relative path that stays
      inside the organized folder, normalized ("Code/Python", never
      "./Code//Python/", "/tmp" or "../Data")
    - extension keys are lowercase and start with a dot (".jpg"), so
      they must be compared with file.suffix.lower()
    - MIME type keys are lowercase ("application/pdf")
    - no two rules conflict once normalized
    - ignore patterns are lowercased ("*.part"), so they must be compared
      with file.name.lower()
    """

    ignore_system_files: bool = True
    ignore: tuple[str, ...] = ()
    hidden: str = "Hidden"
    large_files: LargeFilesConfig = field(default_factory=LargeFilesConfig)
    extensions: dict[str, str] = field(default_factory=dict)
    mimetypes: dict[str, str] = field(default_factory=dict)


# --- Config file ---------------------------------------------------------------


def default_config_path() -> Path:
    """Return the per-user config file.

    - Linux and macOS: $XDG_CONFIG_HOME/mimedy/config.yaml, which is
      ~/.config/mimedy/config.yaml by default
    - Windows: %APPDATA%\\mimedy\\config.yaml, which is
      C:\\Users\\<name>\\AppData\\Roaming\\mimedy\\config.yaml by default

    The config is a user setting: on Windows it goes in Roaming, which follows
    the user from one computer to another on a company network.
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME", "")
        # The XDG spec says to ignore an empty or relative value
        base = Path(xdg) if xdg and Path(xdg).is_absolute() else Path.home() / ".config"
    return base / "mimedy" / "config.yaml"


def read_yaml(config_path: Path) -> dict:
    """Read a YAML config file as a mapping of settings.

    Raise ConfigError if the file is missing, unreadable, not valid YAML, or
    not a mapping.
    """
    try:
        with config_path.open() as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError as e:
        msg = f"Config file not found: {config_path}"
        raise ConfigError(msg) from e
    except OSError as e:
        msg = f"Cannot read {config_path}: {e.strerror}"
        raise ConfigError(msg) from e
    except yaml.YAMLError as e:
        msg = f"Invalid YAML in {config_path}: {e}"
        raise ConfigError(msg) from e

    if not isinstance(data, dict):
        msg = f"Invalid config in {config_path}: expected a mapping of settings"
        raise ConfigError(msg)
    return data


# --- Error reporting -----------------------------------------------------------


def check_unknown_keys(data: dict, config_class: type, errors: list[str]) -> None:
    """Add an error for each key of data that is not a field of config_class.

    A likely typo gets a suggestion: "did you mean 'extensions'?".
    """
    authorized_keys = {f.name for f in fields(config_class)}
    unknown_keys = data.keys() - authorized_keys
    for key in sorted(unknown_keys):
        close_match = get_close_matches(key, authorized_keys, n=1)
        err_msg = f"Unknown key '{key}'"
        if close_match:
            err_msg += f" (did you mean '{close_match[0]}'?)"
        errors.append(err_msg)


def add_section_errors(
    section: str, section_errors: list[str], errors: list[str]
) -> None:
    """Add the errors of a config section, grouped under its name."""
    details = "\n".join(f"    - {error}" for error in section_errors)
    errors.append(f"In '{section}':\n{details}")


# --- Single values -------------------------------------------------------------


def read_bool(value: object, key: str, errors: list[str]) -> bool | None:
    """Read a YAML boolean (true/false, yes/no), not a quoted "true" or 1."""
    if not isinstance(value, bool):
        errors.append(f"'{key}' must be true or false, got {type(value).__name__}")
        return None
    return value


def read_threshold(value: object, key: str, errors: list[str]) -> float | None:
    """Read a strictly positive number, booleans excluded."""
    # YAML reads "yes" as True, and True is an int in Python: reject it first
    if isinstance(value, bool):
        errors.append(f"'{key}' must be a number, got bool")
        return None

    if not isinstance(value, (int, float)):
        errors.append(f"'{key}' must be a positive number, got {type(value).__name__}")
        return None

    threshold = float(value)
    if threshold <= 0:
        errors.append(f"'{key}' must be a positive number")
        return None
    return threshold


def read_dir(value: object, key: str, errors: list[str]) -> str | None:
    """Read a destination folder, relative to the organized folder.

    It must be a non-empty relative path that stays inside the organized
    folder. Surrounding spaces are stripped and the path is normalized
    ("./Code//Python/" becomes "Code/Python").
    """
    if not isinstance(value, str):
        errors.append(f"'{key}' must be a string, got {type(value).__name__}")
        return None

    # PurePath only parses the text: destinations usually don't exist yet,
    # and validating the config must not depend on the disk
    path = PurePath(value.strip())

    # "" and "." both have no parts: they would mean the organized folder itself
    if not path.parts:
        errors.append(f"'{key}' must not be empty")
        return None

    # Path("/organized") / "/tmp" gives "/tmp", and ".." climbs out of it:
    # a destination must never lead outside the organized folder
    if path.is_absolute():
        errors.append(f"'{key}' must be a relative folder name, got '{path}'")
        return None
    if ".." in path.parts:
        errors.append(f"'{key}' must stay inside the organized folder, got '{path}'")
        return None

    # Only the shell expands "~" (and "~user") at the start of a path: here it
    # would create a folder literally named "~", not use the home directory
    if path.parts[0].startswith("~"):
        errors.append(
            f"'{key}' must stay inside the organized folder "
            f"('~' is not expanded), got '{path}'"
        )
        return None
    return str(path)


# --- Lists and mappings --------------------------------------------------------


def read_patterns(value: object, key: str, errors: list[str]) -> tuple[str, ...] | None:
    """Read a list of file name patterns ("*.part", "~$*").

    Surrounding spaces are stripped and patterns are lowercased, so they
    must be compared with the lowercased file name.
    """
    if not isinstance(value, list):
        errors.append(f"'{key}' must be a list, got {type(value).__name__}")
        return None

    patterns_errors: list[str] = []
    patterns: list[str] = []
    for i, pattern in enumerate(value):
        if not isinstance(pattern, str):
            patterns_errors.append(
                f"item {i + 1} must be a string, got {type(pattern).__name__}"
            )
            continue
        stripped = pattern.strip()
        if not stripped:
            patterns_errors.append(f"item {i + 1} must not be empty")
            continue
        patterns.append(stripped.lower())
    if patterns_errors:
        add_section_errors(key, patterns_errors, errors)
        return None
    return tuple(patterns)


def normalize_extension(extension: str) -> str:
    """Normalize an extension: '.JPG' -> '.jpg', 'csv' -> '.csv'.

    Raise ValueError for an empty extension ("" or ".").
    """
    name = extension.lower().removeprefix(".")
    if not name:
        msg = "is not a valid extension"
        raise ValueError(msg)
    return f".{name}"


def read_mapping(
    value: object, key: str, errors: list[str], normalize: Callable[[str], str]
) -> dict[str, str] | None:
    """Read a mapping of rules to destination folders (extensions, mimetypes).

    Keys go through normalize. Two keys that become the same rule are
    accepted when they point to the same folder, and reported otherwise.
    """
    if not isinstance(value, dict):
        errors.append(f"'{key}' must be a mapping, got {type(value).__name__}")
        return None

    # Errors are grouped under the mapping's name, e.g. "In 'extensions':"
    mapping_errors: list[str] = []
    mapping: dict[str, str] = {}
    # Normalized rule -> rule as written, to name both sides of a conflict
    origins: dict[str, str] = {}
    for rule, dest in value.items():
        if not isinstance(rule, str):
            mapping_errors.append(
                f"{rule!r} must be a string, got {type(rule).__name__}"
            )
            continue

        try:
            normalized_rule = normalize(rule)
        except ValueError as e:
            mapping_errors.append(f"'{rule}' {e}")
            continue

        checked_dest = read_dir(dest, rule, mapping_errors)
        if checked_dest is None:
            continue

        if normalized_rule not in mapping:
            mapping[normalized_rule] = checked_dest
            origins[normalized_rule] = rule
        elif mapping[normalized_rule] != checked_dest:
            mapping_errors.append(
                f"'{origins[normalized_rule]}' and '{rule}' "
                "are the same rule but go to different folders"
            )
            continue

    if mapping_errors:
        add_section_errors(key, mapping_errors, errors)
        return None
    return mapping


# --- Sections ------------------------------------------------------------------


def read_fields(
    data: dict, readers: dict[str, Reader], errors: list[str]
) -> dict[str, object]:
    """Read every key of data that has a reader, in the readers' order.

    Return the valid values only: missing or invalid keys keep the
    dataclass default.
    """
    values = {}
    for key, read in readers.items():
        if key in data:
            value = read(data[key], key, errors)
            if value is not None:
                values[key] = value
    return values


LARGE_FILES_READERS: dict[str, Reader] = {
    "threshold_mb": read_threshold,
    "target_dir": read_dir,
}


def read_large_files(
    value: object, key: str, errors: list[str]
) -> LargeFilesConfig | None:
    """Read the large_files section: threshold_mb and target_dir."""
    if not isinstance(value, dict):
        errors.append(f"'{key}' must be a mapping, got {type(value).__name__}")
        return None

    # Errors are grouped under "In 'large_files':", unknown keys included
    section_errors: list[str] = []
    check_unknown_keys(value, LargeFilesConfig, section_errors)
    values = read_fields(value, LARGE_FILES_READERS, section_errors)

    if section_errors:
        add_section_errors(key, section_errors, errors)
        return None
    return LargeFilesConfig(**values)


# The order of this dict is the order of the error messages
CONFIG_READERS: dict[str, Reader] = {
    "ignore_system_files": read_bool,
    "ignore": read_patterns,
    "hidden": read_dir,
    "extensions": partial(read_mapping, normalize=normalize_extension),
    "mimetypes": partial(read_mapping, normalize=str.lower),
    "large_files": read_large_files,
}


def load_config(config_path: Path | None = None) -> Config:
    """Load and validate the configuration.

    config_path is the file given with --config: it must exist. Without it,
    the per-user file from default_config_path() is used when it exists, and
    the default configuration otherwise.

    Raise ConfigError listing every problem found in an invalid file.
    """
    if config_path is None:
        config_path = default_config_path()
        if not config_path.exists():
            logger.debug("No config file at %s, using defaults", config_path)
            return Config()

    data = read_yaml(config_path)

    # Collect every error before reporting, so they can all be fixed at once
    errors: list[str] = []
    check_unknown_keys(data, Config, errors)
    values = read_fields(data, CONFIG_READERS, errors)

    if errors:
        details = "\n".join(f"  - {error}" for error in errors)
        msg = f"Invalid config in {config_path}:\n{details}"
        raise ConfigError(msg)

    logger.info("Loaded config from %s", config_path)
    return Config(**values)
