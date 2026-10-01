from pathlib import Path
from typing import Annotated

import typer
from organizer import organize_directory
from utils import init_logging, load_config


def main(
    directory: Annotated[Path, typer.Argument()],
    config_path: Annotated[Path, typer.Option("--config")] = Path("config.yaml"),
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    lowercase: Annotated[bool, typer.Option("--lowercase")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    init_logging(verbose=verbose)
    config = load_config(config_path)
    organize_directory(directory, config, dry_run=dry_run, lowercase=lowercase)


if __name__ == "__main__":
    typer.run(main)
