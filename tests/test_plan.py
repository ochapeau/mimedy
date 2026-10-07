"""Tests for planning the moves, then executing the plan."""

import os
from collections.abc import Callable
from pathlib import Path

import pytest

from mimedy.config import Config
from mimedy.organizer import (
    Failure,
    Ignored,
    Move,
    blocking_file,
    display_target,
    execute,
    plan_moves,
    printable,
    unique_path,
)
from tests.fakes import FakeMagika

# --- Planning -------------------------------------------------------------------


def test_reserved_names_avoid_collisions(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # A name is taken if it exists on disk or was given earlier in the plan
    make_file("PDF/a.pdf")  # already organized
    make_file("a.pdf")
    make_file("a (1).pdf")
    config = Config(extensions={".pdf": "PDF"})

    plan = plan_moves(tmp_path, FakeMagika(), config)

    targets = {move.source.name: move.target.name for move in plan.moves}
    assert targets == {
        "a (1).pdf": "a (1).pdf",  # free when planned first (sorted order)
        "a.pdf": "a (2).pdf",  # "a.pdf" exists, "a (1).pdf" is reserved
    }


def test_empty_folder_gives_empty_plan(tmp_path: Path) -> None:
    # Nothing to organize is an empty plan, not an error
    plan = plan_moves(tmp_path, FakeMagika(), Config())

    assert plan.moves == []
    assert plan.failures == []


def test_subfolders_are_not_planned(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # Only files directly in the folder are organized, never subfolders. As
    # documented, they are not reported as ignored: that would only add noise,
    # starting with the folders mimedy created itself
    make_file("Photos/photo.jpg")

    plan = plan_moves(tmp_path, FakeMagika(), Config())

    assert plan.moves == []
    assert plan.ignored == []
    assert plan.failures == []


def test_unreadable_file_is_a_failure_and_others_are_planned(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # A file Magika cannot read must not stop the others
    photo = make_file("photo.jpg")
    make_file("data.csv")
    status = "permission_error"
    magika = FakeMagika(ok=False, status=status)
    config = Config(extensions={".csv": "Data"})

    plan = plan_moves(tmp_path, magika, config)

    targets = {move.source.name: move.target.name for move in plan.moves}
    assert targets == {"data.csv": "data.csv"}  # the extension rule needs no Magika
    assert plan.failures == [
        Failure(source=photo, reason=f"Magika could not read the file ({status})")
    ]


def test_planning_does_not_touch_the_disk(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # Planning only decides: nothing is created or moved
    make_file("data.csv")

    files_before = sorted(tmp_path.rglob("*"))
    plan_moves(tmp_path, FakeMagika(), Config())
    files_after = sorted(tmp_path.rglob("*"))

    assert files_after == files_before


# --- Ignoring -------------------------------------------------------------------


def test_system_files_are_ignored(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # System files stay in place, and Magika never reads them
    ds_store = make_file(".DS_Store")
    thumbs_db = make_file("Thumbs.db")
    magika = FakeMagika()

    plan = plan_moves(tmp_path, magika, Config())

    assert plan.moves == []
    assert plan.ignored == [
        Ignored(source=ds_store, reason="system file"),
        Ignored(source=thumbs_db, reason="system file"),
    ]
    assert plan.failures == []
    assert magika.calls == []  # ignored before any content analysis


@pytest.mark.parametrize(
    "name",
    [
        "Icon\r",  # the carriage return is part of the name
        "desktop.ini",
        "Desktop.ini",  # system names ignore case, like Windows does
        "THUMBS.DB",
        "._photo.jpg",  # AppleDouble metadata of photo.jpg
        ".directory",
    ],
)
def test_system_file_names_are_recognized(
    tmp_path: Path, make_file: Callable[..., Path], name: str
) -> None:
    # Each kind of system name is recognized (cases above)
    make_file(name)

    plan = plan_moves(tmp_path, FakeMagika(), Config())

    assert [ignored.reason for ignored in plan.ignored] == ["system file"]


def test_system_files_are_moved_when_not_ignored(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # With ignore_system_files: false, .DS_Store is a hidden file again
    ds_store = make_file(".DS_Store")
    config = Config(ignore_system_files=False)

    plan = plan_moves(tmp_path, FakeMagika(), config)

    assert plan.moves == [
        Move(source=ds_store, target=tmp_path / "Hidden/.DS_Store", rule="hidden file")
    ]
    assert plan.ignored == []
    assert plan.failures == []


def test_other_hidden_files_still_go_to_hidden(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # .env is hidden but not a system file: it still goes to Hidden/
    env = make_file(".env")

    plan = plan_moves(tmp_path, FakeMagika(), Config())

    assert plan.moves == [
        Move(source=env, target=tmp_path / "Hidden/.env", rule="hidden file")
    ]
    assert plan.ignored == []
    assert plan.failures == []


def test_ignore_patterns_ignore_case(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # The pattern *.part also matches B.PART
    lowercase = make_file("a.part")
    uppercase = make_file("B.PART")
    config = Config(ignore=("*.part",))

    plan = plan_moves(tmp_path, FakeMagika(), config)

    assert plan.moves == []
    # A set ignores the order: "B" sorts before "a" (uppercase comes first)
    assert set(plan.ignored) == {
        Ignored(source=lowercase, reason="pattern *.part"),
        Ignored(source=uppercase, reason="pattern *.part"),
    }
    assert plan.failures == []


def test_ignore_patterns_match_the_whole_name(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # A pattern is matched against the whole name, not only the extension
    report = make_file("report.docx")
    report_lock = make_file("~$report.docx")
    config = Config(ignore=("~$*",))

    plan = plan_moves(tmp_path, FakeMagika(), config)

    assert [move.source for move in plan.moves] == [report]
    assert plan.ignored == [Ignored(source=report_lock, reason="pattern ~$*")]
    assert plan.failures == []


def test_symbolic_links_are_ignored(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # A link is never moved: a relative link would break once moved, and its
    # target may not even be in the folder. Broken links and links to folders
    # are ignored too, instead of being skipped silently
    real = make_file("docs/real.pdf")
    to_file = tmp_path / "to-file"
    to_file.symlink_to(real.relative_to(tmp_path))  # relative link to a file
    to_folder = tmp_path / "to-folder"
    to_folder.symlink_to(real.parent.relative_to(tmp_path))  # link to a folder
    broken = tmp_path / "broken"
    broken.symlink_to("nowhere")  # its target does not exist
    magika = FakeMagika()

    plan = plan_moves(tmp_path, magika, Config())

    assert plan.moves == []
    assert plan.ignored == [
        Ignored(source=broken, reason="symbolic link"),
        Ignored(source=to_file, reason="symbolic link"),
        Ignored(source=to_folder, reason="symbolic link"),
    ]
    assert plan.failures == []
    assert magika.calls == []


def test_hidden_symbolic_link_is_ignored_too(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # The link check comes first: a hidden link is not sent to Hidden/
    notes = make_file("docs/notes.txt")
    link = tmp_path / ".notes"
    link.symlink_to(notes.relative_to(tmp_path))  # relative link

    plan = plan_moves(tmp_path, FakeMagika(), Config())

    assert plan.moves == []
    assert plan.ignored == [
        Ignored(source=link, reason="symbolic link"),
    ]
    assert plan.failures == []


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs Unix named pipes")
def test_special_files_are_ignored(tmp_path: Path) -> None:
    # A named pipe is neither a file nor a folder: it is reported as ignored,
    # and never opened (reading a pipe would wait forever)
    pipe = tmp_path / "pipe"
    os.mkfifo(pipe)
    magika = FakeMagika()

    plan = plan_moves(tmp_path, magika, Config())

    assert plan.moves == []
    assert plan.ignored == [Ignored(source=pipe, reason="not a regular file")]
    assert magika.calls == []


# --- Blocked target folders -----------------------------------------------------


def test_file_named_like_the_target_folder_is_a_failure(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # A file "Code" takes the name of the folder Code/: both files that should
    # go there are failures, the blocking file included
    code = make_file("Code")
    data = make_file("j.json")
    magika = FakeMagika(mime_type="text/x-python", group="code")

    plan = plan_moves(tmp_path, magika, Config())

    reason = "the folder name 'Code' is taken by a file: rename it"
    assert plan.moves == []  # "Code" is detected as code too: blocked by itself
    assert plan.failures == [
        Failure(source=code, reason=reason),
        Failure(source=data, reason=reason),
    ]


def test_file_blocking_a_parent_folder_is_a_failure(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # The destination Code/Python is blocked one level up, by a file "Code"
    blocker = make_file("Code")
    script = make_file("script.py")
    config = Config(extensions={".py": "Code/Python"})

    plan = plan_moves(tmp_path, FakeMagika(), config)

    # The blocking file goes to Unknown/, but script.py is refused anyway:
    # the plan never relies on the order of the moves
    assert [move.source for move in plan.moves] == [blocker]
    assert [failure.source for failure in plan.failures] == [script]


def test_existing_target_folder_is_fine(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # A real folder Code/ is the normal case: it must not be mistaken for a
    # blocking file
    make_file("Code/old.py")  # creates the folder Code/
    script = make_file("script.py")
    config = Config(extensions={".py": "Code"})

    plan = plan_moves(tmp_path, FakeMagika(), config)

    assert plan.moves == [
        Move(source=script, target=tmp_path / "Code/script.py", rule="extension .py")
    ]
    assert plan.failures == []


def test_file_blocks_the_folder_whatever_the_case(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # On a case-insensitive disk (macOS by default), a file "data" takes the
    # name of the folder Data/. The test only makes sense on such a disk
    probe = make_file("probe")
    if not (tmp_path / probe.name.upper()).exists():
        pytest.skip("this disk is case-sensitive")
    probe.unlink()

    blocker = make_file("data")
    table = make_file("a.csv")
    config = Config(extensions={".csv": "Data"})

    plan = plan_moves(tmp_path, FakeMagika(), config)

    assert [move.source for move in plan.moves] == [blocker]  # goes to Unknown/
    assert [failure.source for failure in plan.failures] == [table]


@pytest.mark.parametrize(
    ("files", "target_dir", "blocker"),
    [
        ([], "Code/Python", None),  # nothing there yet: the way is free
        (["Code/old.py"], "Code/Python", None),  # Code/ is a real folder
        (["Code"], "Code/Python", "Code"),  # blocked at the first level
        (["Code/Python"], "Code/Python", "Code/Python"),  # at the second level
    ],
)
def test_blocking_file_finds_the_first_blocked_level(
    tmp_path: Path,
    make_file: Callable[..., Path],
    files: list[str],
    target_dir: str,
    blocker: str | None,
) -> None:
    # The helper alone: the first level that is not a folder, or None
    for name in files:
        make_file(name)

    expected = None if blocker is None else tmp_path / blocker
    assert blocking_file(tmp_path, target_dir) == expected


# --- Execution ------------------------------------------------------------------


def test_files_are_moved_and_folders_created(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # Execution creates the target folders, then moves the files
    make_file("data.csv")
    config = Config(extensions={".csv": "Data"})
    plan = plan_moves(tmp_path, FakeMagika(), config)

    files_before = sorted(tmp_path.rglob("*"))
    failures = execute(plan)
    files_after = sorted(tmp_path.rglob("*"))

    assert files_before == [tmp_path / "data.csv"]
    assert files_after == [tmp_path / "Data", tmp_path / "Data/data.csv"]
    assert failures == []


def test_target_appeared_since_planning_is_a_failure(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # The plan promised this exact target: never overwrite or rename it
    data = make_file("data.csv")
    config = Config(extensions={".csv": "Data"})
    plan = plan_moves(tmp_path, FakeMagika(), config)

    # Between planning and execution, another file takes the target name
    intruder = make_file(f"Data/{data.name}")
    intruder.write_text("someone else", encoding="utf-8")

    failures = execute(plan)

    assert [failure.source for failure in failures] == [data]
    assert intruder.read_text(encoding="utf-8") == "someone else"  # never overwritten
    assert data.exists()  # the source did not move


def test_vanished_source_is_a_failure_and_others_are_moved(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # A file deleted after planning fails alone: the others are moved
    make_file("data.csv")
    photo = make_file("photo.jpg")
    config = Config(extensions={".csv": "Data", ".jpg": "Photos"})
    plan = plan_moves(tmp_path, FakeMagika(), config)

    # Between planning and execution, the photo is deleted
    photo.unlink()

    failures = execute(plan)

    assert (tmp_path / "Data/data.csv").exists()  # the other file was moved
    assert [failure.source for failure in failures] == [photo]


# --- Small helpers --------------------------------------------------------------


def test_unique_path_counts_up(tmp_path: Path, make_file: Callable[..., Path]) -> None:
    # Free name: kept as is
    assert unique_path(tmp_path / "photo.jpg", reserved=set()) == tmp_path / "photo.jpg"
    # Already given to another file of the plan
    assert (
        unique_path(tmp_path / "photo.jpg", reserved={tmp_path / "photo.jpg"})
        == tmp_path / "photo (1).jpg"
    )
    # Already taken on disk
    make_file("photo.jpg")
    assert (
        unique_path(tmp_path / "photo.jpg", reserved=set())
        == tmp_path / "photo (1).jpg"
    )
    # Both taken on disk: the counter goes on
    make_file("photo (1).jpg")
    assert (
        unique_path(tmp_path / "photo.jpg", reserved=set())
        == tmp_path / "photo (2).jpg"
    )


def test_fake_magika_only_fails_on_unreadable_files(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # The fake replaces chmod(0) in the CLI tests: it must fail on the named
    # files only, the way the real Magika reports a file it cannot read
    secret = make_file("secret")
    other = make_file("other")
    magika = FakeMagika(unreadable={secret.name})

    failed = magika.identify_path(secret)
    assert failed.ok is False
    assert failed.status == "permission_error"  # the real Magika's status
    assert magika.identify_path(other).ok is True


@pytest.mark.parametrize(
    ("name", "shown"),
    [
        ("photo.jpg", "photo.jpg"),
        ("café été.txt", "café été.txt"),  # accents and spaces are printable
        ("Icon\r", "Icon\\r"),
        ("\x1b[31mred", "\\x1b[31mred"),  # a terminal color code stays inert
    ],
)
def test_printable_escapes_control_characters(name: str, shown: str) -> None:
    # Control characters in a name must not garble the terminal
    assert printable(name) == shown


def test_display_target_shows_folder_or_new_name() -> None:
    # The plan shows the folder, or the new name when the file is renamed
    directory = Path("/downloads")
    source = directory / "data.csv"

    kept = Move(source=source, target=directory / "Data" / "data.csv", rule="")
    renamed = Move(source=source, target=directory / "Data" / "data (1).csv", rule="")

    assert display_target(kept, directory) == "Data/"
    assert display_target(renamed, directory) == "Data/data (1).csv"
