"""Record the moves of a run, so that --undo can move the files back.

Each organized folder has its own journal, which only keeps its last run.
A journal is a JSON Lines file: one JSON object per line, appended as soon as
each move succeeds, so that even an interrupted run can be undone.

    {"version": 1, "directory": "/home/me/Downloads"}
    {"source": "/home/me/Downloads/invoice", "target": "/home/me/Downloads/PDF/invoice"}
    {"created_dir": "/home/me/Downloads/PDF"}
"""

import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import IO

from mimedy.errors import InvalidJournalLineError, UnreadableJournalError

JOURNAL_VERSION = 1


@dataclass(frozen=True)
class JournalMove:
    """A move that was performed: the file went from source to target."""

    source: Path
    target: Path


@dataclass
class Journal:
    """The last run in a folder, as read back from its journal file."""

    directory: Path
    moves: list[JournalMove] = field(default_factory=list)
    created_dirs: list[Path] = field(default_factory=list)


def default_state_dir() -> Path:
    """Return the folder where mimedy keeps its journals.

    - Linux and macOS: $XDG_STATE_HOME/mimedy, which is ~/.local/state/mimedy
      by default
    - Windows: %LOCALAPPDATA%\\mimedy, which is
      C:\\Users\\<name>\\AppData\\Local\\mimedy by default

    Journals are state that mimedy writes for itself, not settings: XDG keeps
    them apart from the config, and on Windows they stay in Local, on this
    computer only, since they hold paths that only exist here.
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        xdg = os.environ.get("XDG_STATE_HOME", "")
        # The XDG spec says to ignore an empty or relative value
        if xdg and Path(xdg).is_absolute():
            base = Path(xdg)
        else:
            base = Path.home() / ".local" / "state"
    return base / "mimedy"


def journal_path(directory: Path, state_dir: Path | None = None) -> Path:
    """Return the journal file of an organized folder.

    The file name is a hash of the folder path: the same folder always gets
    the same journal, and the name is safe whatever the path contains.
    """
    if state_dir is None:
        state_dir = default_state_dir()
    digest = hashlib.sha256(str(directory).encode()).hexdigest()[:16]
    return state_dir / f"{digest}.jsonl"


class JournalWriter:
    """Write the journal of a run, one line per event, as they happen.

    Use it as a context manager: the file is created (or replaced) when
    entering, with a header line, and closed when leaving.

        with JournalWriter(path, directory) as writer:
            writer.record_move(source, target)
    """

    def __init__(self, path: Path, directory: Path) -> None:
        self.path = path
        self.directory = directory
        self._file: IO[str] | None = None

    def __enter__(self) -> "JournalWriter":
        header = {"version": JOURNAL_VERSION, "directory": str(self.directory)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("w", encoding="utf-8")
        self._write(header)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # Returning None lets any exception of the with block go on. If
        # __enter__ failed, Python does not call __exit__ at all
        if self._file is not None:
            self._file.close()

    def _write(self, record: dict[str, object]) -> None:
        """Append one JSON line and flush it to disk right away."""
        self._file.write(json.dumps(record) + "\n")
        self._file.flush()

    def record_move(self, source: Path, target: Path) -> None:
        """Record a move that just succeeded."""
        record = {"source": str(source), "target": str(target)}
        self._write(record)

    def record_created_dir(self, path: Path) -> None:
        """Record a folder that mimedy just created."""
        record = {"created_dir": str(path)}
        self._write(record)


def _parse_line(line: str, number: int, path: Path) -> dict[str, object]:
    """Decode one line of the journal, which must be a JSON object.

    Raise InvalidJournalLineError instead of json.JSONDecodeError.
    """
    try:
        record = json.loads(line)
    except json.JSONDecodeError as e:
        raise InvalidJournalLineError(path, number, "not valid JSON") from e
    if not isinstance(record, dict):
        reason = f"expected a JSON object, got {type(record).__name__}"
        raise InvalidJournalLineError(path, number, reason)
    return record


def _read_path(
    record: dict[str, object], key: str, directory: Path, number: int, path: Path
) -> Path:
    """Read a path of the journal, which must stay strictly inside directory.

    path and number locate the line in the journal, for the error message.
    """
    value = record[key]
    if not isinstance(value, str):
        reason = f"'{key}' must be a path, got {type(value).__name__}"
        raise InvalidJournalLineError(path, number, reason)
    moved = Path(value)
    # is_relative_to only compares the parts of the path: "/dl/../etc" counts
    # as inside "/dl", so ".." must be refused explicitly
    if ".." in moved.parts or moved == directory or not moved.is_relative_to(directory):
        reason = f"'{key}' is outside {directory}"
        raise InvalidJournalLineError(path, number, reason)
    return moved


def read_journal(path: Path) -> Journal | None:
    """Read a journal back. Return None if there is none.

    A crash while writing can only cut the last line: an incomplete last
    line is ignored. Raise UnreadableJournalError if the file cannot be read
    or is empty, and InvalidJournalLineError for any line that mimedy would
    not write (header, version, record, or a path outside the folder).
    """
    # 1. Read the whole file. Only the expected errors are caught, each one
    #    turned into what the caller needs: None, or an UnreadableJournalError
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None  # No journal: nothing to undo, not an error
    except OSError as e:
        raise UnreadableJournalError(path, e.strerror or str(e)) from e

    # 2. Every complete line ends with "\n". What follows the last "\n" is
    #    either "" or a line cut by a crash: it is dropped in both cases
    *lines, _cut = text.split("\n")
    if not lines:
        raise UnreadableJournalError(path, "the file is empty")

    # 3. Header: right version, and an absolute directory
    header = _parse_line(lines[0], 1, path)
    version = header.get("version")
    if version != JOURNAL_VERSION:
        reason = f"unsupported version {version!r}, expected {JOURNAL_VERSION}"
        raise InvalidJournalLineError(path, 1, reason)
    directory = header.get("directory")
    if not isinstance(directory, str) or not Path(directory).is_absolute():
        raise InvalidJournalLineError(path, 1, "'directory' must be an absolute path")
    journal = Journal(Path(directory))

    # 4. Records: the exact set of keys says what the line is
    for number, line in enumerate(lines[1:], start=2):
        record = _parse_line(line, number, path)
        if record.keys() == {"source", "target"}:
            journal.moves.append(
                JournalMove(
                    source=_read_path(
                        record, "source", journal.directory, number, path
                    ),
                    target=_read_path(
                        record, "target", journal.directory, number, path
                    ),
                )
            )
        elif record.keys() == {"created_dir"}:
            journal.created_dirs.append(
                _read_path(record, "created_dir", journal.directory, number, path)
            )
        else:
            keys = ", ".join(sorted(record))
            reason = f"unexpected record with keys {keys}"
            raise InvalidJournalLineError(path, number, reason)
    return journal
