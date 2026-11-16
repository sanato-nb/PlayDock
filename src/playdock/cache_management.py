"""기존 cache_management import 경로 호환용. 실제 구현은 services/cache_service.py."""
from services.cache_service import (
    IMAGE_FILES, GAME_ID, CacheStats, CacheService, _safe_folder,
    image_files, image_stats, recycle_images,
)
