"""Command-line interface of mimedy."""

import logging
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path
from typing import Annotated

import typer
from magika import Magika

from mimedy.config import default_config_path, load_config
from mimedy.errors import ConfigError
from mimedy.organizer import execute, log_plan, plan_moves

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
    target_config_path.write_text((files("mimedy") / "config.example.yaml").read_text())

    typer.echo(f"Created config file: {target_config_path}")
    raise typer.Exit(EXIT_OK)


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

    try:
        config = load_config(config_path)
    except ConfigError as e:
        # Reported by Typer as a usage error, with exit code 2
        raise typer.BadParameter(str(e), param_hint="--config") from e

    # Loading the Magika model is slow: do it once for all files
    magika = Magika()

    # Phase 1: decide where every file goes, without touching anything
    logger.info("Organizing %s", directory)
    plan = plan_moves(directory, magika, config, lowercase=lowercase)
    log_plan(plan)
    planning_code = EXIT_FAILURES if plan.failures else EXIT_OK

    if not plan.moves:
        logger.info("Nothing to move")
        raise typer.Exit(planning_code)

    logger.info(
        "%d files to move into %d folders, %d skipped",
        len(plan.moves),
        len(plan.folders),
        len(plan.failures),
    )

    if dry_run:
        logger.info("Dry run: nothing was moved")
        raise typer.Exit(planning_code)

    if not yes:
        typer.confirm(f"Move {len(plan.moves)} files?", abort=True)

    # Phase 2: perform the plan
    failures = execute(plan)
    logger.info(
        "Done: %d moved, %d failed", len(plan.moves) - len(failures), len(failures)
    )

    if failures or plan.failures:
        raise typer.Exit(EXIT_FAILURES)


if __name__ == "__main__":
    app()
