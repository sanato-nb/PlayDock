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

__all__ += ["SearchDecision", "WebEvidence", "classify_game", "examine_web_results", "ReviewStore"]
