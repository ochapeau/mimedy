"""Test doubles shared by the test files."""

from dataclasses import dataclass, field
from pathlib import Path

# The real Magika model is slow to load and its answers depend on its version:
# the code is tested against a fake that returns exactly what each test asks for.


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
    """Answer every identify_path() call with the same detection.

    Files named in unreadable fail instead, as the real Magika reports a file
    it cannot read: ok=False and the status "permission_error".
    """

    mime_type: str = "application/octet-stream"
    group: str = "unknown"
    ok: bool = True
    status: str = "ok"
    unreadable: set[str] = field(default_factory=set)
    calls: list[Path] = field(default_factory=list)

    def identify_path(self, path: Path) -> FakeResult:
        self.calls.append(path)
        if path.name in self.unreadable:
            output = FakeOutput(self.mime_type, self.group)
            return FakeResult(ok=False, status="permission_error", output=output)
        return FakeResult(self.ok, self.status, FakeOutput(self.mime_type, self.group))
