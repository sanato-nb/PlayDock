"""Regression coverage for protected ZIPs, including WinZip AES method 99."""
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import (Library, install, archive_requires_password,
                  ArchivePasswordRequired, ArchivePasswordInvalid)


def make_library(tmp_path):
    root = tmp_path / 'install'
    source = tmp_path / 'archives'
    root.mkdir()
    source.mkdir()
    lib = Library(tmp_path / 'settings')
    lib.change_root(root)
    lib.change_archive_root(source)
    return lib, root, source


def test_unencrypted_zip_still_works(tmp_path):
    lib, root, source = make_library(tmp_path)
    with zipfile.ZipFile(source / 'Plain.zip', 'w') as zf:
        zf.writestr('Game.exe', b'MZ')
    assert not archive_requires_password(source / 'Plain.zip')
    installed = install(lib.scan()[0])
    assert (installed / 'Game.exe').read_bytes() == b'MZ'


def test_zipcrypto_requires_password_and_extracts(tmp_path):
    if shutil.which('zip') is None:
        pytest.skip('zip CLI is not available for creating a ZipCrypto test file')
    lib, root, source = make_library(tmp_path)
    folder = tmp_path / 'original'
    folder.mkdir()
    (folder / 'Game.exe').write_bytes(b'MZtest')
    subprocess.run(['zip', '-q', '-j', '-P', 'my-test-secret', str(source / 'Secret.zip'),
                    str(folder / 'Game.exe')], check=True)
    archive = source / 'Secret.zip'
    assert archive_requires_password(archive)
    game = lib.scan()[0]
    with pytest.raises(ArchivePasswordRequired):
        install(game)
    assert not (root / 'Secret').exists()
    with pytest.raises(ArchivePasswordInvalid):
        install(game, password='wrong-password')
    assert not (root / 'Secret').exists()
    assert not list(root.glob('.localgameshelf-staging-*'))
    result = install(game, password='my-test-secret')
    assert (result / 'Game.exe').read_bytes() == b'MZtest'
    assert archive.is_file()


def test_aes_zip_password_roundtrip(tmp_path):
    pyzipper = pytest.importorskip('pyzipper')
    lib, root, source = make_library(tmp_path)
    archive = source / 'AES Game.zip'
    with pyzipper.AESZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED,
                             encryption=pyzipper.WZ_AES) as zf:
        zf.setpassword(b'test-pass-123')
        zf.setencryption(pyzipper.WZ_AES, nbits=256)
        zf.writestr('AES Game/Game.exe', b'MZtest')
    with zipfile.ZipFile(archive) as zf:
        assert zf.infolist()[0].compress_type == 99
    assert archive_requires_password(archive)
    game = lib.scan()[0]
    with pytest.raises(ArchivePasswordRequired):
        install(game)
    with pytest.raises(ArchivePasswordInvalid):
        install(game, password='bad-pass')
    assert not (root / 'AES Game').exists()
    result = install(game, password='test-pass-123')
    assert (result / 'Game.exe').read_bytes() == b'MZtest'
    assert archive.exists()
