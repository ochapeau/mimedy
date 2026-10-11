"""Undo the last run in a folder, from its journal.

The undo reuses the plan and execute steps of a normal run, the other way
round: plan_undo() builds a Plan whose moves go back to where the files were,
execute() performs it, then remove_created_folders() removes the folders
mimedy created, and update_journal() keeps only what is left to undo.

This module knows both the journal and the organizer, so that these two
never need to know each other.
"""

import logging
from pathlib import Path

from mimedy.journal import Journal, JournalWriter
from mimedy.organizer import Failure, Move, Plan, is_system_file, printable

logger = logging.getLogger("mimedy.undo")

UNDO_RULE = "undo"


def plan_undo(journal: Journal) -> Plan:
    """Plan the moves back to where the files were. Nothing is moved.

    The moves of the journal are reversed, newest first: each file goes
    from where mimedy put it back to its original place, under its original
    name ("report (1).pdf" becomes "report.pdf" again). Refuse rather than
    guess: a file no longer where mimedy put it, or whose original place is
    taken, is a failure. Nothing is ever overwritten or renamed.
    """
    plan = Plan(journal.directory)
    # reversed() walks the list backwards without changing it: update_journal()
    # needs the journal in its original order afterwards
    for done in reversed(journal.moves):
        # A failure names where the file is now: the file the user would look
        # for, and the key update_journal() uses to keep this move
        if not done.target.exists():
            plan.failures.append(Failure(source=done.target, reason="no longer there"))
            continue
        if done.source.exists():
            reason = "its original place is taken"
            plan.failures.append(Failure(source=done.target, reason=reason))
            continue
        plan.moves.append(Move(source=done.target, target=done.source, rule=UNDO_RULE))
    return plan


def only_system_files(folder: Path) -> bool:
    """Return whether folder holds nothing but system files (.DS_Store...).

    Opening a folder in the Finder writes a .DS_Store in it: such a folder
    still counts as empty, or the cleanup would almost never work on macOS.
    An empty folder holds only system files too: none at all.
    """
    for entry in folder.iterdir():
        if not entry.is_file() or not is_system_file(entry.name.lower()):
            return False
    return True


def remove_created_folders(journal: Journal) -> list[Path]:
    """Remove the folders mimedy created, when empty. Return the removed ones.

    Only folders of the journal are considered: a folder that existed before
    the run is never touched. The deepest come first (Code/Python before
    Code). A folder that still holds a file of the user is kept, and a
    folder already gone is skipped.
    """
    removed: list[Path] = []
    # Recorded top first, so reversed: Code/Python is removed before Code
    for folder in reversed(journal.created_dirs):
        # Already gone, or holding a file of the user: leave it
        if not folder.exists() or not only_system_files(folder):
            continue
        for system_file in folder.iterdir():  # .DS_Store and the like only
            system_file.unlink()
        folder.rmdir()
        removed.append(folder)
    return removed


def update_journal(
    path: Path, journal: Journal, failures: list[Failure], removed: list[Path]
) -> None:
    """Delete the journal after a complete undo, or rewrite it with what is left.

    failures are those of the planning and of the execution of the undo:
    their source is where the file is now, the target of its journal move.
    What is left: the moves that failed while their file is still where
    mimedy put it (its original place was taken, say), and the created
    folders that still exist. A second --undo then only tries those again.
    A file deleted since the run is forgotten: it could never go back.
    """
    failure_sources = {failure.source for failure in failures}
    # Keep a failed move only if the file is still where mimedy put it: a file
    # deleted since the run can never go back, retrying it would fail forever
    left_moves = [
        move
        for move in journal.moves
        if move.target in failure_sources and move.target.exists()
    ]
    left_dirs = [
        folder
        for folder in journal.created_dirs
        if folder.exists() and folder not in removed
    ]
    if not left_moves and not left_dirs:
        path.unlink()  # fully undone: a second --undo finds nothing to undo
        return

    # Rewritten in the order of a run: folders first, then the moves
    with JournalWriter(path, journal.directory) as writer:
        for folder in left_dirs:
            writer.record_created_dir(folder)
        for move in left_moves:
            writer.record_move(move.source, move.target)


def _shown(path: Path, directory: Path) -> str:
    """Return path relative to the organized folder, safe to print."""
    return printable(str(path.relative_to(directory)))


def log_undo_plan(plan: Plan) -> None:
    """Log every move back ("'PDF/invoice' → invoice"), then every failure."""
    for move in plan.moves:
        logger.info(
            "'%s' → %s",
            _shown(move.source, plan.directory),
            _shown(move.target, plan.directory),
        )
    for failure in plan.failures:
        name = _shown(failure.source, plan.directory)
        logger.warning("Skipped '%s': %s", name, failure.reason)
