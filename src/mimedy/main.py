from pathlib import Path
from typing import Annotated

import typer

from mimedy.organizer import organize_directory
from mimedy.utils import init_logging, load_config

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def main(
    directory: Annotated[Path, typer.Argument(help="Folder to organize.")],
    config_path: Annotated[
        Path, typer.Option("--config", help="YAML configuration file.")
    ] = Path("config.yaml"),
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show planned moves without moving.")
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
    config = load_config(config_path)
    organize_directory(directory, config, dry_run=dry_run, lowercase=lowercase)


if __name__ == "__main__":
    app()
