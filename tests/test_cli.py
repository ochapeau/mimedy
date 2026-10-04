"""End-to-end tests of the mimedy command, with the real Magika model."""

from collections.abc import Callable
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mimedy.config import default_config_path
from mimedy.main import app

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


# Always pass --config explicitly: by default mimedy reads config.yaml from the
# current directory, which is the project root here, with your own config in it.


# --- Dry run and confirmation ---------------------------------------------------


def test_dry_run_moves_nothing(
    downloads: Path,
    write_config: Callable[..., Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    (downloads / "data.csv").write_text("a,b\n1,2\n")
    config = write_config("extensions:\n  .csv: Data\n")

    result = runner.invoke(app, [str(downloads), "--config", str(config), "--dry-run"])

    assert result.exit_code == 0
    assert files_in(downloads) == ["data.csv"]
    # Log messages go to caplog, not to result.output
    assert "Dry run: nothing was moved" in caplog.messages


def test_declined_confirmation_moves_nothing(
    downloads: Path, write_config: Callable[..., Path]
) -> None:
    (downloads / "data.csv").write_text("a,b\n1,2\n")
    config = write_config("extensions:\n  .csv: Data\n")

    # input= is what the user types at the "Move 1 files? [y/N]" prompt
    result = runner.invoke(app, [str(downloads), "--config", str(config)], input="n\n")

    assert result.exit_code == 1  # Aborted
    assert "Move 1 files?" in result.output
    assert files_in(downloads) == ["data.csv"]


def test_accepted_confirmation_moves_files(
    downloads: Path, write_config: Callable[..., Path]
) -> None:
    (downloads / "data.csv").write_text("a,b\n1,2\n")
    config = write_config("extensions:\n  .csv: Data\n")

    # input= is what the user types at the "Move 1 files? [y/N]" prompt
    result = runner.invoke(app, [str(downloads), "--config", str(config)], input="y\n")

    assert result.exit_code == 0  # Success
    assert "Move 1 files?" in result.output
    assert files_in(downloads) == ["Data", "Data/data.csv"]


def test_yes_moves_files_without_asking(
    downloads: Path, write_config: Callable[..., Path]
) -> None:
    (downloads / "data.csv").write_text("a,b\n1,2\n")
    config = write_config("extensions:\n  .csv: Data\n")

    result = runner.invoke(app, [str(downloads), "--config", str(config), "--yes"])

    assert result.exit_code == 0  # Success
    assert "Move" not in result.output
    assert files_in(downloads) == ["Data", "Data/data.csv"]


# --- Real detection -------------------------------------------------------------


def test_pdf_without_extension_is_detected_by_content(
    downloads: Path, write_config: Callable[..., Path]
) -> None:
    file = downloads / "invoice"
    file.write_bytes(
        b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
        b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"
    )
    config = write_config("mimetypes:\n  application/pdf: PDF\n")

    result = runner.invoke(app, [str(downloads), "--config", str(config), "--yes"])

    assert result.exit_code == 0  # Success
    assert "Move" not in result.output
    assert files_in(downloads) == ["PDF", "PDF/invoice"]


# --- Exit codes -----------------------------------------------------------------


def test_missing_directory_exits_with_2(
    tmp_path: Path, write_config: Callable[..., Path]
) -> None:
    missing_dir = tmp_path / "missing"  # tmp_path is new and empty: never exists
    config = write_config()

    result = runner.invoke(app, [str(missing_dir), "--config", str(config)])

    assert result.exit_code == 2  # Usage error
    assert "does not exist" in result.output


def test_invalid_config_exits_with_2(
    downloads: Path, write_config: Callable[..., Path]
) -> None:
    invalid_config = write_config("extentions:\n  .csv: Data\n")

    result = runner.invoke(
        app, [str(downloads), "--config", str(invalid_config), "--yes"]
    )

    assert result.exit_code == 2  # Usage error
    assert "did you mean" in result.output


def test_unreadable_file_exits_with_1(
    downloads: Path,
    write_config: Callable[..., Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    file = downloads / "document"
    file.write_text("secret")
    file.chmod(0)  # make the file unreadable
    config = write_config()

    result = runner.invoke(app, [str(downloads), "--config", str(config), "--yes"])

    assert result.exit_code == 1  # At least one file move failed
    assert any("Skipped 'document'" in message for message in caplog.messages)


# --- Config file location -------------------------------------------------------


def test_config_is_read_from_default_location_without_option(
    downloads: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Writing default location config file
    xdg_path = tmp_path / "xdg-config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_path))
    path = xdg_path / "mimedy/config.yaml"
    path.parent.mkdir(parents=True)
    path.write_text("extensions:\n  .csv: Data\n")

    # Testing the command
    (downloads / "data.csv").write_text("a,b\n1,2\n")

    result = runner.invoke(app, [str(downloads), "--yes"])

    assert result.exit_code == 0  # Success
    assert "Move" not in result.output
    assert files_in(downloads) == ["Data", "Data/data.csv"]


def test_missing_config_option_file_exits_with_2(
    downloads: Path, tmp_path: Path
) -> None:
    config = tmp_path / "nope.yaml"
    result = runner.invoke(app, [str(downloads), "--config", str(config), "--yes"])

    assert result.exit_code == 2  # Usage error
    assert "Config file not found" in result.output


# --- Version --------------------------------------------------------------------


@pytest.mark.parametrize("option", ["--version", "-V"])
def test_version_is_shown_without_directory(option: str) -> None:
    result = runner.invoke(app, [option])

    assert result.exit_code == 0  # Success
    assert result.output == f"mimedy {version('mimedy')}\n"


# --- Config initialization ------------------------------------------------------


def test_init_config_creates_the_example_at_the_default_location() -> None:
    result = runner.invoke(app, ["--init-config"])

    assert result.exit_code == 0  # Success
    assert (
        default_config_path().read_text()
        == (files("mimedy") / "config.example.yaml").read_text()
    )


def test_init_config_never_overwrites_an_existing_config() -> None:
    # Write a config file at default_config_path()
    path = default_config_path()
    content = "extensions:\n  .csv: Data\n"
    path.parent.mkdir(parents=True)
    path.write_text(content)

    result = runner.invoke(app, ["--init-config"])

    assert result.exit_code == 1  # Aborted
    assert default_config_path().read_text() == content
