"""Tests for undoing a run: the plan back, the cleanup, the journal left."""

from collections.abc import Callable
from pathlib import Path

from mimedy.journal import Journal, JournalMove, JournalWriter, read_journal
from mimedy.organizer import Failure, Move
from mimedy.undo import plan_undo, remove_created_folders, update_journal

# Each test builds the journal of a past run by hand, then puts the files
# where that run left them: no Magika, no real run needed.

# --- Planning the moves back ----------------------------------------------------


def test_moves_are_planned_back_newest_first(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # The last move of the run is undone first, the exact reverse of the run
    data = make_file("Data/data.csv")
    photo = make_file("Photos/photo.jpg")
    journal = Journal(
        directory=tmp_path,
        moves=[
            JournalMove(source=tmp_path / "data.csv", target=data),
            JournalMove(source=tmp_path / "photo.jpg", target=photo),
        ],
    )

    plan = plan_undo(journal)

    assert plan.moves == [
        Move(source=photo, target=tmp_path / "photo.jpg", rule="undo"),
        Move(source=data, target=tmp_path / "data.csv", rule="undo"),
    ]
    assert plan.failures == []


def test_renamed_file_gets_its_original_name_back(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # The run renamed report.pdf to "report (1).pdf" to avoid a collision
    renamed = make_file("PDF/report (1).pdf")
    journal = Journal(
        directory=tmp_path,
        moves=[JournalMove(source=tmp_path / "report.pdf", target=renamed)],
    )

    plan = plan_undo(journal)

    assert plan.moves[0].source == renamed
    assert plan.moves[0].target == tmp_path / "report.pdf"


def test_file_no_longer_there_is_a_failure(tmp_path: Path) -> None:
    # Deleted or moved by the user since the run: nothing to move back
    gone = tmp_path / "Data/data.csv"  # never created
    journal = Journal(
        directory=tmp_path,
        moves=[JournalMove(source=tmp_path / "data.csv", target=gone)],
    )

    plan = plan_undo(journal)

    assert plan.moves == []
    assert plan.failures == [Failure(source=gone, reason="no longer there")]


def test_original_place_taken_is_a_failure(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # A new data.csv arrived where the old one was: never overwrite it
    moved = make_file("Data/data.csv")
    make_file("data.csv")  # the newcomer
    journal = Journal(
        directory=tmp_path,
        moves=[JournalMove(source=tmp_path / "data.csv", target=moved)],
    )

    plan = plan_undo(journal)

    assert plan.moves == []
    assert plan.failures == [
        Failure(source=moved, reason="its original place is taken")
    ]


def test_planning_the_undo_does_not_touch_the_disk(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # Planning only decides, as for a normal run
    data = make_file("Data/data.csv")
    journal = Journal(
        directory=tmp_path,
        moves=[JournalMove(source=tmp_path / "data.csv", target=data)],
        created_dirs=[tmp_path / "Data"],
    )
    files_before = sorted(tmp_path.rglob("*"))

    plan_undo(journal)

    assert files_before == sorted(tmp_path.rglob("*"))


# --- Removing the created folders ------------------------------------------------


def test_empty_created_folders_are_removed_deepest_first(tmp_path: Path) -> None:
    # Code/ cannot be removed while Code/Python/ is in it
    (tmp_path / "Code/Python").mkdir(parents=True)
    journal = Journal(
        directory=tmp_path,
        created_dirs=[tmp_path / "Code", tmp_path / "Code/Python"],  # top first
    )

    removed = remove_created_folders(journal)

    assert removed == [tmp_path / "Code/Python", tmp_path / "Code"]  # deepest first
    assert not (tmp_path / "Code").exists()


def test_folder_with_a_user_file_is_kept(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # The user put a file there since the run: it is theirs now
    make_file("Data/notes.txt")
    journal = Journal(directory=tmp_path, created_dirs=[tmp_path / "Data"])

    removed = remove_created_folders(journal)

    assert removed == []
    assert (tmp_path / "Data/notes.txt").exists()


def test_folder_with_only_system_files_is_removed(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # The Finder wrote a .DS_Store when the user opened the folder: it still
    # counts as empty, or the cleanup would almost never work on macOS
    make_file("Data/.DS_Store")
    journal = Journal(directory=tmp_path, created_dirs=[tmp_path / "Data"])

    removed = remove_created_folders(journal)

    assert removed == [tmp_path / "Data/"]
    assert not (tmp_path / "Data/").exists()


def test_folder_not_in_the_journal_is_never_removed(tmp_path: Path) -> None:
    # Photos/ existed before the run: even empty, it is not mimedy's to remove
    (tmp_path / "Photos").mkdir()
    journal = Journal(directory=tmp_path)  # no created folder

    removed = remove_created_folders(journal)

    assert removed == []
    assert (tmp_path / "Photos/").exists()


def test_folder_already_gone_is_skipped(tmp_path: Path) -> None:
    # The user deleted it already: nothing to do, and no error
    journal = Journal(directory=tmp_path, created_dirs=[tmp_path / "Data"])

    removed = remove_created_folders(journal)

    assert removed == []


# --- What is left in the journal -------------------------------------------------


def test_complete_undo_deletes_the_journal(tmp_path: Path) -> None:
    # Everything was undone: a second --undo must find nothing to undo
    path = tmp_path / "journal.jsonl"
    with JournalWriter(path, tmp_path) as writer:
        writer.record_move(tmp_path / "data.csv", tmp_path / "Data/data.csv")
    journal = read_journal(path)

    update_journal(path, journal, failures=[], removed=[tmp_path / "Data"])

    assert not path.exists()


def test_partial_undo_keeps_what_is_left(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # The photo could not go back, its original place being taken: a second
    # --undo only tries it again, and still knows Photos/ to remove it afterwards
    path = tmp_path / "journal.jsonl"
    data_move = JournalMove(
        source=tmp_path / "data.csv", target=tmp_path / "Data/data.csv"
    )
    photo = make_file("Photos/photo.jpg")  # still where mimedy put it
    photo_move = JournalMove(source=tmp_path / "photo.jpg", target=photo)
    journal = Journal(
        directory=tmp_path,
        moves=[data_move, photo_move],
        created_dirs=[tmp_path / "Data", tmp_path / "Photos"],
    )
    failures = [Failure(source=photo_move.target, reason="its original place is taken")]

    update_journal(path, journal, failures, removed=[tmp_path / "Data"])

    assert read_journal(path) == Journal(
        directory=tmp_path, moves=[photo_move], created_dirs=[tmp_path / "Photos"]
    )


def test_deleted_file_is_forgotten(tmp_path: Path) -> None:
    # The user deleted the file since the run: it can never go back, so it is
    # not kept for a second --undo, which would report it again forever
    path = tmp_path / "journal.jsonl"
    deleted = JournalMove(
        source=tmp_path / "data.csv", target=tmp_path / "Data/data.csv"
    )
    with JournalWriter(path, tmp_path) as writer:  # the journal of the run
        writer.record_move(deleted.source, deleted.target)
    journal = read_journal(path)
    failures = [Failure(source=deleted.target, reason="no longer there")]

    update_journal(path, journal, failures, removed=[])

    assert not path.exists()  # nothing left that could be undone
