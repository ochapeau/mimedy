"""Plan where each file goes, then move the files."""

import errno
import logging
import shutil
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path, PurePath

from magika import Magika

from mimedy.config import Config
from mimedy.errors import ClassificationError

logger = logging.getLogger("mimedy.organizer")

# Files the operating system or the file manager keeps in folders: moving them
# is useless (they are recreated) or breaks what they describe. Lowercase,
# because Windows and default macOS volumes ignore case.
SYSTEM_FILES = frozenset(
    {
        # macOS
        ".ds_store",  # Finder view settings
        ".localized",  # translated folder name
        "icon\r",  # custom folder icon (the name really ends with a carriage return)
        ".volumeicon.icns",  # custom drive icon
        ".com.apple.timemachine.donotpresent",  # Time Machine marker
        ".apdisk",  # network share info
        # Windows
        "thumbs.db",  # thumbnail cache
        "ehthumbs.db",  # Media Center thumbnail cache
        "ehthumbs_vista.db",
        "desktop.ini",  # folder appearance
        # Linux
        ".directory",  # KDE Dolphin folder settings
        ".hidden",  # files hidden by GNOME Files
    }
)

# macOS writes "._photo.jpg" next to "photo.jpg" on USB drives and network
# shares, to keep its metadata: it only makes sense next to its file
APPLEDOUBLE_PREFIX = "._"


@dataclass(frozen=True)
class Move:
    """A planned move of one file."""

    source: Path
    target: Path
    rule: str


@dataclass(frozen=True)
class Ignored:
    """A file left in place on purpose (not a failure)."""

    source: Path
    reason: str


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
    ignored: list[Ignored] = field(default_factory=list)
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


def blocking_file(directory: Path, target_dir: str) -> Path | None:
    """Return what blocks the target folder, or None if the way is free.

    Every level of target_dir is checked, from the top: with "Code/Python",
    a file named "Code" blocks as much as a file "Code/Python". A level
    blocks when it exists but is not a folder (a file, a link to a file...).
    On a case-insensitive disk, as on macOS by default, a file "data" also
    blocks "Data": the disk itself answers that "Data" exists.
    """
    current = directory
    for part in PurePath(target_dir).parts:
        current = current / part
        if current.exists() and not current.is_dir():
            return current
    return None


def is_system_file(name: str) -> bool:
    """Return whether a lowercased file name belongs to the system."""
    return name in SYSTEM_FILES or name.startswith(APPLEDOUBLE_PREFIX)


def ignore_reason(file: Path, config: Config) -> str | None:
    """Return why the file must not be moved, or None to plan it."""
    name = file.name.lower()
    if config.ignore_system_files and is_system_file(name):
        return "system file"
    for pattern in config.ignore:
        if fnmatchcase(name, pattern):
            return f"pattern {pattern}"
    return None


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
    """Decide where every file goes. Nothing is moved or created.

    Ignored files are checked first: .DS_Store is hidden, and would
    otherwise go to the hidden folder. A file whose target folder is blocked
    by a file of the same name is a failure, not a move that would fail.
    """
    plan = Plan(directory)
    reserved: set[Path] = set()

    for file in sorted(directory.iterdir()):
        if not file.is_file():
            continue

        reason = ignore_reason(file, config)
        if reason is not None:
            plan.ignored.append(Ignored(file, reason))
            continue

        try:
            target_dir, rule = determine_target_directory(
                file, magika, config, lowercase=lowercase
            )
        except (OSError, ClassificationError) as e:
            plan.failures.append(Failure(file, describe_error(e)))
            continue

        # A file named like the target folder would make the move fail at
        # execution: report it now, so that the plan shows what will happen.
        # Refused even if that file goes elsewhere: never rely on the order
        blocker = blocking_file(directory, target_dir)
        if blocker is not None:
            name = blocker.relative_to(directory)
            reason = f"the folder name '{name}' is taken by a file: rename it"
            plan.failures.append(Failure(source=file, reason=reason))
            continue

        # Pick a free name in the target folder ("photo (1).jpg" when the name
        # is taken on disk or by an earlier file of this plan), and reserve it
        # for this file, so that no later file of the plan gets it too
        target = unique_path(directory / target_dir / file.name, reserved)
        reserved.add(target)
        plan.moves.append(Move(file, target, rule))

    return plan


def printable(text: str) -> str:
    """Escape control characters: "Icon\r" becomes "Icon\\r".

    Printed as is, a carriage return sends the cursor back to the start of
    the line, and the rest of the message overwrites it.
    """
    # repr("\r") is "'\\r'": keep it without its quotes
    return "".join(c if c.isprintable() else repr(c)[1:-1] for c in text)


def display_target(move: Move, directory: Path) -> str:
    """Return "Photos/" when the name is kept, "Photos/photo (1).jpg" if renamed."""
    relative = move.target.relative_to(directory)
    if move.target.name == move.source.name:
        return printable(f"{relative.parent}/")
    return printable(str(relative))


def log_plan(plan: Plan) -> None:
    """Log the moves, the ignored files (verbose only), then the failures."""
    for move in plan.moves:
        name = printable(move.source.name)
        logger.debug("'%s': rule %s", name, move.rule)
        logger.info("'%s' → %s", name, display_target(move, plan.directory))
    for ignored in plan.ignored:
        name = printable(ignored.source.name)
        logger.debug("Ignored '%s': %s", name, ignored.reason)
    for failure in plan.failures:
        name = printable(failure.source.name)
        logger.warning("Skipped '%s': %s", name, failure.reason)


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
        name = printable(move.source.name)
        if failure:
            failures.append(failure)
            logger.error("Failed to move '%s': %s", name, failure.reason)
        else:
            logger.debug("Moved '%s' → %s", name, display_target(move, plan.directory))

    return failures
