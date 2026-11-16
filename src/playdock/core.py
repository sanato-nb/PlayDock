"""Stable compatibility API for PlayDock's local game library.

Implementations live in models/ and services/. Existing callers can keep
``from core import ...`` while responsibilities are separated incrementally.
"""
from models.game import Game, game_key, safe_folder_name
from services.library_service import (
    Library, data_dir, default_library, load_json, save_json,
)
from services.archive_service import (
    ARCHIVE_EXT, BLOCK_SIZE, MAX_FILES, MAX_EXTRACTED_BYTES,
    ArchivePasswordRequired, ArchivePasswordInvalid, archive_requires_password,
    validate_archive_member, _check_target, _unpack_zip, _unpack_7z, _unpack_rar,
)
from services.launch_service import BAD_EXE_WORDS, executable_candidates, chosen_executable
from services.install_service import install, uninstall_target, uninstall_to_recycle_bin

APP_NAME = "PlayDock"
