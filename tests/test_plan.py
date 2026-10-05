"""Tests for planning the moves, then executing the plan."""

from collections.abc import Callable
from pathlib import Path

import pytest

from mimedy.config import Config
from mimedy.organizer import (
    Failure,
    Ignored,
    Move,
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
    plan = plan_moves(tmp_path, FakeMagika(), Config())

    assert plan.moves == []  # no moves
    assert plan.failures == []  # no failures


def test_subfolders_are_not_planned(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    make_file("Photos/photo.jpg")

    plan = plan_moves(tmp_path, FakeMagika(), Config())

    assert plan.moves == []  # no moves because subfolders not planned
    assert plan.failures == []  # no failures


def test_unreadable_file_is_a_failure_and_others_are_planned(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    photo = make_file("photo.jpg")
    make_file("data.csv")
    status = "permission_error"
    magika = FakeMagika(ok=False, status=status)
    config = Config(extensions={".csv": "Data"})

    plan = plan_moves(tmp_path, magika, config)

    targets = {move.source.name: move.target.name for move in plan.moves}
    # only csv planned, as jpg unreadable by fake magika
    assert targets == {"data.csv": "data.csv"}
    # only jpg file is a failure
    assert plan.failures == [
        Failure(source=photo, reason=f"Magika could not read the file ({status})")
    ]


def test_planning_does_not_touch_the_disk(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    make_file("data.csv")

    before_plan_dir_state = sorted(tmp_path.rglob("*"))
    plan_moves(tmp_path, FakeMagika(), Config())
    after_plan_dir_state = sorted(tmp_path.rglob("*"))

    assert before_plan_dir_state == after_plan_dir_state  # disk not modified by plan


# --- Ignoring -------------------------------------------------------------------


def test_system_files_are_ignored(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
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
    assert magika.calls == []


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
    make_file(name)

    plan = plan_moves(tmp_path, FakeMagika(), Config())

    assert [ignored.reason for ignored in plan.ignored] == ["system file"]


def test_system_files_are_moved_when_not_ignored(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    ds_store = make_file(".DS_Store")
    config = Config(ignore_system_files=False)

    plan = plan_moves(tmp_path, FakeMagika(), config)

    assert plan.moves == [
        Move(ds_store, tmp_path / "Hidden" / ".DS_Store", "hidden file")
    ]
    assert plan.ignored == []
    assert plan.failures == []


def test_other_hidden_files_still_go_to_hidden(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    env = make_file(".env")

    plan = plan_moves(tmp_path, FakeMagika(), Config())

    assert plan.moves == [Move(env, tmp_path / "Hidden" / ".env", "hidden file")]
    assert plan.ignored == []
    assert plan.failures == []


def test_ignore_patterns_ignore_case(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    a = make_file("a.part")
    b = make_file("B.PART")
    config = Config(ignore=("*.part",))

    plan = plan_moves(tmp_path, FakeMagika(), config)

    assert plan.moves == []
    # A set ignores the order: "B" sorts before "a" (uppercase comes first)
    assert set(plan.ignored) == {
        Ignored(source=a, reason="pattern *.part"),
        Ignored(source=b, reason="pattern *.part"),
    }
    assert plan.failures == []


def test_ignore_patterns_match_the_whole_name(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    report = make_file("report.docx")
    report_lock = make_file("~$report.docx")
    config = Config(ignore=("~$*",))

    plan = plan_moves(tmp_path, FakeMagika(), config)

    assert [move.source for move in plan.moves] == [report]
    assert plan.ignored == [Ignored(source=report_lock, reason="pattern ~$*")]
    assert plan.failures == []


# --- Execution ------------------------------------------------------------------


def test_files_are_moved_and_folders_created(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    make_file("data.csv")
    config = Config(extensions={".csv": "Data"})
    plan = plan_moves(tmp_path, FakeMagika(), config)

    before_execute_dir_state = sorted(tmp_path.rglob("*"))
    failures = execute(plan)
    after_execute_dir_state = sorted(tmp_path.rglob("*"))

    assert before_execute_dir_state == [tmp_path / "data.csv"]
    # execute created and moved the file to subfolder
    assert after_execute_dir_state == [tmp_path / "Data", tmp_path / "Data/data.csv"]
    assert failures == []


def test_target_appeared_since_planning_is_a_failure(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    make_file("data.csv")
    config = Config(extensions={".csv": "Data"})
    plan = plan_moves(tmp_path, FakeMagika(), config)

    # Between planning and execution, another file takes the target name
    intruder = make_file("Data/data.csv")
    intruder.write_text("someone else")

    failures = execute(plan)

    assert [failure.source.name for failure in failures] == ["data.csv"]
    assert intruder.read_text() == "someone else"  # never overwritten
    assert (tmp_path / "data.csv").exists()  # the source did not move


def test_vanished_source_is_a_failure_and_others_are_moved(
    tmp_path: Path, make_file: Callable[..., Path]
) -> None:
    # Planning two files
    make_file("data.csv")
    photo = make_file("photo.jpg")
    config = Config(extensions={".csv": "Data", ".jpg": "Photos"})
    plan = plan_moves(tmp_path, FakeMagika(), config)

    # delete photo
    photo.unlink()

    failures = execute(plan)

    assert (tmp_path / "Data" / "data.csv").exists()  # csv has been moved
    assert [failure.source for failure in failures] == [photo]


# --- Small helpers --------------------------------------------------------------


def test_unique_path_counts_up(tmp_path: Path, make_file: Callable[..., Path]) -> None:
    # Basic test
    assert unique_path(tmp_path / "photo.jpg", reserved=set()) == tmp_path / "photo.jpg"
    # Reserved test
    assert (
        unique_path(tmp_path / "photo.jpg", reserved={tmp_path / "photo.jpg"})
        == tmp_path / "photo (1).jpg"
    )
    # Collision test
    make_file("photo.jpg")
    assert (
        unique_path(tmp_path / "photo.jpg", reserved=set())
        == tmp_path / "photo (1).jpg"
    )
    # Second collision test
    make_file("photo (1).jpg")
    assert (
        unique_path(tmp_path / "photo.jpg", reserved=set())
        == tmp_path / "photo (2).jpg"
    )


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
    assert printable(name) == shown


def test_display_target_shows_folder_or_new_name() -> None:
    directory = Path("/downloads")
    source = directory / "data.csv"

    kept = Move(source=source, target=directory / "Data" / "data.csv", rule="")
    renamed = Move(source=source, target=directory / "Data" / "data (1).csv", rule="")

    assert display_target(kept, directory) == "Data/"
    assert display_target(renamed, directory) == "Data/data (1).csv"
