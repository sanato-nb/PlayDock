"""게임 이미지 검색창에서 사용되는 업무 규칙과 저장을 담당한다.

Qt 위젯과 대화상자를 참조하지 않는다. 사용자 확인 여부는 호출하는 UI가 결정한다.
기존 게임 파일, 압축파일, 모음집을 변경하지 않는다.
"""
from __future__ import annotations

from datetime import datetime
import shutil

from game_identity import GameIdentity, initial_identity
from game_codes import normalize_code
from product_titles import extract_code
from online_artwork import save_selected_art


class ArtworkActions:
    def __init__(self, library, game):
        self.library = library
        self.game = game

    def initial_identity(self) -> GameIdentity:
        game = self.game
        library = self.library
        identity = initial_identity(
            library.base_title(game), game.name,
            game.archive.name if game.archive else "",
        )
        meta = library.meta(game)
        registered_code = library.product_code(game)
        if "product_code" in meta and not registered_code:
            return GameIdentity(identity.title, "작품 코드 없음 · 게임명으로 검색",
                                None, identity.confidence, False)
        if registered_code:
            identity = GameIdentity(identity.title, identity.source,
                                    registered_code, identity.confidence, False)
        saved_code = meta.get("artwork_identity_code", "")
        saved_title = meta.get("artwork_identity_title", "")
        if (registered_code and extract_code(saved_code) == registered_code
                and isinstance(saved_title, str) and saved_title.strip()):
            return GameIdentity(saved_title, "이전에 확인한 작품 정보 (게임 캐시)",
                                registered_code, 1.0, True)
        return identity

    def save_product_code(self, raw_code: str, query: str,
                          identity: GameIdentity) -> tuple[str, GameIdentity]:
        code = normalize_code(raw_code)
        self.library.set_product_code(self.game, code)
        if code:
            if identity.code != code:
                identity = GameIdentity(query.strip(), "직접 입력한 작품 코드 · 공식 작품 확인 전",
                                        code, 0.5, False)
        else:
            identity = GameIdentity(query.strip(), "품번 없는 게임 · 이름으로 검색",
                                    None, 0.5, False)
        return code, identity

    def record_verified_identity(self, identity: GameIdentity) -> bool:
        if not (identity.verified and identity.code):
            return False
        self.library.update_meta(
            self.game, artwork_identity_code=identity.code,
            artwork_identity_title=identity.title,
        )
        self.library.set_product_code(self.game, identity.code)
        return True

    @staticmethod
    def confirmed_search_code(identity: GameIdentity, query: str,
                              raw_code: str) -> str | None:
        if (identity.verified and identity.code and query.strip() == identity.title
                and raw_code.strip().upper() == identity.code):
            return identity.code
        return None

    def has_artwork(self, kind: str) -> bool:
        return (self.library.art_dir(self.game) / f"{kind}.png").exists()

    def apply_selection(self, image_data: bytes, candidate, kind: str,
                        x: int, y: int, zoom: int) -> None:
        """확인된 이미지만 기존 백업을 만든 뒤 저장하고 출처를 기록한다.

        교체 확인 대화상자는 UI에서 먼저 실행해야 한다.
        """
        target = self.library.art_dir(self.game) / f"{kind}.png"
        if target.exists():
            backup = self.library.store / "backups" / "artwork" / self.game.id
            backup.mkdir(parents=True, exist_ok=True)
            saved = backup / f'{kind}_{datetime.now().strftime("%Y%m%d_%H%M%S_%f")}.png'
            shutil.copy2(target, saved)
        save_selected_art(image_data, target, kind, x, y, zoom)
        metadata = self.library.meta(self.game)
        sources = metadata.get("artwork_sources")
        sources = dict(sources) if isinstance(sources, dict) else {}
        sources[kind] = {
            "url": candidate.image_url,
            "page": candidate.source_url,
            "source": candidate.provider,
            "license": candidate.license_label,
        }
        self.library.update_meta(
            self.game, artwork_source="인터넷 검색 · 사용자가 선택함",
            artwork_sources=sources,
        )
