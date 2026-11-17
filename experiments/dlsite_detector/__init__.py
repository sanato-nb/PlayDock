"""DLsite 등록·게임 형식 확인 기능의 독립 실험 패키지."""
from .detector import (
    Detection, Product, LookupUnavailable, detect_dlsite_game,
    fetch_product, parse_product, extract_code, normalized_title,
    product_page_candidate,
)

__all__ = [
    "Detection", "Product", "LookupUnavailable", "detect_dlsite_game",
    "fetch_product", "parse_product", "extract_code", "normalized_title",
    "product_page_candidate",
]

from .pipeline import SearchDecision, WebEvidence, classify_game, examine_web_results
from .review_store import ReviewStore
from .enhanced_search import enhanced_classify_game
from .identity_hints import extract_hints, ArchiveHints
from .steam_client import SteamProduct, fetch_steam_product

__all__ += ["SearchDecision", "WebEvidence", "classify_game", "examine_web_results", "ReviewStore", "enhanced_classify_game", "extract_hints", "ArchiveHints",
            "SteamProduct", "fetch_steam_product"]
