"""Configuration loading and validation.

Dataclasses do not check types at runtime: building a Config directly from
unchecked data would accept anything. Always go through load_config(), which
validates every value before building the dataclasses.
"""

import logging
from dataclasses import dataclass, field, fields
from difflib import get_close_matches
from pathlib import Path, PurePath

import yaml

from mimedy.errors import ConfigError

logger = logging.getLogger("mimedy.config")


@dataclass(frozen=True)
class LargeFilesConfig:
    """The config for large files."""

    threshold_mb: int = 100
    target_dir: str = "Large"


@dataclass(frozen=True)
class Config:
    """A config to load."""

    hidden: str = "Hidden"
    large_files: LargeFilesConfig = field(default_factory=LargeFilesConfig)
    extensions: dict[str, str] = field(default_factory=dict)
    mimetypes: dict[str, str] = field(default_factory=dict)


def check_unknown_keys(data: dict, config_class: type, errors: list[str]) -> None:
    """Add an error for each key of data that is not a field of config_class."""
    authorized_keys = {f.name for f in fields(config_class)}
    unknown_keys = data.keys() - authorized_keys
    for key in sorted(unknown_keys):
        close_match = get_close_matches(key, authorized_keys, n=1)
        err_msg = f"Unknown key '{key}'"
        if close_match:
            err_msg += f" (did you mean '{close_match[0]}'?)"
        errors.append(err_msg)


def read_dir(value: object, key: str, errors: list[str]) -> str | None:
    """A destination folder, relative to the organized folder.

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


def read_threshold(value: object, key: str, errors: list[str]) -> float | None:
    """A strictly positive number, booleans excluded."""
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


def add_section_errors(
    section: str, section_errors: list[str], errors: list[str]
) -> None:
    """Add the errors of a config section, grouped under its name."""
    details = "\n".join(f"    - {error}" for error in section_errors)
    errors.append(f"In '{section}':\n{details}")


def read_mapping(value: object, key: str, errors: list[str]) -> dict[str, str] | None:
    """A mapping of strings to strings (extensions, mimetypes)."""
    if not isinstance(value, dict):
        errors.append(f"'{key}' must be a mapping, got {type(value).__name__}")
        return None

    # Errors are grouped under the mapping's name, e.g. "In 'extensions':"
    mapping_errors: list[str] = []
    mapping: dict[str, str] = {}
    for rule, dest in value.items():
        if not isinstance(rule, str):
            mapping_errors.append(
                f"{rule!r} must be a string, got {type(rule).__name__}"
            )
            continue
        checked_dest = read_dir(dest, rule, mapping_errors)
        if checked_dest is not None:
            mapping[rule] = checked_dest

    if mapping_errors:
        add_section_errors(key, mapping_errors, errors)
        return None
    return mapping


def read_large_files(value: object, errors: list[str]) -> LargeFilesConfig | None:
    """The large_files section: a mapping with threshold_mb and target_dir."""
    if not isinstance(value, dict):
        errors.append(f"'large_files' must be a mapping, got {type(value).__name__}")
        return None

    # Errors are grouped under "In 'large_files':", unknown keys included
    large_files_errors: list[str] = []
    check_unknown_keys(value, LargeFilesConfig, large_files_errors)

    kwargs = {}
    if "threshold_mb" in value:
        threshold_mb = read_threshold(
            value["threshold_mb"], "threshold_mb", large_files_errors
        )
        if threshold_mb is not None:
            kwargs["threshold_mb"] = threshold_mb
    if "target_dir" in value:
        target_dir = read_dir(value["target_dir"], "target_dir", large_files_errors)
        if target_dir is not None:
            kwargs["target_dir"] = target_dir

    if large_files_errors:
        add_section_errors("large_files", large_files_errors, errors)
        return None

    return LargeFilesConfig(**kwargs)


def load_config(config_path: Path) -> Config:
    try:
        with config_path.open() as f:
            config_to_load = yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning("Config file not found: %s, using defaults", config_path)
        return Config()
    except OSError as err:
        msg = f"Cannot read {config_path}: {err.strerror}"
        raise ConfigError(msg) from err
    except yaml.YAMLError as err:
        msg = f"Invalid YAML in {config_path}: {err}"
        raise ConfigError(msg) from err

    # Safety check that config_to_load is a mapping
    if not isinstance(config_to_load, dict):
        msg = f"Invalid config in {config_path}: expected a mapping of settings"
        raise ConfigError(msg)

    # Collect every error before reporting, so they can all be fixed at once
    errors: list[str] = []
    check_unknown_keys(config_to_load, Config, errors)

    # Build the config
    config_kwargs = {}
    if "hidden" in config_to_load:
        hidden = read_dir(config_to_load["hidden"], "hidden", errors)
        if hidden is not None:
            config_kwargs["hidden"] = hidden
    if "extensions" in config_to_load:
        extensions = read_mapping(config_to_load["extensions"], "extensions", errors)
        if extensions is not None:
            config_kwargs["extensions"] = extensions
    if "mimetypes" in config_to_load:
        mimetypes = read_mapping(config_to_load["mimetypes"], "mimetypes", errors)
        if mimetypes is not None:
            config_kwargs["mimetypes"] = mimetypes

    # Get the large files config
    large_files_config = config_to_load.get("large_files", {})
    large_files = read_large_files(large_files_config, errors)

    # Errors check
    if errors:
        details = "\n".join(f"  - {error}" for error in errors)
        msg = f"Invalid config in {config_path}:\n{details}"
        raise ConfigError(msg)

    logger.info("Loaded config from %s", config_path)
    return Config(**config_kwargs, large_files=large_files)
