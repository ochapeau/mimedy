"""Plan where each file goes, then move the files."""

import errno
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from magika import Magika

from mimedy.config import Config
from mimedy.errors import ClassificationError

logger = logging.getLogger("mimedy.organizer")


@dataclass(frozen=True)
class Move:
    """A planned move of one file."""

    source: Path
    target: Path
    rule: str


@dataclass(frozen=True)
class Failure:
    """A file that could not be planned or moved."""

    source: Path
    reason: str


@dataclass
class Plan:
    """Every move to perform, computed without touching the disk."""

    directory: Path
    moves: list[Move] = field(default_factory=list)
    failures: list[Failure] = field(default_factory=list)

    @property
    def folders(self) -> set[Path]:
        """Return the destination folders used by the plan."""
        return {move.target.parent for move in self.moves}


def is_hidden(path: Path) -> bool:
    """Return whether the file is hidden (its name starts with '.')."""
    return path.name.startswith(".")


def is_large(path: Path, threshold_mb: float) -> bool:
    """Return whether the file size reaches threshold_mb."""
    # Decimal MB (1000, not 1024), like Finder and Explorer display sizes
    filesize_mb = path.stat().st_size / 1000 / 1000

    return filesize_mb >= threshold_mb


def get_file_mimetype_and_group(m: Magika, file: Path) -> tuple[str, str]:
    """Return the MIME type and content group detected by Magika."""
    # The magic happens here !
    res = m.identify_path(file)

    # Magika reports read errors in the result instead of raising
    if not res.ok:
        msg = f"Magika could not read the file ({res.status})"
        raise ClassificationError(msg)

    return (res.output.mime_type, res.output.group)


def determine_target_directory(
    file: Path, magika: Magika, config: Config, *, lowercase: bool
) -> tuple[str, str]:
    """Return the target directory and the rule that selected it."""
    extension = file.suffix.lower()

    if is_hidden(file):
        return config.hidden, "hidden file"
    threshold_mb = config.large_files.threshold_mb
    if is_large(file, threshold_mb):
        return config.large_files.target_dir, f"larger than {threshold_mb} MB"
    if extension in config.extensions:
        return config.extensions[extension], f"extension {extension}"

    mimetype, group = get_file_mimetype_and_group(magika, file)
    if mimetype in config.mimetypes:
        return config.mimetypes[mimetype], f"mimetype {mimetype}"

    target_dir = group if lowercase else group.capitalize()
    return target_dir, f"magika group {group} ({mimetype})"


def unique_path(path: Path, reserved: set[Path]) -> Path:
    """Return a free target: "photo.jpg", then "photo (1).jpg", "photo (2).jpg"...

    A target is taken if it exists on disk or was already given to another
    file of the plan.
    """
    candidate = path
    counter = 1
    while candidate.exists() or candidate in reserved:
        candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
        counter += 1
    return candidate


def describe_error(e: Exception) -> str:
    """Return a short reason, e.g. "Permission denied".

    OSError messages otherwise look like "[Errno 13] Permission denied: '/path'".
    """
    if isinstance(e, OSError) and e.strerror:
        return e.strerror
    return str(e)


def plan_moves(
    directory: Path, magika: Magika, config: Config, *, lowercase: bool = False
) -> Plan:
    """Decide where every file goes. Nothing is moved or created."""
    plan = Plan(directory)
    reserved: set[Path] = set()

    for file in sorted(directory.iterdir()):
        if not file.is_file():
            continue

        try:
            target_dir, rule = determine_target_directory(
                file, magika, config, lowercase=lowercase
            )
        except (OSError, ClassificationError) as e:
            plan.failures.append(Failure(file, describe_error(e)))
            continue

        target = unique_path(directory / target_dir / file.name, reserved)
        reserved.add(target)
        plan.moves.append(Move(file, target, rule))

    return plan


def display_target(move: Move, directory: Path) -> str:
    """Return "Photos/" when the name is kept, "Photos/photo (1).jpg" if renamed."""
    relative = move.target.relative_to(directory)
    if move.target.name == move.source.name:
        return f"{relative.parent}/"
    return str(relative)


def log_plan(plan: Plan) -> None:
    """Log every planned move, then every file skipped while planning."""
    for move in plan.moves:
        logger.debug("'%s': rule %s", move.source.name, move.rule)
        logger.info("'%s' → %s", move.source.name, display_target(move, plan.directory))
    for failure in plan.failures:
        logger.warning("Skipped '%s': %s", failure.source.name, failure.reason)


def apply_move(move: Move) -> None:
    """Move one file to its planned target, creating its folder if needed."""
    move.target.parent.mkdir(parents=True, exist_ok=True)

    # The plan promised this exact target: never rename it again behind the
    # user's back if something appeared there since planning
    if move.target.exists():
        raise FileExistsError(
            errno.EEXIST, "Target appeared since planning", str(move.target)
        )

    shutil.move(move.source, move.target)


def try_move(move: Move) -> Failure | None:
    """Apply a move, returning a Failure instead of raising."""
    try:
        apply_move(move)
    except OSError as e:
        return Failure(move.source, describe_error(e))
    return None


def execute(plan: Plan) -> list[Failure]:
    """Perform the planned moves. A failed move doesn't stop the others."""
    failures: list[Failure] = []

    for move in plan.moves:
        failure = try_move(move)
        if failure:
            failures.append(failure)
            logger.error("Failed to move '%s': %s", move.source.name, failure.reason)
        else:
            logger.debug(
                "Moved '%s' → %s",
                move.source.name,
                display_target(move, plan.directory),
            )

    return failures
