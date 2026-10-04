"""Tests for the classification rules: which folder each file goes to."""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from mimedy.config import Config, LargeFilesConfig
from mimedy.errors import ClassificationError
from mimedy.organizer import determine_target_directory

# --- Fake Magika ----------------------------------------------------------------
# The real model is slow to load and its answers depend on its version: the
# rules are tested against a fake that returns exactly what each test asks for.


@dataclass(frozen=True)
class FakeOutput:
    mime_type: str
    group: str


@dataclass(frozen=True)
class FakeResult:
    ok: bool
    status: str
    output: FakeOutput


@dataclass
class FakeMagika:
    """Answer every identify_path() call with the same detection."""

    mime_type: str = "application/octet-stream"
    group: str = "unknown"
    ok: bool = True
    status: str = "ok"
    calls: list[Path] = field(default_factory=list)

    def identify_path(self, path: Path) -> FakeResult:
        self.calls.append(path)
        return FakeResult(self.ok, self.status, FakeOutput(self.mime_type, self.group))


# --- Fixtures -------------------------------------------------------------------


@pytest.fixture
def make_file(tmp_path: Path) -> Callable[..., Path]:
    """Return a function that creates a file of a given name and size."""

    def make(name: str, size: int = 10) -> Path:
        path = tmp_path / name
        path.write_bytes(b"x" * size)
        return path

    return make


# --- Hidden files ---------------------------------------------------------------


def test_hidden_file_goes_to_hidden_folder(make_file: Callable[..., Path]) -> None:
    file = make_file(".env")

    target, rule = determine_target_directory(
        file, FakeMagika(), Config(), lowercase=False
    )

    assert target == "Hidden"
    assert rule == "hidden file"


# --- Large files ----------------------------------------------------------------


def test_large_file_goes_to_large_folder(make_file: Callable[..., Path]) -> None:
    file = make_file("video.mp4", size=2000)

    threshold_mb = 0.001  # 1_000 bytes
    config = Config(large_files=LargeFilesConfig(threshold_mb=threshold_mb))

    target, rule = determine_target_directory(
        file, FakeMagika(), config, lowercase=False
    )

    assert target == "Large"  # default Large target
    assert rule == f"larger than {threshold_mb} MB"


def test_file_below_threshold_is_not_large(make_file: Callable[..., Path]) -> None:
    file = make_file("video.mp4", size=2000)

    threshold_mb = 0.005  # 5_000 bytes
    config = Config(large_files=LargeFilesConfig(threshold_mb=threshold_mb))

    target, _ = determine_target_directory(file, FakeMagika(), config, lowercase=False)

    assert target == "Unknown"


# --- Extensions -----------------------------------------------------------------


def test_extension_rule_skips_magika(make_file: Callable[..., Path]) -> None:
    file = make_file("data.csv")
    magika = FakeMagika()
    config = Config(extensions={".csv": "Data"})

    target, rule = determine_target_directory(file, magika, config, lowercase=False)

    assert target == "Data"
    assert rule == "extension .csv"
    assert magika.calls == []  # rules 1 to 3 never read the file content


def test_uppercase_extension_matches_the_rule(make_file: Callable[..., Path]) -> None:
    file = make_file("PHOTO.JPG")
    config = Config(extensions={".jpg": "Photos"})

    target, _ = determine_target_directory(file, FakeMagika(), config, lowercase=False)

    assert target == "Photos"


# --- MIME types -----------------------------------------------------------------


def test_detected_mimetype_goes_to_its_folder(make_file: Callable[..., Path]) -> None:
    file = make_file("document")
    magika = FakeMagika(mime_type="application/pdf", group="document")
    config = Config(mimetypes={"application/pdf": "PDF"})

    target, rule = determine_target_directory(file, magika, config, lowercase=False)

    assert target == "PDF"
    assert rule == "mimetype application/pdf"
    assert magika.calls == [file]


# --- Magika group fallback ------------------------------------------------------


def test_magika_group_is_capitalized(make_file: Callable[..., Path]) -> None:
    file = make_file("video.mp4")
    magika = FakeMagika(mime_type="video/mp4", group="video")

    target, rule = determine_target_directory(file, magika, Config(), lowercase=False)

    assert target == "Video"
    assert rule == "magika group video (video/mp4)"


def test_lowercase_option_keeps_group_lowercase(make_file: Callable[..., Path]) -> None:
    file = make_file("video.mp4")
    magika = FakeMagika(mime_type="video/mp4", group="video")

    target, _ = determine_target_directory(file, magika, Config(), lowercase=True)

    assert target == "video"


# --- Rule priority --------------------------------------------------------------


def test_hidden_beats_extension(make_file: Callable[..., Path]) -> None:
    file = make_file(".hidden.csv")
    config = Config(extensions={".csv": "Data"})

    target, rule = determine_target_directory(
        file, FakeMagika(), config, lowercase=False
    )

    assert target == "Hidden"
    assert rule == "hidden file"


def test_large_beats_extension(make_file: Callable[..., Path]) -> None:
    file = make_file("video.mp4", size=2000)

    threshold_mb = 0.001  # 1_000 bytes
    config = Config(
        large_files=LargeFilesConfig(threshold_mb=threshold_mb),
        extensions={".mp4": "Video"},
    )

    target, rule = determine_target_directory(
        file, FakeMagika(), config, lowercase=False
    )

    assert target == "Large"  # default Large target
    assert rule == f"larger than {threshold_mb} MB"


def test_extension_beats_mimetype(make_file: Callable[..., Path]) -> None:
    file = make_file("video.mp4")
    magika = FakeMagika(mime_type="video/mp4")
    config = Config(extensions={".mp4": "MP4"}, mimetypes={"video/mp4": "Video"})

    target, _ = determine_target_directory(file, magika, config, lowercase=False)

    assert target == "MP4"


# --- Errors ---------------------------------------------------------------------


def test_unreadable_file_raises_classification_error(
    make_file: Callable[..., Path],
) -> None:
    file = make_file("file")
    status = "permission_error"
    magika = FakeMagika(ok=False, status=status)

    with pytest.raises(
        ClassificationError,
        match=re.escape(f"Magika could not read the file ({status})"),
    ):
        determine_target_directory(file, magika, Config(), lowercase=False)
