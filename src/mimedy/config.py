import logging
from dataclasses import dataclass, field, fields
from difflib import get_close_matches
from pathlib import Path

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


def check_unknown_keys(
    data: dict, config_class: type, section: str, errors: list[str]
) -> None:
    """Add an error for each key of data that is not a field of config_class."""
    authorized_keys = {f.name for f in fields(config_class)}
    unknown_keys = data.keys() - authorized_keys
    for key in sorted(unknown_keys):
        close_match = get_close_matches(key, authorized_keys, n=1)
        err_msg = f"Unknown key '{key}'"
        if section:
            err_msg += f" in {section}"
        if close_match:
            err_msg += f" (did you mean '{close_match[0]}'?)"
        errors.append(err_msg)


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
    check_unknown_keys(config_to_load, Config, "", errors)

    # Get the large files config
    large_files_config = config_to_load.get("large_files", {})
    if isinstance(large_files_config, dict):
        check_unknown_keys(large_files_config, LargeFilesConfig, "large_files", errors)
    else:
        errors.append("'large_files' must be a mapping")

    if errors:
        details = "\n".join(f"  - {error}" for error in errors)
        msg = f"Invalid config in {config_path}:\n{details}"
        raise ConfigError(msg)

    # Build the config
    kwargs = {}
    if "hidden" in config_to_load:
        kwargs["hidden"] = config_to_load["hidden"]
    if "extensions" in config_to_load:
        kwargs["extensions"] = config_to_load["extensions"]
    if "mimetypes" in config_to_load:
        kwargs["mimetypes"] = config_to_load["mimetypes"]
    logger.info("Loaded config from %s", config_path)
    return Config(**kwargs, large_files=LargeFilesConfig(**large_files_config))
