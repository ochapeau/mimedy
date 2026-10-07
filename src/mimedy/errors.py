"""Exceptions raised by mimedy."""

from pathlib import Path


class MimedyError(Exception):
    """Base class for all mimedy errors."""


class ConfigError(MimedyError):
    """The configuration file cannot be loaded."""


class ClassificationError(MimedyError):
    """A file cannot be classified."""


class JournalError(MimedyError):
    """The journal of a previous run cannot be read."""


class UnreadableJournalError(JournalError):
    """The journal file cannot be read at all (permissions, empty file...)."""

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f"Cannot read the journal {path}: {reason}")
        self.path = path
        self.reason = reason


class InvalidJournalLineError(JournalError):
    """A line of the journal is not what mimedy writes.

    number is the line number in the file, starting at 1 for the header.
    """

    def __init__(self, path: Path, number: int, reason: str) -> None:
        super().__init__(f"Invalid line {number} of the journal {path}: {reason}")
        self.path = path
        self.number = number
        self.reason = reason
