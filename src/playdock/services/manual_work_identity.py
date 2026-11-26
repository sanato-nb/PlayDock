"""User-selected work identity; no title, artwork or game-file writes."""
from database.official_catalog import DL_CODE, STEAM_ID
from services.official_work_service import explicit_work_identity


def normalize_manual_identity(store, code):
    code = str(code or "").strip()
    if store == "none":
        return "", ""
    if store == "dlsite" and DL_CODE.fullmatch(code.upper()):
        return store, code.upper()
    if store == "steam" and STEAM_ID.fullmatch(code):
        return store, code
    raise ValueError("DLsite는 RJ/VJ/BJ/EJ + 숫자 6~8자리, Steam은 숫자 App ID를 입력하세요.")


def current_work_choice(library, game, db):
    meta = library.meta(game)
    if "product_code" in meta and not meta.get("product_code"):
        return "none", ""
    identity = explicit_work_identity(library, game, meta=meta)
    linked = db.get_linked_official_work(game.id)
    if linked and not meta.get("manual_work_identity"):
        return linked["store"], str(linked["code"])
    return identity or ("none", "")


def save_manual_work_identity(library, game, db, store, code):
    store, code = normalize_manual_identity(store, code)
    meta = library.meta(game)
    if (meta.get("manual_work_identity") and meta.get("product_store") == store
            and meta.get("product_code") == code):
        return False
    # Delete association before changing local metadata; never delete the
    # shared official work. A failed metadata write leaves no stale link.
    db.clear_game_link(game.id)
    library.update_meta(game, product_store=store, product_code=code,
                        steam_app_id=code if store == "steam" else "",
                        manual_work_identity=True)
    return True
