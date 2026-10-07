"""Tests for writing and reading back the journal of a run."""

import sys
from pathlib import Path

import pytest

from mimedy.errors import InvalidJournalLineError, UnreadableJournalError
from mimedy.journal import (
    Journal,
    JournalMove,
    JournalWriter,
    default_state_dir,
    journal_path,
    read_journal,
)

# --- Journal location -----------------------------------------------------------


def test_default_state_dir_uses_xdg_state_home(tmp_path: Path) -> None:
    # The isolate_user_dirs fixture sets XDG_STATE_HOME to tmp_path/"xdg-state"
    assert default_state_dir() == tmp_path / "xdg-state/mimedy"


@pytest.mark.parametrize("xdg_state_home", [None, "", "relative/state"])
def test_default_state_dir_falls_back_to_local_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, xdg_state_home: str | None
) -> None:
    # Unset, empty or relative: the XDG spec says to use the default
    if xdg_state_home is None:
        monkeypatch.delenv("XDG_STATE_HOME")
    else:
        monkeypatch.setenv("XDG_STATE_HOME", xdg_state_home)
    monkeypatch.setenv("HOME", str(tmp_path))

    assert default_state_dir() == tmp_path / ".local/state/mimedy"


def test_default_state_dir_uses_localappdata_on_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Local, not Roaming: the journals hold paths of this computer only
    localappdata_path = tmp_path / "localappdata"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(localappdata_path))

    assert default_state_dir() == localappdata_path / "mimedy"


def test_each_directory_has_its_own_journal(tmp_path: Path) -> None:
    # The name only depends on the folder: same folder, same journal
    state_dir = tmp_path / "state"
    downloads = Path("/home/me/Downloads")
    desktop = Path("/home/me/Desktop")

    downloads_journal = journal_path(downloads, state_dir)
    desktop_journal = journal_path(desktop, state_dir)

    assert journal_path(downloads, state_dir) == downloads_journal
    assert desktop_journal != downloads_journal
    assert downloads_journal.parent == state_dir
    assert downloads_journal.suffix == ".jsonl"


def test_journals_go_to_the_default_state_dir() -> None:
    # Without state_dir, mimedy's own folder is used
    journal = journal_path(Path("/home/me/Downloads"))

    assert journal.parent == default_state_dir()


# --- Writing and reading back ---------------------------------------------------

# The journals are written in tmp_path. The organized folder is never created:
# the journal only stores its paths as text.
DOWNLOADS = Path("/home/me/Downloads")


def test_recorded_run_is_read_back(tmp_path: Path) -> None:
    # What is written must be read back exactly, in the same order
    path = tmp_path / "journal.jsonl"
    invoice = DOWNLOADS / "invoice"
    photo = DOWNLOADS / "photo.jpg"

    with JournalWriter(path, DOWNLOADS) as writer:
        writer.record_move(invoice, DOWNLOADS / "PDF/invoice")
        writer.record_created_dir(DOWNLOADS / "PDF")
        writer.record_move(photo, DOWNLOADS / "Photos/photo.jpg")

    journal = read_journal(path)

    assert journal == Journal(
        directory=DOWNLOADS,
        moves=[
            JournalMove(source=invoice, target=DOWNLOADS / "PDF/invoice"),
            JournalMove(source=photo, target=DOWNLOADS / "Photos/photo.jpg"),
        ],
        created_dirs=[DOWNLOADS / "PDF"],
    )


def test_each_line_is_written_right_away(tmp_path: Path) -> None:
    # Checked while the file is still open: without flush(), the lines would
    # still sit in memory, and a crash would lose them
    path = tmp_path / "journal.jsonl"

    with JournalWriter(path, DOWNLOADS) as writer:
        writer.record_move(DOWNLOADS / "invoice", DOWNLOADS / "PDF/invoice")

        lines = path.read_text().splitlines(keepends=True)
        assert len(lines) == 2  # header + move
        assert '"source"' in lines[1]
        assert lines[1].endswith("\n")  # complete, not cut


def test_new_run_replaces_the_previous_journal(tmp_path: Path) -> None:
    # Only the last run can be undone
    path = tmp_path / "journal.jsonl"

    with JournalWriter(path, DOWNLOADS) as writer:
        writer.record_move(DOWNLOADS / "old", DOWNLOADS / "PDF/old")
    with JournalWriter(path, DOWNLOADS) as writer:
        writer.record_move(DOWNLOADS / "new", DOWNLOADS / "PDF/new")

    journal = read_journal(path)

    assert journal.moves == [
        JournalMove(source=DOWNLOADS / "new", target=DOWNLOADS / "PDF/new")
    ]


def test_missing_journal_reads_as_none(tmp_path: Path) -> None:
    # No journal: nothing to undo, which is not an error
    assert read_journal(tmp_path / "missing.jsonl") is None


# --- Damaged journals -----------------------------------------------------------

HEADER = '{"version": 1, "directory": "/home/me/Downloads"}\n'
MOVE = '{"source": "/home/me/Downloads/a", "target": "/home/me/Downloads/X/a"}\n'


def test_truncated_last_line_is_ignored(tmp_path: Path) -> None:
    # A crash cut the second move in the middle (no final "\n"): the complete
    # move before it is still read, so the run can be undone
    path = tmp_path / "journal.jsonl"
    path.write_text(HEADER + MOVE + '{"source": "/home/me/Downl')

    journal = read_journal(path)

    assert journal.moves == [
        JournalMove(source=DOWNLOADS / "a", target=DOWNLOADS / "X/a")
    ]


def test_invalid_line_in_the_middle_is_an_error(tmp_path: Path) -> None:
    # A broken line 2, followed by a valid line 3: not a crash, a damaged file
    path = tmp_path / "journal.jsonl"
    path.write_text(HEADER + "not json\n" + MOVE)

    with pytest.raises(InvalidJournalLineError) as exc_info:
        read_journal(path)
    assert exc_info.value.number == 2


@pytest.mark.parametrize(
    ("text", "number"),
    [
        # The header itself is broken
        ("not json\n", 1),
        # A version this mimedy does not know
        ('{"version": 99, "directory": "/home/me/Downloads"}\n', 1),
        # A relative directory in the header
        ('{"version": 1, "directory": "Downloads"}\n', 1),
        # A line that is valid JSON, but not an object
        (HEADER + "42\n", 2),
        # A record with unexpected keys
        (HEADER + '{"what": 1}\n', 2),
        # A path that climbs out of the folder with "..": the other path is
        # valid, so that only ".." can be the reason for the refusal
        (
            HEADER + '{"source": "/home/me/Downloads/../.ssh/id",'
            ' "target": "/home/me/Downloads/X/id"}\n',
            2,
        ),
        # A path that is not text
        (HEADER + '{"created_dir": 42}\n', 2),
        # A path in another folder
        (HEADER + '{"created_dir": "/etc"}\n', 2),
        # The organized folder itself: undoing would try to remove it
        (HEADER + '{"created_dir": "/home/me/Downloads"}\n', 2),
    ],
)
def test_invalid_journal_lines_are_rejected(
    tmp_path: Path, text: str, number: int
) -> None:
    # Any line that mimedy would not write is refused, with its line number
    path = tmp_path / "journal.jsonl"
    path.write_text(text)

    with pytest.raises(InvalidJournalLineError) as exc_info:
        read_journal(path)
    assert exc_info.value.number == number


def test_empty_journal_is_unreadable(tmp_path: Path) -> None:
    # Not even a header: there is nothing to check the rest against
    path = tmp_path / "journal.jsonl"
    path.write_text("")

    with pytest.raises(UnreadableJournalError):
        read_journal(path)


def test_journal_that_cannot_be_opened_is_unreadable(tmp_path: Path) -> None:
    # A folder instead of a file: opening it raises an OSError
    with pytest.raises(UnreadableJournalError):
        read_journal(tmp_path)
