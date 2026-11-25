"""Single-result EXE ranking must match the full sorted list."""
from pathlib import Path

import pytest

from core import Game, Library
from services import launch_service


@pytest.mark.parametrize("title", ["", "Other Game", "Example"])
def test_best_executable_matches_full_ranking(tmp_path, title):
    for name in ("Example.exe", "OtherGame.exe", "game.exe", "setup.exe",
                 "bin/Example-Win64-Shipping.exe", "backup/Example.exe",
                 "redist/game.exe"):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"MZ fixture")
    ordered = launch_service.executable_candidates(tmp_path, title)
    assert ordered
    assert launch_service.best_executable_candidate(tmp_path, title) == ordered[0]
    assert all(p.name != "setup.exe" and p.parent.name not in {"backup", "redist"}
               for p in ordered)


def test_chosen_executable_reuses_current_candidate_list(tmp_path, monkeypatch):
    folder = tmp_path / "game"
    folder.mkdir()
    first = folder / "first.exe"
    selected = folder / "selected.exe"
    first.write_bytes(b"MZ fixture")
    selected.write_bytes(b"MZ fixture")
    library = Library(tmp_path / "data")
    game = Game("example", "Example", tmp_path, folder=folder)

    def unexpected(*args, **kwargs):
        pytest.fail("Current ranked candidate list must not trigger another scan")

    monkeypatch.setattr(launch_service, "best_executable_candidate", unexpected)
    assert launch_service.chosen_executable(library, game, meta={}, candidates=[first]) == first
    assert launch_service.chosen_executable(library, game, meta={"executable": selected.name},
                                            candidates=[first]) == selected.resolve()
    assert launch_service.chosen_executable(library, game, meta={}, candidates=[]) is None
    assert launch_service.chosen_executable(library, game, meta={"executable": "missing.exe"},
                                            candidates=[first]) == first


def test_single_result_empty_folder(tmp_path):
    assert launch_service.best_executable_candidate(tmp_path) is None
