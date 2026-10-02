class MimedyError(Exception):
    """Base class for all mimedy errors."""


class ConfigError(MimedyError):
    """The configuration file cannot be loaded."""


class ClassificationError(MimedyError):
    """A file cannot be classified."""
