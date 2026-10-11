"""End-to-end tests of the mimedy command, with the real Magika model."""

from collections.abc import Callable
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path

import pytest
import typer.rich_utils
from typer.testing import CliRunner

from mimedy.config import default_config_path
from mimedy.journal import JournalMove, JournalWriter, journal_path, read_journal
from mimedy.main import app, plural
from tests.fakes import FakeMagika

runner = CliRunner()


# --- Fixtures -------------------------------------------------------------------


@pytest.fixture
def downloads(tmp_path: Path) -> Path:
    """Return the folder to organize, separate from the config file."""
    folder = tmp_path / "downloads"
    folder.mkdir()
    return folder


@pytest.fixture(autouse=True)
def plain_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give Rich the same plain terminal on every machine: fixed width, no color.

    Typer shows usage errors in a Rich panel that wraps long lines at the
    terminal width (COLUMNS, 80 by default): fixed here, an exported COLUMNS
    can no longer change where messages are cut. Typer also forces colors
    when GITHUB_ACTIONS, FORCE_COLOR or PY_COLORS is set, read once when it is
    imported: color codes then split the checked text ("--undo" is colored),
    so the tests failed in CI only.
    """
    monkeypatch.setenv("COLUMNS", "100")
    monkeypatch.setattr(typer.rich_utils, "FORCE_TERMINAL", None)
    for name in ("FORCE_COLOR", "PY_COLORS"):  # Rich reads FORCE_COLOR itself
        monkeypatch.delenv(name, raising=False)


def files_in(folder: Path) -> list[str]:
    """List every file and folder under folder, as relative paths."""
    return sorted(path.relative_to(folder).as_posix() for path in folder.rglob("*"))


# Always pass --config explicitly, so each test states the rules it relies on.
# Without it, mimedy reads the per-user config: the isolate_user_dirs fixture
# (conftest.py) points it to an empty folder, never to your own config.


# --- Dry run and confirmation ---------------------------------------------------


def test_dry_run_moves_nothing(
    downloads: Path,
    write_config: Callable[..., Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # --dry-run shows the plan and stops there: no file moves
    (downloads / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    config_path = write_config("extensions:\n  .csv: Data\n")

    result = runner.invoke(
        app, [str(downloads), "--config", str(config_path), "--dry-run"]
    )

    assert result.exit_code == 0  # Success
    assert files_in(downloads) == ["data.csv"]
    # Log messages go to caplog, not to result.output
    assert "Dry run: nothing was moved" in caplog.messages


def test_declined_confirmation_moves_nothing(
    downloads: Path, write_config: Callable[..., Path]
) -> None:
    # Without --yes, mimedy asks first: answering no moves nothing
    (downloads / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    config_path = write_config("extensions:\n  .csv: Data\n")

    # input= is what the user types at the "Move 1 file? [y/N]" prompt
    result = runner.invoke(
        app, [str(downloads), "--config", str(config_path)], input="n\n"
    )

    assert result.exit_code == 1  # Declined: the user answered no
    assert "Move 1 file?" in result.output
    assert files_in(downloads) == ["data.csv"]


def test_accepted_confirmation_moves_files(
    downloads: Path, write_config: Callable[..., Path]
) -> None:
    # Answering yes at the prompt performs the plan
    (downloads / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    config_path = write_config("extensions:\n  .csv: Data\n")

    # input= is what the user types at the "Move 1 file? [y/N]" prompt
    result = runner.invoke(
        app, [str(downloads), "--config", str(config_path)], input="y\n"
    )

    assert result.exit_code == 0  # Success
    assert "Move 1 file?" in result.output
    assert files_in(downloads) == ["Data", "Data/data.csv"]


def test_yes_moves_files_without_asking(
    downloads: Path, write_config: Callable[..., Path]
) -> None:
    # --yes skips the question, e.g. in a script
    (downloads / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    config_path = write_config("extensions:\n  .csv: Data\n")

    result = runner.invoke(app, [str(downloads), "--config", str(config_path), "--yes"])

    assert result.exit_code == 0  # Success
    assert "Move" not in result.output
    assert files_in(downloads) == ["Data", "Data/data.csv"]


# --- Journal for --undo ----------------------------------------------------------


def test_a_run_writes_its_journal(
    downloads: Path, write_config: Callable[..., Path]
) -> None:
    # Every real run records its moves, so that --undo can reverse them
    data = downloads / "data.csv"
    data.write_text("a,b\n1,2\n", encoding="utf-8")
    config_path = write_config("extensions:\n  .csv: Data\n")

    result = runner.invoke(app, [str(downloads), "--config", str(config_path), "--yes"])

    assert result.exit_code == 0  # Success
    journal = read_journal(journal_path(downloads))
    assert journal.directory == downloads
    assert journal.moves == [
        JournalMove(source=data, target=downloads / "Data/data.csv")
    ]
    assert journal.created_dirs == [downloads / "Data"]


@pytest.mark.parametrize(
    ("options", "answer"),
    [
        (["--dry-run"], None),  # only shows the plan
        ([], "n\n"),  # the user answers no
    ],
)
def test_no_journal_when_nothing_is_moved(
    downloads: Path,
    write_config: Callable[..., Path],
    options: list[str],
    answer: str | None,
) -> None:
    # Without a real run, the journal of the previous run must stay untouched:
    # here, there was none, so there must still be none
    (downloads / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    config_path = write_config("extensions:\n  .csv: Data\n")

    runner.invoke(
        app, [str(downloads), "--config", str(config_path), *options], input=answer
    )

    assert not journal_path(downloads).exists()


# --- Risky folders --------------------------------------------------------------


def test_home_folder_gets_a_warning(
    downloads: Path,
    write_config: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Organizing the home folder would send every dotfile to Hidden/
    monkeypatch.setenv("HOME", str(downloads))  # downloads plays the home folder
    config_path = write_config()

    result = runner.invoke(
        app, [str(downloads), "--config", str(config_path), "--dry-run"]
    )

    assert result.exit_code == 0  # Success: a warning, not an error
    assert any("is your home folder" in message for message in caplog.messages)


def test_git_repository_gets_a_warning(
    downloads: Path,
    write_config: Callable[..., Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Organizing a code project would scatter its source files
    (downloads / ".git").mkdir()
    config_path = write_config()

    result = runner.invoke(
        app, [str(downloads), "--config", str(config_path), "--dry-run"]
    )

    assert result.exit_code == 0  # Success: a warning, not an error
    assert any("is a Git repository" in message for message in caplog.messages)


def test_ordinary_folder_gets_no_warning(
    downloads: Path,
    write_config: Callable[..., Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # A warning on every run would soon be ignored: only risky folders get one
    config_path = write_config()

    runner.invoke(app, [str(downloads), "--config", str(config_path), "--dry-run"])

    assert not any(
        "is your home folder" in message or "is a Git repository" in message
        for message in caplog.messages
    )


def test_yes_goes_on_despite_the_warning(
    downloads: Path, write_config: Callable[..., Path]
) -> None:
    # Only a warning: a script with --yes stays predictable, and --undo can
    # move the files back
    (downloads / ".git").mkdir()
    (downloads / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    config_path = write_config("extensions:\n  .csv: Data\n")

    result = runner.invoke(app, [str(downloads), "--config", str(config_path), "--yes"])

    assert result.exit_code == 0  # Success
    assert (downloads / "Data/data.csv").exists()


# --- Undo -------------------------------------------------------------------------


def test_undo_restores_the_folder_exactly(
    downloads: Path, write_config: Callable[..., Path]
) -> None:
    # The whole point of --undo: after a run then an undo, the folder is back
    # exactly as it was, created folders included
    (downloads / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (downloads / "script.py").write_text("print(1)\n", encoding="utf-8")
    config_path = write_config("extensions:\n  .csv: Data\n  .py: Code/Python\n")
    files_before = files_in(downloads)
    runner.invoke(app, [str(downloads), "--config", str(config_path), "--yes"])

    result = runner.invoke(app, [str(downloads), "--undo", "--yes"])

    assert result.exit_code == 0
    assert files_before == files_in(downloads)
    assert not journal_path(downloads).exists()


def test_undo_dry_run_changes_nothing(
    downloads: Path, write_config: Callable[..., Path]
) -> None:
    # --dry-run shows the moves back, and leaves the files and the journal alone
    (downloads / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    config_path = write_config("extensions:\n  .csv: Data\n")
    runner.invoke(app, [str(downloads), "--config", str(config_path), "--yes"])
    files_after_run = files_in(downloads)

    result = runner.invoke(app, [str(downloads), "--undo", "--dry-run"])

    assert result.exit_code == 0
    assert files_in(downloads) == files_after_run
    assert journal_path(downloads).exists()  # kept for the real --undo


def test_undo_asks_before_moving_back(
    downloads: Path, write_config: Callable[..., Path]
) -> None:
    # Without --yes, the undo asks first, like a run: answering no changes
    # nothing, and keeps the journal for a later --undo
    (downloads / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    config_path = write_config("extensions:\n  .csv: Data\n")
    runner.invoke(app, [str(downloads), "--config", str(config_path), "--yes"])
    files_after_run = files_in(downloads)

    result = runner.invoke(app, [str(downloads), "--undo"], input="n\n")

    assert result.exit_code == 1  # Declined: the user answered no
    assert "Move back 1 file?" in result.output
    assert files_in(downloads) == files_after_run
    assert journal_path(downloads).exists()


def test_undo_skips_a_file_no_longer_there(
    downloads: Path,
    write_config: Callable[..., Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The user deleted one organized file since the run: the others still go
    # back, and the missing one is reported
    (downloads / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (downloads / "notes.txt").write_text("hello\n", encoding="utf-8")
    config_path = write_config("extensions:\n  .csv: Data\n  .txt: Text\n")
    runner.invoke(app, [str(downloads), "--config", str(config_path), "--yes"])
    (downloads / "Data/data.csv").unlink()

    result = runner.invoke(app, [str(downloads), "--undo", "--yes"])

    assert result.exit_code == 1  # At least one file could not be processed
    assert "Skipped 'Data/data.csv': no longer there" in caplog.messages
    assert files_in(downloads) == ["notes.txt"]  # both created folders removed
    # The deleted file is forgotten: nothing is left to undo
    assert not journal_path(downloads).exists()


def test_undo_without_journal_has_nothing_to_undo(
    downloads: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # A folder never organized: not an error, just nothing to do
    result = runner.invoke(app, [str(downloads), "--undo"])

    assert result.exit_code == 0
    assert any(message.startswith("Nothing to undo") for message in caplog.messages)


def test_second_undo_has_nothing_to_undo(
    downloads: Path, write_config: Callable[..., Path], caplog: pytest.LogCaptureFixture
) -> None:
    # Only the last run can be undone, and only once
    (downloads / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    config_path = write_config("extensions:\n  .csv: Data\n")
    runner.invoke(app, [str(downloads), "--config", str(config_path), "--yes"])
    runner.invoke(app, [str(downloads), "--undo", "--yes"])

    result = runner.invoke(app, [str(downloads), "--undo", "--yes"])

    assert result.exit_code == 0
    assert any(message.startswith("Nothing to undo") for message in caplog.messages)


@pytest.mark.parametrize(
    ("options", "option"),
    [
        (["--config", "config.yaml"], "--config"),
        (["--lowercase"], "--lowercase"),
    ],
)
def test_undo_refuses_options_that_only_organize(
    downloads: Path, options: list[str], option: str
) -> None:
    # Refused rather than silently ignored: they mean nothing for an undo
    result = runner.invoke(app, [str(downloads), "--undo", *options])

    assert result.exit_code == 2  # Usage error
    assert "cannot be combined with --undo" in result.output


def test_damaged_journal_exits_with_1(
    downloads: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # Refuse rather than guess: a journal that cannot be trusted moves nothing
    path = journal_path(downloads)
    path.parent.mkdir(parents=True)
    path.write_text("not json\n", encoding="utf-8")

    result = runner.invoke(app, [str(downloads), "--undo", "--yes"])

    assert result.exit_code == 1
    assert any(
        "Invalid line 1 of the journal" in message for message in caplog.messages
    )


def test_journal_of_another_folder_is_refused(
    downloads: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # Almost impossible with the hash, but never move files of another folder.
    # The file of the other folder really exists: without the check, the undo
    # would move it back, so the test cannot pass for another reason
    other = tmp_path / "other"
    moved = other / "Data/data.csv"
    moved.parent.mkdir(parents=True)
    moved.write_text("a,b\n1,2\n", encoding="utf-8")
    with JournalWriter(journal_path(downloads), other) as writer:
        writer.record_move(other / "data.csv", moved)

    result = runner.invoke(app, [str(downloads), "--undo", "--yes"])

    assert result.exit_code == 1  # The journal cannot be trusted
    assert moved.exists()  # the other folder was left alone
    assert any("not for this folder" in message for message in caplog.messages)


# --- Verbose mode ---------------------------------------------------------------


def test_verbose_lists_ignored_files(
    downloads: Path,
    write_config: Callable[..., Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Ignored files only show with --verbose, but the summary always counts them
    (downloads / ".DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1")
    (downloads / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    config_path = write_config("extensions:\n  .csv: Data\n")

    result = runner.invoke(
        app, [str(downloads), "--config", str(config_path), "--dry-run", "--verbose"]
    )

    assert result.exit_code == 0  # Success
    # Debug messages only show with --verbose
    assert "Ignored '.DS_Store': system file" in caplog.messages
    assert "1 file to move into 1 folder, 0 skipped, 1 ignored" in caplog.messages


# --- Real detection -------------------------------------------------------------


def test_pdf_without_extension_is_detected_by_content(
    downloads: Path, write_config: Callable[..., Path]
) -> None:
    # The real Magika model recognizes a PDF by its content, without extension
    file = downloads / "invoice"
    file.write_bytes(
        b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
        b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"
    )
    config_path = write_config("mimetypes:\n  application/pdf: PDF\n")

    result = runner.invoke(app, [str(downloads), "--config", str(config_path), "--yes"])

    assert result.exit_code == 0  # Success
    assert "Move" not in result.output
    assert files_in(downloads) == ["PDF", "PDF/invoice"]


# --- Exit codes -----------------------------------------------------------------


def test_missing_directory_exits_with_2(
    tmp_path: Path, write_config: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Typer checks DIRECTORY before mimedy even starts. Relative paths keep the
    # message short and the same on every machine: an absolute temporary path
    # made Rich cut "does not exist" on some machines (Docker)
    monkeypatch.chdir(tmp_path)  # tmp_path is new and empty: "missing" never exists
    write_config()

    result = runner.invoke(app, ["missing", "--config", "config.yaml"])

    assert result.exit_code == 2  # Usage error: invalid DIRECTORY argument
    assert "does not exist" in result.output


def test_invalid_config_exits_with_2(
    downloads: Path,
    write_config: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # A typo in the config stops mimedy before any move. The config is given by
    # a relative path, to keep the message short (see the test above)
    monkeypatch.chdir(tmp_path)
    write_config("extentions:\n  .csv: Data\n")

    result = runner.invoke(app, [str(downloads), "--config", "config.yaml", "--yes"])

    assert result.exit_code == 2  # Usage error: invalid config
    assert "did you mean" in result.output


def test_invalid_default_config_does_not_mention_the_option(
    downloads: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Without --config, an error in the per-user config must not say "Invalid
    # value for --config": the user never typed that option
    xdg_path = tmp_path / "xdg-config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_path))
    config_path = xdg_path / "mimedy/config.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("hiden: Dotfiles\n", encoding="utf-8")

    result = runner.invoke(app, [str(downloads), "--yes"])

    assert result.exit_code == 2  # Usage error: invalid config
    assert "the config file" in result.output
    assert "--config" not in result.output


def test_unreadable_file_exits_with_1(
    downloads: Path,
    write_config: Callable[..., Path],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The only file cannot be read: it is skipped, nothing is moved. The fake
    # Magika fails on it: chmod(0) does not stop root (Docker) nor Windows
    document = downloads / "document"
    document.write_text("secret", encoding="utf-8")
    # Replace the name Magika where main.py uses it, not in the magika package
    fake = FakeMagika(unreadable={document.name})
    monkeypatch.setattr("mimedy.main.Magika", lambda: fake)
    config_path = write_config()

    result = runner.invoke(app, [str(downloads), "--config", str(config_path), "--yes"])

    assert result.exit_code == 1  # At least one file could not be processed
    assert any("Skipped 'document'" in message for message in caplog.messages)


def test_failure_after_moving_exits_with_1(
    downloads: Path,
    write_config: Callable[..., Path],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Unlike the test above, one file can be moved: mimedy goes on to move it,
    # then still reports the unreadable one with the exit code
    document = downloads / "document"
    document.write_text("secret", encoding="utf-8")
    fake = FakeMagika(unreadable={document.name})
    monkeypatch.setattr("mimedy.main.Magika", lambda: fake)
    (downloads / "data.csv").write_text(
        "a,b\n1,2\n", encoding="utf-8"
    )  # goes to Data/ by extension
    config_path = write_config("extensions:\n  .csv: Data\n")

    result = runner.invoke(app, [str(downloads), "--config", str(config_path), "--yes"])

    assert result.exit_code == 1  # At least one file could not be processed
    assert files_in(downloads) == ["Data", "Data/data.csv", "document"]
    # The unreadable file was skipped while planning: it is not a failed move
    assert "Done: 1 moved, 0 failed" in caplog.messages


def test_blocked_target_folder_is_reported_before_moving(
    downloads: Path,
    write_config: Callable[..., Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The reported bug: Magika detects "Code" and j.json as code, so both go to
    # Code/, a name taken by the file "Code" itself. The plan must show them as
    # skipped, instead of announcing moves that then fail
    (downloads / "Code").write_text(
        "def f():\n    return 1\n\nclass A:\n    pass\n", encoding="utf-8"
    )
    (downloads / "j.json").write_text('{"a": 1, "b": [1, 2, 3]}\n', encoding="utf-8")
    config_path = write_config()

    result = runner.invoke(app, [str(downloads), "--config", str(config_path), "--yes"])

    assert result.exit_code == 1  # At least one file could not be processed
    assert files_in(downloads) == ["Code", "j.json"]  # nothing moved
    assert "Nothing to move" in caplog.messages  # both were skipped
    assert any("Skipped 'Code'" in message for message in caplog.messages)
    assert any("Skipped 'j.json'" in message for message in caplog.messages)


# --- Config file location -------------------------------------------------------


def test_config_is_read_from_default_location_without_option(
    downloads: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Without --config, the per-user config file is used
    xdg_path = tmp_path / "xdg-config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_path))
    config_path = xdg_path / "mimedy/config.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("extensions:\n  .csv: Data\n", encoding="utf-8")
    (downloads / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    result = runner.invoke(app, [str(downloads), "--yes"])

    assert result.exit_code == 0  # Success
    assert "Move" not in result.output
    assert files_in(downloads) == ["Data", "Data/data.csv"]


def test_missing_config_option_file_exits_with_2(
    downloads: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A file given with --config must exist, unlike the default one. Relative
    # path: a short message, the same on every machine
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, [str(downloads), "--config", "missing.yaml", "--yes"])

    assert result.exit_code == 2  # Usage error: the --config file is missing
    assert "Config file not found" in result.output


# --- Messages -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, "0 files"), (1, "1 file"), (2, "2 files")],
)
def test_plural_only_drops_the_s_for_one(count: int, expected: str) -> None:
    # English plural: 0 files, 1 file, 2 files
    assert plural(count, "file") == expected


# --- Version --------------------------------------------------------------------


@pytest.mark.parametrize("option", ["--version", "-V"])
def test_version_is_shown_without_directory(option: str) -> None:
    # --version works alone, although DIRECTORY is otherwise required
    result = runner.invoke(app, [option])

    assert result.exit_code == 0  # Success
    assert result.output == f"mimedy {version('mimedy')}\n"


# --- Config initialization ------------------------------------------------------


def test_init_config_creates_the_example_at_the_default_location() -> None:
    # --init-config copies the shipped example where mimedy looks for it
    result = runner.invoke(app, ["--init-config"])

    assert result.exit_code == 0  # Success
    assert default_config_path().read_text(encoding="utf-8") == (
        files("mimedy") / "config.example.yaml"
    ).read_text(encoding="utf-8")


def test_init_config_never_overwrites_an_existing_config() -> None:
    # --init-config must never destroy a config the user wrote
    config_path = default_config_path()
    content = "extensions:\n  .csv: Data\n"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(content, encoding="utf-8")

    result = runner.invoke(app, ["--init-config"])

    assert result.exit_code == 1  # Refused: an existing config is never overwritten
    assert config_path.read_text(encoding="utf-8") == content
