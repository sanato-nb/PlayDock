"""Metadata integration regression tests; never call external DLsite during CI."""
import io
import json
import sqlite3
import zipfile
from pathlib import Path
from urllib.request import Request

import pytest

from core import Library
from data_management import backup_data, restore_data, inspect_backup
from work_db import WorkDatabase, fetch_dlsite_work, _safe_dlsite_url


class FakeResponse(io.BytesIO):
    status = 200
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.close()


def mock_opener(request: Request, *, timeout: float):
    url = request.full_url
    if 'workno=RJ01234567' not in url:
        raise AssertionError('unexpected remote code')
    if 'ja_JP' in url:
        title = '見本ゲーム'
    elif 'ko_KR' in url:
        title = '예제 게임'
    else:
        title = 'Example Game'
    payload = [{'workno': 'RJ01234567', 'work_name': title,
                'maker_name': 'Example Circle', 'regist_date': '2024-09-03',
                'genres': [{'name': 'RPG'}, {'name': 'ADV'}],
                'image_main': {'url': '//img.dlsite.jp/modpub/images2/work/doujin/RJ01234567_img_main.jpg'},
                'image_samples': [{'url':'https://img.dlsite.jp/sample.jpg'}]}]
    return FakeResponse(json.dumps(payload, ensure_ascii=False).encode())


def test_fetch_only_exact_code_with_locales_and_images():
    record = fetch_dlsite_work('RJ01234567', opener=mock_opener)
    assert record['titles'] == {'ja': '見本ゲーム', 'ko': '예제 게임', 'en': 'Example Game'}
    assert record['maker'] == 'Example Circle'
    assert record['release_date'] == '2024-09-03'
    assert record['tags'] == ['RPG', 'ADV']
    assert len(record['images']) == 2
    assert record['images'][0]['url'].startswith('https://img.dlsite.jp/')
    assert 'RJ01234567' in record['page_url']


def test_reject_wrong_code_and_bad_urls():
    def mismatch(*args, **kwargs):
        return FakeResponse(b'[{' + b'"workno":"RJ01234568","work_name":"wrong"' + b'}]')
    with pytest.raises(LookupError):
        fetch_dlsite_work('RJ01234567', opener=mismatch, categories=('maniax',))
    assert _safe_dlsite_url('https://example.com/pic.jpg') == ''
    assert _safe_dlsite_url('http://www.dlsite.com/a') == ''
    assert _safe_dlsite_url('//img.dlsite.jp/image.jpg').startswith('https://')
    with pytest.raises(ValueError):
        fetch_dlsite_work('RJbad', opener=mismatch)


def _setup(tmp_path: Path):
    archive = tmp_path / 'game_archives'
    installed = tmp_path / 'game_installs'
    archive.mkdir()
    installed.mkdir()
    (archive / 'RJ01234567 [v1.0].zip').write_bytes(b'not a real archive but not modified')
    store = tmp_path / 'data'
    library = Library(store)
    library.settings['archives'] = str(archive)
    library.settings['library'] = str(installed)
    library.save_settings()
    return library, archive


def test_save_retrieve_sync_preserves_user_meta(tmp_path):
    lib, archive = _setup(tmp_path)
    game, = lib.scan()
    lib.update_meta(game, title='사용자 지정 이름', prefer_manual_title=True)
    db = WorkDatabase(lib.store)
    assert db.count_works() == 0
    db.sync_library(lib, lib.scan())
    with db.connect() as con:
        assert con.execute('SELECT product_code FROM library_links').fetchone()[0] == 'RJ01234567'
    record = fetch_dlsite_work('RJ01234567', opener=mock_opener)
    db.save_work(record)
    assert db.count_works() == 1
    assert db.get_work('RJ01234567')['titles']['ko'] == '예제 게임'
    assert lib.title(game) == '사용자 지정 이름 [RJ01234567]'
    assert (archive / 'RJ01234567 [v1.0].zip').read_bytes().startswith(b'not a real archive')
    assert not (lib.art_dir(game) / 'hero.png').exists()


def test_sqlite_backup_and_restore_does_not_touch_archives(tmp_path):
    lib, archive = _setup(tmp_path)
    db = WorkDatabase(lib.store)
    db.save_work(fetch_dlsite_work('RJ01234567', opener=mock_opener))
    before = (archive / 'RJ01234567 [v1.0].zip').read_bytes()
    destination = tmp_path / 'backup.zip'
    backup_data(lib.store, lib.scan(), destination)
    assert 'playdock.db' in inspect_backup(destination)
    with zipfile.ZipFile(destination) as z:
        assert 'playdock.db' in z.namelist()
        assert not any('RJ01234567 [v1.0].zip' == n for n in z.namelist())
    with db.connect() as con:
        con.execute('DELETE FROM works')
    assert db.count_works() == 0
    restore_data(lib.store, destination)
    assert db.count_works() == 1
    assert (archive / 'RJ01234567 [v1.0].zip').read_bytes() == before


def test_reject_corrupt_database_restore_without_modifying_data(tmp_path):
    lib, _ = _setup(tmp_path)
    db = WorkDatabase(lib.store)
    broken = tmp_path / 'corrupt.zip'
    with zipfile.ZipFile(broken, 'w') as z:
        z.writestr('manifest.json', json.dumps({'format':'PlayDockDataBackup', 'version':1, 'files':['playdock.db']}))
        z.writestr('playdock.db', b'not a sqlite database')
    with pytest.raises(ValueError):
        restore_data(lib.store, broken)
    assert db.count_works() == 0


def test_no_user_database_in_public_distribution(tmp_path):
    from make_public_release import build_public_release, EXECUTABLES, MANUAL_FILENAME
    dist = tmp_path / 'dist'
    dist.mkdir()
    for exe in EXECUTABLES:
        (dist / exe).write_bytes(b'MZ' + b'\0' * 110000)
    (dist / 'data').mkdir()
    (dist / 'data' / 'playdock.db').write_bytes(b'USER_PRIVATE_DB')
    manual = tmp_path / MANUAL_FILENAME
    manual.write_bytes(b'%PDF-1.4\n%%EOF')
    release = build_public_release(dist, tmp_path / 'out', manual)
    with zipfile.ZipFile(release['zip']) as z:
        assert 'data/playdock.db' not in z.namelist()
        assert 'data/' in z.namelist()


def test_sqlite_connection_closes_after_context_on_windows(tmp_path):
    """A context exit must unlock the DB file before restoring/backing up."""
    lib, _ = _setup(tmp_path)
    db = WorkDatabase(lib.store)
    with db.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM works').fetchone()[0] == 0
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        con.execute('SELECT 1')
