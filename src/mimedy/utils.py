import logging
from pathlib import Path
from typing import Any

import yaml

from mimedy.errors import ConfigError

logger = logging.getLogger("mimedy.utils")

# Default values of config:
DEFAULT_CONFIG: dict[str, Any] = {
    # Hidden files (starts with '.' in UNIX)
    "hidden": "Hidden",
    # Large files
    "large_files": {"threshold_mb": 100, "target_dir": "Large"},
    # Extensions
    "extensions": {},
    # Mimetypes
    "mimetypes": {},
}


# Simple 2-level merge
def merge_config(user_config: dict[str, Any]) -> dict[str, Any]:
    config = DEFAULT_CONFIG.copy()
    for key, default_value in DEFAULT_CONFIG.items():
        user_value = user_config.get(key)
        if isinstance(default_value, dict) and isinstance(user_value, dict):
            config[key] = default_value.copy()
            config[key].update(user_value)
        elif user_value is not None:
            config[key] = user_value
    return config


def init_logging(*, verbose: bool = False) -> None:
    if verbose:
        log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    else:
        log_format = "[%(levelname)s] %(message)s"
    logging.basicConfig(format=log_format)

    # Only our own loggers go down to DEBUG, not third-party libraries
    logging.getLogger("mimedy").setLevel(logging.DEBUG if verbose else logging.INFO)


def load_config(config_path: Path) -> dict[str, Any]:
    try:
        with config_path.open() as f:
            user_config = yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning("Config file not found: %s, using defaults", config_path)
        return DEFAULT_CONFIG.copy()
    except OSError as err:
        msg = f"Cannot read {config_path}: {err.strerror}"
        raise ConfigError(msg) from err
    except yaml.YAMLError as err:
        msg = f"Invalid YAML in {config_path}: {err}"
        raise ConfigError(msg) from err

    if not isinstance(user_config, dict):
        msg = f"Invalid config in {config_path}: expected a mapping of settings"
        raise ConfigError(msg)
    logger.info("Loaded config from %s", config_path)
    return merge_config(user_config)
