from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile
import pytest

from make_public_release import (EXECUTABLES, INSTALL_MARKER, REQUIRED_ZIP,
                                 build_public_release, MANUAL_FILENAME)


def fake_dist(tmp_path: Path):
    dist = tmp_path / 'dist'
    dist.mkdir()
    for name in EXECUTABLES:
        (dist / name).write_bytes(b'MZ' + b'\0' * 100001)
    manual = tmp_path / MANUAL_FILENAME
    manual.write_bytes(b'%PDF-1.4\n%%EOF')
    return dist, manual


def test_release_never_copies_installed_user_data_or_install_json(tmp_path):
    dist, manual = fake_dist(tmp_path)
    # These must remain completely excluded, even if somebody accidentally
    # puts installed application data in their build/dist folder.
    (dist / 'data' / 'cache').mkdir(parents=True)
    (dist / 'data' / 'settings.json').write_text('{"api_key": "PRIVATE_CANARY"}')
    (dist / 'data' / 'collections.json').write_text('PRIVATE_CANARY')
    (dist / 'data' / 'cache' / 'meta.json').write_text('PRIVATE_CANARY')
    (dist / 'PlayDock.install.json').write_text('{"api_key":"PRIVATE_CANARY"}')
    (dist / 'README_PRIVATE.txt').write_text('PRIVATE_CANARY')
    (dist / '.env').write_text('PRIVATE_CANARY')
    result = build_public_release(dist, tmp_path / 'out', manual)
    with ZipFile(result['zip']) as zf:
        assert set(zf.namelist()) == REQUIRED_ZIP
        assert zf.read('data/') == b''
        assert b'PRIVATE_CANARY' not in b''.join(zf.read(name) for name in zf.namelist())
        assert json.loads(zf.read(INSTALL_MARKER)) == {
            'id': 'playdock-installed-v1', 'data_directory': 'data', 'version': '0.8.2'}
    assert result['setup'].read_bytes() == (dist / 'PlayDock_Setup.exe').read_bytes()


def test_rejects_missing_and_non_exe(tmp_path):
    dist, manual = fake_dist(tmp_path)
    (dist / 'PlayDock.exe').write_bytes(b'PK' + b'0' * 200000)
    with pytest.raises(ValueError, match='Windows EXE'):
        build_public_release(dist, tmp_path / 'out', manual)
    (dist / 'PlayDock.exe').unlink()
    with pytest.raises(FileNotFoundError):
        build_public_release(dist, tmp_path / 'out', manual)


def test_source_literal_credential_scan(tmp_path):
    dist, manual = fake_dist(tmp_path)
    src = tmp_path / 'source'
    src.mkdir()
    (src / 'app.py').write_text('KEY = "AIza' + 'A'*36 + '"', encoding='utf-8')
    with pytest.raises(ValueError, match='키처럼'):
        build_public_release(dist, tmp_path / 'out', manual, source=src)


def test_rejects_non_pdf_manual(tmp_path):
    dist, manual = fake_dist(tmp_path)
    manual.write_text('Not a real PDF')
    with pytest.raises(ValueError, match='PDF'):
        build_public_release(dist, tmp_path / 'out', manual)
