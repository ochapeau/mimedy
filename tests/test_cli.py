"""End-to-end tests of the mimedy command, with the real Magika model."""

from collections.abc import Callable
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mimedy.config import default_config_path
from mimedy.main import app, plural

runner = CliRunner()


# --- Fixtures -------------------------------------------------------------------


@pytest.fixture
def downloads(tmp_path: Path) -> Path:
    """Return the folder to organize, separate from the config file."""
    folder = tmp_path / "downloads"
    folder.mkdir()
    return folder


def files_in(folder: Path) -> list[str]:
    """List every file and folder under folder, as relative paths."""
    return sorted(path.relative_to(folder).as_posix() for path in folder.rglob("*"))


# Always pass --config explicitly, so each test states the rules it relies on.
# Without it, mimedy reads the per-user config: the isolate_user_config fixture
# (conftest.py) points it to an empty folder, never to your own config.


# --- Dry run and confirmation ---------------------------------------------------


def test_dry_run_moves_nothing(
    downloads: Path,
    write_config: Callable[..., Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # --dry-run shows the plan and stops there: no file moves
    (downloads / "data.csv").write_text("a,b\n1,2\n")
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
    (downloads / "data.csv").write_text("a,b\n1,2\n")
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
    (downloads / "data.csv").write_text("a,b\n1,2\n")
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
    (downloads / "data.csv").write_text("a,b\n1,2\n")
    config_path = write_config("extensions:\n  .csv: Data\n")

    result = runner.invoke(app, [str(downloads), "--config", str(config_path), "--yes"])

    assert result.exit_code == 0  # Success
    assert "Move" not in result.output
    assert files_in(downloads) == ["Data", "Data/data.csv"]


# --- Verbose mode ---------------------------------------------------------------


def test_verbose_lists_ignored_files(
    downloads: Path,
    write_config: Callable[..., Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Ignored files only show with --verbose, but the summary always counts them
    (downloads / ".DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1")
    (downloads / "data.csv").write_text("a,b\n1,2\n")
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
    tmp_path: Path, write_config: Callable[..., Path]
) -> None:
    # Typer checks DIRECTORY before mimedy even starts
    missing = tmp_path / "missing"  # tmp_path is new and empty: never exists
    config_path = write_config()

    result = runner.invoke(app, [str(missing), "--config", str(config_path)])

    assert result.exit_code == 2  # Usage error: invalid DIRECTORY argument
    assert "does not exist" in result.output


def test_invalid_config_exits_with_2(
    downloads: Path, write_config: Callable[..., Path]
) -> None:
    # A typo in the config stops mimedy before any move
    config_path = write_config("extentions:\n  .csv: Data\n")

    result = runner.invoke(app, [str(downloads), "--config", str(config_path), "--yes"])

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
) -> None:
    # The only file cannot be read: it is skipped, nothing is moved
    file = downloads / "document"
    file.write_text("secret")
    file.chmod(0)  # make the file unreadable
    config_path = write_config()

    result = runner.invoke(app, [str(downloads), "--config", str(config_path), "--yes"])

    assert result.exit_code == 1  # At least one file could not be processed
    assert any("Skipped 'document'" in message for message in caplog.messages)


def test_failure_after_moving_exits_with_1(
    downloads: Path,
    write_config: Callable[..., Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Unlike the test above, one file can be moved: mimedy goes on to move it,
    # then still reports the unreadable one with the exit code
    file = downloads / "document"
    file.write_text("secret")
    file.chmod(0)  # make the file unreadable
    (downloads / "data.csv").write_text("a,b\n1,2\n")
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
    (downloads / "Code").write_text("def f():\n    return 1\n\nclass A:\n    pass\n")
    (downloads / "j.json").write_text('{"a": 1, "b": [1, 2, 3]}\n')
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
    config_path.write_text("extensions:\n  .csv: Data\n")
    (downloads / "data.csv").write_text("a,b\n1,2\n")

    result = runner.invoke(app, [str(downloads), "--yes"])

    assert result.exit_code == 0  # Success
    assert "Move" not in result.output
    assert files_in(downloads) == ["Data", "Data/data.csv"]


def test_missing_config_option_file_exits_with_2(
    downloads: Path, tmp_path: Path
) -> None:
    # A file given with --config must exist, unlike the default one
    config_path = tmp_path / "missing.yaml"

    result = runner.invoke(app, [str(downloads), "--config", str(config_path), "--yes"])

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
    assert (
        default_config_path().read_text()
        == (files("mimedy") / "config.example.yaml").read_text()
    )


def test_init_config_never_overwrites_an_existing_config() -> None:
    # --init-config must never destroy a config the user wrote
    config_path = default_config_path()
    content = "extensions:\n  .csv: Data\n"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(content)

    result = runner.invoke(app, ["--init-config"])

    assert result.exit_code == 1  # Refused: an existing config is never overwritten
    assert config_path.read_text() == content
