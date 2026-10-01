import logging
import shutil
from pathlib import Path
from typing import Any

from magika import Magika

logger = logging.getLogger("mimedy.organizer")


def is_hidden(path: Path) -> bool:
    return path.name.startswith(".")


def is_large(path: Path, threshold_mb: float) -> bool:
    # Usage of 1000 and not 1024 to better align with OS file browsers
    filesize_mb = path.stat().st_size / 1000 / 1000

    return filesize_mb >= threshold_mb


def get_file_mimetype_and_group(m: Magika, file: Path) -> tuple[str, str]:
    # The magic happens here !
    res = m.identify_path(file)
    return (res.output.mime_type, res.output.group)


def determine_target_directory(
    file: Path, magika: Magika, config: dict[str, Any], *, lowercase: bool
) -> tuple[str, str]:
    """Return the target directory and the rule that selected it."""
    extension = file.suffix

    if is_hidden(file):
        return config["hidden"], "hidden file"
    threshold_mb = config["large_files"]["threshold_mb"]
    if is_large(file, threshold_mb):
        return config["large_files"]["target_dir"], f"larger than {threshold_mb} MB"
    if extension in config["extensions"]:
        return config["extensions"][extension], f"extension {extension}"

    mimetype, group = get_file_mimetype_and_group(magika, file)
    if mimetype in config["mimetypes"]:
        return config["mimetypes"][mimetype], f"mimetype {mimetype}"

    target_dir = group if lowercase else group.capitalize()
    return target_dir, f"magika group {group} ({mimetype})"


def unique_path(path: Path) -> Path:
    # Never overwrite: "photo.jpg" -> "photo (1).jpg", "photo (2).jpg", ...
    candidate = path
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
        counter += 1
    return candidate


def display_target(file: Path, target: Path, directory: Path) -> str:
    # "Photos/" when the name is kept, "Photos/photo (1).jpg" when renamed
    relative = target.relative_to(directory)
    if target.name == file.name:
        return f"{relative.parent}/"
    return str(relative)


def move_file(file: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(file, target)


def organize_directory(
    directory: Path,
    config: dict[str, Any],
    *,
    dry_run: bool = False,
    lowercase: bool = False,
) -> None:
    logger.info("Organizing %s", directory)

    # Instantiate magika once
    magika = Magika()

    moved = 0
    folders: set[str] = set()

    for file in sorted(directory.iterdir()):
        if not file.is_file():
            continue

        target_dir, rule = determine_target_directory(
            file, magika, config, lowercase=lowercase
        )
        logger.debug("'%s' → %s/ (rule: %s)", file.name, target_dir, rule)

        target = unique_path(directory / target_dir / file.name)
        shown = display_target(file, target, directory)

        if dry_run:
            logger.info("[dry-run] Would move '%s' → %s", file.name, shown)
        else:
            move_file(file, target)
            logger.info("Moved '%s' → %s", file.name, shown)

        moved += 1
        folders.add(target_dir)

    if dry_run:
        logger.info("Done: would move %d files into %d folders", moved, len(folders))
    else:
        logger.info("Done: %d files moved into %d folders", moved, len(folders))
