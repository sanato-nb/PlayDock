"""Tests proving the modules own real functionality rather than duplicate stubs."""
from pathlib import Path
import zipfile

import pytest

import core
import work_db
from models.game import Game
from services.library_service import Library
from services.archive_service import archive_requires_password, validate_archive_member
from services.launch_service import executable_candidates
from services.install_service import install, uninstall_target
from integrations.dlsite_client import fetch_dlsite_work
from database.work_repository import WorkDatabase


def test_core_facade_reuses_real_model_and_services():
    assert core.Game is Game
    assert core.Library is Library
    assert core.install is install
    assert core.uninstall_target is uninstall_target
    assert core.executable_candidates is executable_candidates
    assert core.archive_requires_password is archive_requires_password


def test_db_facade_reuses_repository_and_network_adapter():
    assert work_db.WorkDatabase is WorkDatabase
    assert work_db.fetch_dlsite_work is fetch_dlsite_work


def test_local_library_scans_and_installs_zip_without_changing_archive(tmp_path):
    store, archive_dir, install_dir = (tmp_path / name for name in ('data', 'zip', 'games'))
    archive_dir.mkdir()
    install_dir.mkdir()
    source = archive_dir / 'My Game.zip'
    with zipfile.ZipFile(source, 'w') as z:
        z.writestr('My Game/Game.exe', b'MZtest')
    library = Library(store)
    library.change_archive_root(archive_dir)
    library.change_root(install_dir)
    game = library.scan()[0]
    assert isinstance(game, Game)
    assert not archive_requires_password(source)
    target = install(game)
    assert (target / 'Game.exe').read_bytes() == b'MZtest'
    assert source.exists()
    assert executable_candidates(target)[0].name == 'Game.exe'


@pytest.mark.parametrize('bad', ['../outside', '/absolute', 'C:\\evil', 'x/../../y'])
def test_archive_validation_still_rejects_traversal(bad):
    with pytest.raises(ValueError):
        validate_archive_member(bad)


def test_db_repository_is_independent_of_live_dlsite(tmp_path):
    db = WorkDatabase(tmp_path / 'data')
    assert db.count_works() == 0
    assert db.get_work('RJ01234567') is None
