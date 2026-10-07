"""Exceptions raised by mimedy, and how to describe any error to the user."""


class MimedyError(Exception):
    """Base class for all mimedy errors."""


class ConfigError(MimedyError):
    """The configuration file cannot be loaded."""


class ClassificationError(MimedyError):
    """A file cannot be classified."""


def describe_error(e: Exception) -> str:
    """Return a short reason for an error, e.g. "Permission denied".

    For an OSError, only its strerror: str(e) would read "[Errno 13]
    Permission denied: '/path'", with a path the caller's message already
    shows. Any other exception is already a readable message: str(e).
    """
    if isinstance(e, OSError) and e.strerror:
        return e.strerror
    return str(e)
