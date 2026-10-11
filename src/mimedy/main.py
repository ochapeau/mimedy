"""Command-line interface of mimedy."""

import logging
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path
from typing import Annotated

import typer
from magika import Magika

from mimedy.config import default_config_path, load_config
from mimedy.errors import ConfigError, InvalidJournalLineError, JournalError
from mimedy.journal import JournalWriter, journal_path, read_journal
from mimedy.organizer import execute, log_plan, plan_moves
from mimedy.undo import (
    log_undo_plan,
    plan_undo,
    remove_created_folders,
    update_journal,
)

# Exit codes
EXIT_OK = 0
EXIT_FAILURES = 1  # the run completed, but at least one file failed
# Invalid arguments or configuration exit with 2, handled by Typer

logger = logging.getLogger("mimedy.main")

app = typer.Typer(
    no_args_is_help=True,
    add_completion=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def init_logging(*, verbose: bool = False) -> None:
    """Configure log output: short messages, or detailed ones with --verbose."""
    if verbose:
        log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    else:
        log_format = "[%(levelname)s] %(message)s"
    logging.basicConfig(format=log_format)

    # Only our own loggers go down to DEBUG, not third-party libraries
    logging.getLogger("mimedy").setLevel(logging.DEBUG if verbose else logging.INFO)


def show_version(value: bool) -> None:
    """Print the version and exit, before any other argument is checked."""
    if value:
        typer.echo(f"mimedy {version('mimedy')}")
        raise typer.Exit(EXIT_OK)


def init_config(value: bool) -> None:
    """Copy the example config to the default location, then exit.

    An existing config is never overwritten.
    """
    if not value:
        return

    target_config_path = default_config_path()

    if target_config_path.exists():
        typer.echo(f"Config file already exists: {target_config_path}", err=True)
        raise typer.Exit(EXIT_FAILURES)

    # Create the folder that holds the file (~/.config/mimedy), not the file itself
    target_config_path.parent.mkdir(parents=True, exist_ok=True)
    target_config_path.write_text(
        (files("mimedy") / "config.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    typer.echo(f"Created config file: {target_config_path}")
    raise typer.Exit(EXIT_OK)


def plural(count: int, word: str) -> str:
    """Return "1 file", "2 files", "0 files"."""
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def warn_about_risky_folder(directory: Path, hidden: str) -> None:
    """Warn when directory is a folder that is almost never meant to be organized.

    Only a warning: the confirmation still lets the user go on, --yes goes on
    without asking, and --undo can move the files back.
    """
    # directory was resolved by Typer: resolve the home folder too (on macOS,
    # /var and /private/var are the same folder under two names)
    if directory == Path.home().resolve():
        logger.warning(
            "%s is your home folder: its hidden files (.zshrc, .gitconfig...) "
            "would go to %s/",
            directory,
            hidden,
        )
    # .git may be a folder, or a file in a Git worktree: exists() covers both
    if (directory / ".git").exists():
        logger.warning(
            "%s is a Git repository: organizing it would scatter its files", directory
        )


def undo_last_run(directory: Path, *, dry_run: bool, yes: bool) -> None:
    """Move the files of the last run in directory back, then exit.

    Neither the config nor Magika are loaded: the journal holds everything,
    and a config made invalid since the run cannot prevent the undo.
    """
    logger.info("Undoing the last run in %s", directory)
    path = journal_path(directory)
    try:
        journal = read_journal(path)
        # Refuse rather than guess: the journal must be the one of this folder
        if journal is not None and journal.directory != directory:
            reason = f"written for {journal.directory}, not for this folder"
            raise InvalidJournalLineError(path, 1, reason)
    except JournalError as e:
        # A message for the user, not a traceback: logging.exception would add it
        logger.error("%s", e)  # noqa: TRY400
        raise typer.Exit(EXIT_FAILURES) from e

    if journal is None:
        logger.info("Nothing to undo in %s", directory)
        raise typer.Exit(EXIT_OK)

    plan = plan_undo(journal)
    log_undo_plan(plan)
    files_back = plural(len(plan.moves), "file")
    logger.info("%s to move back, %d skipped", files_back, len(plan.failures))

    if dry_run:
        logger.info("Dry run: nothing was moved")
        raise typer.Exit(EXIT_FAILURES if plan.failures else EXIT_OK)

    if plan.moves and not yes:
        typer.confirm(f"Move back {files_back}?", abort=True)

    # No recorder: the undo itself is not recorded in a journal
    failures = execute(plan)
    removed = remove_created_folders(journal)
    update_journal(path, journal, plan.failures + failures, removed)
    logger.info(
        "Done: %d moved back, %d failed, %s removed",
        len(plan.moves) - len(failures),
        len(failures),
        plural(len(removed), "empty folder"),
    )
    raise typer.Exit(EXIT_FAILURES if failures or plan.failures else EXIT_OK)


@app.command()
def main(  # noqa: PLR0913, PLR0917 (one parameter per CLI option)
    directory: Annotated[
        Path,
        typer.Argument(
            help="Folder to organize.",
            exists=True,
            file_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ],
    config_path: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help=f"YAML configuration file (default: {default_config_path()}).",
        ),
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", "-n", help="Show planned moves without moving.")
    ] = False,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Move without asking for confirmation.")
    ] = False,
    lowercase: Annotated[
        bool,
        typer.Option("--lowercase", "-l", help="Keep Magika folder names lowercase."),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show the rule applied to each file."),
    ] = False,
    undo: Annotated[
        bool,
        typer.Option(
            "--undo", "-u", help="Move the files of the last run back, then stop."
        ),
    ] = False,
    show_version_flag: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            callback=show_version,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
    init_config_flag: Annotated[
        bool,
        typer.Option(
            "--init-config",
            callback=init_config,
            is_eager=True,
            help="Create a commented example config at the default location.",
        ),
    ] = False,
) -> None:
    """Organize a folder by real file type, detected from content with Magika."""
    init_logging(verbose=verbose)

    if undo:
        # These options only mean something when organizing: refuse them
        # rather than silently ignore them
        if config_path is not None:
            msg = "cannot be combined with --undo"
            raise typer.BadParameter(msg, param_hint="--config")
        if lowercase:
            msg = "cannot be combined with --undo"
            raise typer.BadParameter(msg, param_hint="--lowercase")
        undo_last_run(directory, dry_run=dry_run, yes=yes)

    try:
        config = load_config(config_path)
    except ConfigError as e:
        # Reported by Typer as a usage error, with exit code 2
        hint = "--config" if config_path is not None else "the config file"
        raise typer.BadParameter(str(e), param_hint=hint) from e

    # Loading the Magika model is slow: do it once for all files
    magika = Magika()

    # Phase 1: decide where every file goes, without touching anything
    logger.info("Organizing %s", directory)
    # Before the plan, so that the warning is read before the confirmation
    warn_about_risky_folder(directory, config.hidden)
    plan = plan_moves(directory, magika, config, lowercase=lowercase)
    log_plan(plan)
    planning_code = EXIT_FAILURES if plan.failures else EXIT_OK

    if not plan.moves:
        logger.info("Nothing to move")
        raise typer.Exit(planning_code)

    files_to_move = plural(len(plan.moves), "file")
    logger.info(
        "%s to move into %s, %d skipped, %d ignored",
        files_to_move,
        plural(len(plan.folders), "folder"),
        len(plan.failures),
        len(plan.ignored),
    )

    if dry_run:
        logger.info("Dry run: nothing was moved")
        raise typer.Exit(planning_code)

    if not yes:
        typer.confirm(f"Move {files_to_move}?", abort=True)

    # Phase 2: perform the plan, recording every folder created and every move
    # in the journal of this folder, for --undo. Dry runs, declined
    # confirmations and empty plans stopped above: they leave no journal
    path = journal_path(directory)
    logger.debug("Recording the moves in %s", path)
    with JournalWriter(path, directory) as journal:
        failures = execute(plan, recorder=journal)
    logger.info(
        "Done: %d moved, %d failed", len(plan.moves) - len(failures), len(failures)
    )

    if failures or plan.failures:
        raise typer.Exit(EXIT_FAILURES)


if __name__ == "__main__":
    app()
