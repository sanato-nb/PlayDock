"""기존 data_management import 경로 호환용. 실제 구현은 services/data_service.py."""
from services.data_service import (
    GAME_ID, FORMAT, LEGACY_FORMAT, VERSION, ROOT_FILES, CACHE_FILES,
    MAX_FILES, MAX_JSON, MAX_DB, MAX_IMAGE, MAX_TOTAL,
    DataInventory, _redirected, _cache_folders, _data_paths,
    _allowed, _validate_file, inventory, backup_data, inspect_backup,
    restore_data,
)
