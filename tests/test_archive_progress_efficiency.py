"""Ordinary ZIP installation keeps layout and avoids repeated progress signals."""
import zipfile

import pytest

from core import Game, install
from services.archive_service import _progress_reporter


def test_progress_reporter_emits_only_changed_percentages():
    seen = []
    report = _progress_reporter(seen.append, 1000)
    for done in range(1, 1001):
        report(done)
    assert seen == list(range(100))


@pytest.mark.parametrize("nested", [False, True])
def test_many_small_members_keep_layout_and_coalesce_progress(tmp_path, nested):
    root = tmp_path / "installed"
    root.mkdir()
    archive = tmp_path / "Example.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for index in range(250):
            prefix = "Wrapper/" if nested else ""
            zf.writestr(prefix + f"data_{index:03}.txt", b"fixture")
    original = archive.read_bytes()
    game = Game("example", "Example", root, archive=archive)
    seen = []
    destination = install(game, seen.append)
    assert destination == root / "Example"
    assert len(list(destination.iterdir())) == 250
    assert (destination / "data_000.txt").read_bytes() == b"fixture"
    assert seen[-1] == 100
    assert seen == sorted(set(seen))
    assert len(seen) <= 101
    assert archive.read_bytes() == original
