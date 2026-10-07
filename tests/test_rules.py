"""Tests for the classification rules: which folder each file goes to."""

import re
from collections.abc import Callable
from pathlib import Path

import pytest

from mimedy.config import Config, LargeFilesConfig
from mimedy.errors import ClassificationError
from mimedy.organizer import determine_target_directory
from tests.fakes import FakeMagika

# --- Hidden files ---------------------------------------------------------------


def test_hidden_file_goes_to_hidden_folder(make_file: Callable[..., Path]) -> None:
    # Rule 1: a name starting with '.' goes to the hidden folder
    file = make_file(".env")

    target, rule = determine_target_directory(
        file, FakeMagika(), Config(), lowercase=False
    )

    assert target == "Hidden"
    assert rule == "hidden file"


# --- Large files ----------------------------------------------------------------


def test_large_file_goes_to_large_folder(make_file: Callable[..., Path]) -> None:
    # Rule 2: a file over the threshold goes to the large files folder
    file = make_file("video.mp4", size=2000)
    threshold_mb = 0.001  # 1_000 bytes
    config = Config(large_files=LargeFilesConfig(threshold_mb=threshold_mb))

    target, rule = determine_target_directory(
        file, FakeMagika(), config, lowercase=False
    )

    assert target == "Large"  # default target_dir
    assert rule == f"larger than {threshold_mb} MB"


def test_file_below_threshold_is_not_large(make_file: Callable[..., Path]) -> None:
    # Under the threshold, the next rules decide
    file = make_file("video.mp4", size=2000)
    threshold_mb = 0.005  # 5_000 bytes
    config = Config(large_files=LargeFilesConfig(threshold_mb=threshold_mb))

    target, _ = determine_target_directory(file, FakeMagika(), config, lowercase=False)

    assert target == "Unknown"  # FakeMagika's default group, capitalized


# --- Extensions -----------------------------------------------------------------


def test_extension_rule_skips_magika(make_file: Callable[..., Path]) -> None:
    # Rule 3: an extension rule decides without reading the content
    file = make_file("data.csv")
    magika = FakeMagika()
    config = Config(extensions={".csv": "Data"})

    target, rule = determine_target_directory(file, magika, config, lowercase=False)

    assert target == "Data"
    assert rule == "extension .csv"
    assert magika.calls == []  # rules 1 to 3 never read the file content


def test_uppercase_extension_matches_the_rule(make_file: Callable[..., Path]) -> None:
    # Extensions ignore case: PHOTO.JPG matches .jpg
    file = make_file("PHOTO.JPG")
    config = Config(extensions={".jpg": "Photos"})

    target, _ = determine_target_directory(file, FakeMagika(), config, lowercase=False)

    assert target == "Photos"


# --- MIME types -----------------------------------------------------------------


def test_detected_mimetype_goes_to_its_folder(make_file: Callable[..., Path]) -> None:
    # Rule 4: the MIME type detected by Magika picks the folder
    file = make_file("invoice")
    magika = FakeMagika(mime_type="application/pdf", group="document")
    config = Config(mimetypes={"application/pdf": "PDF"})

    target, rule = determine_target_directory(file, magika, config, lowercase=False)

    assert target == "PDF"
    assert rule == "mimetype application/pdf"
    assert magika.calls == [file]


# --- Magika group fallback ------------------------------------------------------


def test_magika_group_is_capitalized(make_file: Callable[..., Path]) -> None:
    # Rule 5, the fallback: the Magika group, capitalized as a folder name
    file = make_file("video.mp4")
    magika = FakeMagika(mime_type="video/mp4", group="video")

    target, rule = determine_target_directory(file, magika, Config(), lowercase=False)

    assert target == "Video"
    assert rule == "magika group video (video/mp4)"


def test_lowercase_option_keeps_group_lowercase(make_file: Callable[..., Path]) -> None:
    # --lowercase keeps the group name as Magika gives it
    file = make_file("video.mp4")
    magika = FakeMagika(mime_type="video/mp4", group="video")

    target, _ = determine_target_directory(file, magika, Config(), lowercase=True)

    assert target == "video"


# --- Rule priority --------------------------------------------------------------


def test_hidden_beats_extension(make_file: Callable[..., Path]) -> None:
    # Rule 1 before rule 3: a hidden .csv goes to Hidden/, not to Data/
    file = make_file(".hidden.csv")
    config = Config(extensions={".csv": "Data"})

    target, rule = determine_target_directory(
        file, FakeMagika(), config, lowercase=False
    )

    assert target == "Hidden"
    assert rule == "hidden file"


def test_large_beats_extension(make_file: Callable[..., Path]) -> None:
    # Rule 2 before rule 3: a large .mp4 goes to Large/
    file = make_file("video.mp4", size=2000)
    threshold_mb = 0.001  # 1_000 bytes
    config = Config(
        large_files=LargeFilesConfig(threshold_mb=threshold_mb),
        extensions={".mp4": "Video"},
    )

    target, rule = determine_target_directory(
        file, FakeMagika(), config, lowercase=False
    )

    assert target == "Large"  # default target_dir
    assert rule == f"larger than {threshold_mb} MB"


def test_extension_beats_mimetype(make_file: Callable[..., Path]) -> None:
    # Rule 3 before rule 4: the extension wins over the detected type
    file = make_file("video.mp4")
    magika = FakeMagika(mime_type="video/mp4")
    config = Config(extensions={".mp4": "MP4"}, mimetypes={"video/mp4": "Video"})

    target, _ = determine_target_directory(file, magika, config, lowercase=False)

    assert target == "MP4"


# --- Errors ---------------------------------------------------------------------


def test_unreadable_file_raises_classification_error(
    make_file: Callable[..., Path],
) -> None:
    # Magika reports read errors in its result: mimedy raises them as errors
    file = make_file("file")
    status = "permission_error"
    magika = FakeMagika(ok=False, status=status)

    with pytest.raises(
        ClassificationError,
        match=re.escape(f"Magika could not read the file ({status})"),
    ):
        determine_target_directory(file, magika, Config(), lowercase=False)
