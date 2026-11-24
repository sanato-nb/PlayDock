"""Rebranding must not damage prior installation data, credentials or backups."""
from pathlib import Path
import json
import sys
import types
import zipfile

import pytest

from local_storage import (LEGACY_INSTALL_MARKER, LEGACY_MARKER_ID, INSTALL_MARKER,
                           marker_is_valid, data_dir_for_executable, write_install_marker)
import install_management as mgr
import ai_providers as ai
from data_management import backup_data, inspect_backup, restore_data
from core import Library
from save_backups import create_save_backup, restore_save_backup


def test_release_names_and_build_payload():
    root = Path(__file__).resolve().parents[1]
    for filename in ('Build-Windows-Release.ps1', 'build_setup_windows.bat', '00_BUILD_WINDOWS_EXE.bat'):
        source = (root/"scripts"/filename).read_text('utf-8-sig')
        for name in ('PlayDock.exe', 'PlayDock_TitleEditor.exe', 'PlayDock_Setup.exe', 'PlayDock_Uninstall.exe'):
            assert name in source
    assert mgr.DISPLAY_NAME == 'PlayDock'
    assert mgr.MAIN_EXE == 'PlayDock.exe'
    assert mgr.EDITOR_EXE == 'PlayDock_TitleEditor.exe'
    assert mgr.UNINSTALL_EXE == 'PlayDock_Uninstall.exe'
    assert mgr.VERSION == '0.8.0'
    assert (root / 'assets' / 'playdock.ico').is_file()


def test_old_install_marker_still_uses_original_data_folder(tmp_path):
    folder = tmp_path/'LocalGameShelf'
    folder.mkdir()
    old_marker = folder / LEGACY_INSTALL_MARKER
    old_marker.write_text(json.dumps({'id':LEGACY_MARKER_ID, 'data_directory':'data'}), encoding='utf-8')
    (folder/'data').mkdir()
    (folder/'data'/'collections.json').write_text('keep', encoding='utf-8')
    assert marker_is_valid(folder)
    assert data_dir_for_executable(folder/'PlayDock.exe',frozen=True) == folder/'data'
    write_install_marker(folder)
    assert (folder/INSTALL_MARKER).is_file()
    assert (folder/'data'/'collections.json').read_text('utf-8')=='keep'
    old_marker.unlink()
    assert marker_is_valid(folder)


def test_legacy_app_backup_can_still_be_restored(tmp_path):
    store=tmp_path/'data'; store.mkdir()
    (store/'collections.json').write_text('{"collections":[]}', encoding='utf-8')
    backup=tmp_path/'data.zip'
    backup_data(store, [], backup)
    rewrite=tmp_path/'old-format.zip'
    with zipfile.ZipFile(backup) as src, zipfile.ZipFile(rewrite,'w') as dst:
        for entry in src.infolist():
            b=src.read(entry.filename)
            if entry.filename == 'manifest.json':
                manifest=json.loads(b)
                manifest['format']='LocalGameShelfDataBackup'
                b=json.dumps(manifest).encode('utf-8')
            dst.writestr(entry, b)
    assert 'collections.json' in inspect_backup(rewrite)
    (store/'collections.json').write_text('{"collections":[{"name":"changed"}]}',encoding='utf-8')
    restored,safety=restore_data(store,rewrite)
    assert restored == 1
    assert json.loads((store/'collections.json').read_text('utf-8'))['collections']==[]
    assert safety.exists()


def test_legacy_save_backups_still_restore(tmp_path):
    saves=tmp_path/'saves';saves.mkdir();(saves/'slot1.dat').write_text('ok')
    output=tmp_path/'backups';output.mkdir()
    archive=create_save_backup(saves, output,'Test','abc')
    legacy=tmp_path/'old-save.zip'
    with zipfile.ZipFile(archive) as src, zipfile.ZipFile(legacy,'w') as dst:
        for entry in src.infolist():
            b=src.read(entry.filename)
            if entry.filename=='manifest.json':
                manifest=json.loads(b);manifest['format']='LocalGameShelfSaveBackup'
                b=json.dumps(manifest).encode('utf-8')
            dst.writestr(entry,b)
    restored=restore_save_backup(legacy, tmp_path)
    assert (restored/'slot1.dat').read_text()=='ok'


def test_api_credential_compatibility_and_deletion(monkeypatch):
    passwords={('LocalGameShelf','gemini'):'legacy-secret'}
    class Missing(Exception): pass
    fake=types.SimpleNamespace(
        errors=types.SimpleNamespace(PasswordDeleteError=Missing),
        get_password=lambda service,name: passwords.get((service,name)),
        set_password=lambda service,name,value: passwords.__setitem__((service,name),value),
        delete_password=lambda service,name: passwords.pop((service,name)) if (service,name) in passwords else (_ for _ in ()).throw(Missing()),
    )
    monkeypatch.setitem(sys.modules,'keyring',fake)
    monkeypatch.delenv('GEMINI_API_KEY',raising=False)
    assert ai.get_secret('gemini')=='legacy-secret'
    ai.set_secret('gemini','new-secret')
    assert passwords=={('PlayDock','gemini'):'new-secret'}
    assert ai.get_secret('gemini')=='new-secret'
    ai.set_secret('gemini','')
    assert ai.get_secret('gemini')==''
    assert passwords=={}


def test_built_release_has_no_personal_data():
    root=Path(__file__).resolve().parents[1]
    assert not (root/'data').exists()
    assert not (root/'dist').exists()
    assert not (root/'build').exists()
    assert not (root/'settings.json').exists()
    assert not (root/'collections.json').exists()
