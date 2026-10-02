import logging
from pathlib import Path
from typing import Annotated

import typer

from mimedy.errors import ConfigError
from mimedy.organizer import execute, log_plan, plan_moves
from mimedy.utils import init_logging, load_config

# Exit codes
EXIT_OK = 0
EXIT_FAILURES = 1  # the run completed, but at least one file failed
# Invalid arguments or configuration exit with 2, handled by Typer

logger = logging.getLogger("mimedy.main")

app = typer.Typer(no_args_is_help=True, add_completion=False)


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
        Path, typer.Option("--config", help="YAML configuration file.")
    ] = Path("config.yaml"),
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show planned moves without moving.")
    ] = False,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Move without asking for confirmation.")
    ] = False,
    lowercase: Annotated[
        bool, typer.Option("--lowercase", help="Keep Magika folder names lowercase.")
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show the rule applied to each file."),
    ] = False,
) -> None:
    """Organize a folder by real file type, detected from content with Magika."""
    init_logging(verbose=verbose)

    try:
        config = load_config(config_path)
    except ConfigError as err:
        # Reported by Typer as a usage error, with exit code 2
        raise typer.BadParameter(str(err), param_hint="--config") from err

    # Phase 1: decide where every file goes, without touching anything
    logger.info("Organizing %s", directory)
    plan = plan_moves(directory, config, lowercase=lowercase)
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
