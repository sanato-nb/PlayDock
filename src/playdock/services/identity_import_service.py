"""Read external AI identity suggestions as untrusted data; verify before writes."""
from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
import json
import re
from urllib.parse import urlsplit

from database.official_catalog import DL_CODE, STEAM_ID
from database.work_repository import WorkDatabase
from integrations.official_lookup.code_only import codes_in, steam_ids_in
from services.catalog_collection_service import CatalogCollector, CatalogEntry, CatalogEvent

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 1000


@dataclass(frozen=True)
class IdentitySuggestion:
    game: object
    filename: str
    store: str
    code: str
    title: str
    url: str
    status: str = "confirmed"
    reason: str = ""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON 키가 중복되었습니다.")
        result[key] = value
    return result


def _valid_url(store, code, url):
    try:
        p = urlsplit(url)
        if p.scheme != "https" or p.username or p.password or p.port not in (None, 443):
            return False
        if store == "dlsite":
            return p.hostname == "www.dlsite.com" and bool(re.fullmatch(
                r"/[^/]+/work/=/product_id/" + re.escape(code) + r"\.html/?", p.path, re.I))
        return p.hostname == "store.steampowered.com" and bool(re.fullmatch(
            r"/app/" + re.escape(code) + r"(?:/[^/]*)?/?", p.path))
    except ValueError:
        return False


def _available(library, db, game, filename):
    # Do not overwrite any existing identity or a deliberate manual clear.
    if game.archive is None or game.archive.name != filename or not game.archive.is_file():
        return False
    if codes_in(filename) or steam_ids_in(filename):
        return False
    meta = library.meta(game)
    if "product_code" in meta or any(meta.get(k) for k in
        ("product_store", "steam_app_id", "artwork_identity_code", "title_product_code")):
        return False
    return db.get_link(game.id) is None


def prepare_identity_import(text, library, games, db, *, allowed_names=None):
    """No writes, network, or fuzzy matching. Return accepted candidates and rejected reasons."""
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("JSON 결과는 최대 2MB까지 가져올 수 있습니다.")
    text = text.strip().lstrip("\ufeff").strip()
    if text.startswith("\x60\x60\x60"):
        match = re.fullmatch(r"\x60\x60\x60(?:json)?\s*\n(.*?)\n?\x60\x60\x60", text, re.S | re.I)
        if not match:
            raise ValueError("JSON만 붙여넣어 주세요.")
        text = match.group(1)
    try:
        data = json.loads(text, object_pairs_hook=_unique_object)
    except (ValueError, RecursionError) as exc:
        raise ValueError("올바른 PlayDock JSON 형식이 아닙니다.") from exc
    if not isinstance(data, dict) or data.get("format") != "PlayDock_Identity_Import" or type(data.get("version")) is not int or data["version"] != 1:
        raise ValueError("지원하는 형식은 PlayDock_Identity_Import 버전 1입니다.")
    rows = data.get("games")
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise ValueError("games 배열은 최대 1000개 항목이어야 합니다.")
    by_name = defaultdict(list)
    for game in games:
        if game.archive is not None:
            by_name[game.archive.name].append(game)
    counts = Counter(r.get("original_filename") for r in rows
                     if isinstance(r, dict) and isinstance(r.get("original_filename"), str))
    allowed = set(allowed_names) if allowed_names is not None else None
    proposals, rejected = [], []
    for index, row in enumerate(rows, 1):
        def reject(reason):
            rejected.append(f"{index}번: {reason}")
        if not isinstance(row, dict):
            reject("잘못된 항목"); continue
        name = row.get("original_filename")
        if not isinstance(name, str) or not name or len(name)>512 or any(c in name for c in "/\\\r\n\x00"):
            reject("원본 파일명 형식 오류"); continue
        if counts[name] != 1:
            reject(f"{name}: 중복 결과"); continue
        if allowed is not None and name not in allowed:
            reject(f"{name}: 현재 제외 목록에 없음"); continue
        status = row.get("status")
        reason = row.get("reason")
        reason = reason.strip()[:1000] if isinstance(reason, str) else ""
        if status not in ("confirmed", "needs_review"):
            reject(f"{name}: 미확인" + (f" · {reason}" if reason else "")); continue
        if status == "needs_review" and not reason:
            reject(f"{name}: 검토 근거 없음"); continue
        if status == "needs_review" and not row.get("product_code"):
            reject(f"{name}: 품번 후보 없음 · {reason}"); continue
        store, code, title, url = (row.get(k) for k in
                                  ("store","product_code","official_title","official_url"))
        if not all(isinstance(x,str) for x in (store,code,title,url)):
            reject(f"{name}: 필수 식별정보 누락"); continue
        code = code.strip().upper() if store == "dlsite" else code.strip()
        valid = (store=="dlsite" and DL_CODE.fullmatch(code) or
                 store=="steam" and STEAM_ID.fullmatch(code))
        if not valid or not title.strip() or len(title)>512 or len(url)>2048 or not _valid_url(store,code,url):
            reject(f"{name}: 품번 또는 공식 URL 형식 오류"); continue
        matches = by_name.get(name, [])
        if len(matches)!=1 or not _available(library,db,matches[0],name):
            reject(f"{name}: 게임 미등록·중복·기존 품번 또는 연결 보호"); continue
        proposals.append(IdentitySuggestion(matches[0],name,store,code,title.strip(),url,status,reason))
    return proposals, rejected


def collect_import_batch(proposals, library, db_path, *, is_cancelled=lambda: False,
                         callback=lambda i,total,event: None, collector_factory=None, verify_only=False):
    """Fetch by validated ID only (never open AI URLs), persist only verified work."""
    from pathlib import Path
    db = WorkDatabase(Path(db_path).parent, db_path=Path(db_path))
    collector = collector_factory(db) if collector_factory else CatalogCollector(db)
    proposals = tuple(proposals)
    events = []
    for index, suggestion in enumerate(proposals, 1):
        if is_cancelled():
            break
        g = suggestion.game
        entry = CatalogEntry(g.id, suggestion.filename, "archive",
                             suggestion.code if suggestion.store=="dlsite" else "",
                             suggestion.code if suggestion.store=="steam" else "")
        def excluded(message):
            return CatalogEvent(g.id,suggestion.filename,"excluded",message)
        try:
            if not _available(library,db,g,suggestion.filename):
                event = excluded("기존 품번 또는 게임 상태가 변경되어 제외")
            else:
                result = collector.collect_one(entry,link_game=False,force_lookup=True)
                if (result.outcome not in ("cached","fetched") or
                    (result.store,result.code)!=(suggestion.store,suggestion.code) or
                    not db.get_official_work(suggestion.store,suggestion.code)):
                    event = excluded("공식 품번 재확인 실패 · 품번 미등록")
                elif is_cancelled() or not _available(library,db,g,suggestion.filename):
                    event = excluded("중단 또는 기존 정보 변경 · 품번 미등록")
                elif verify_only:
                    event = replace(result, message="공식 품번 확인 완료 · 등록 승인 대기", connected=False)
                elif suggestion.status == "needs_review":
                    event = excluded("미확정 후보는 공식 조회 후 별도 등록 승인이 필요합니다.")
                else:
                    # Only an exact verified store/code is stored. User title/artwork
                    # and archive are never changed. Re-collection can repair a link
                    # if an unexpected DB write failure occurs after metadata save.
                    library.update_meta(g,product_store=suggestion.store,product_code=suggestion.code,
                                        identity_import_source="external_ai_verified")
                    if not db.save_verified_game_link(g.id,suggestion.store,suggestion.code):
                        event = replace(result,outcome="error",message="검증 품번 저장됨 · DB 연결 재수집 필요",connected=False)
                    else:
                        event = replace(result,message=f"{suggestion.store.upper()} {suggestion.code} 품번 등록·공식 연결 완료",connected=True)
        except Exception as exc:
            event = CatalogEvent(g.id,suggestion.filename,"error",f"가져오기 오류: {type(exc).__name__}")
        events.append(event)
        callback(index,len(proposals),event)
    return events


def approve_verified_import(proposals, events, library, db):
    """Commit only explicitly selected, freshly verified candidates; no web I/O."""
    verified = {(e.game_id,e.store,e.code):e for e in events
                if e.outcome in ("cached","fetched") and not e.connected}
    results = []
    for p in proposals:
        g = p.game
        event = verified.get((g.id,p.store,p.code))
        if event is None:
            continue
        try:
            if not _available(library,db,g,p.filename) or not db.get_official_work(p.store,p.code):
                results.append(replace(event,outcome="excluded",message="게임 또는 공식 정보 변경 · 등록 제외"))
                continue
            library.update_meta(g,product_store=p.store,product_code=p.code,
                                identity_import_source="external_ai_verified")
            connected = db.save_verified_game_link(g.id,p.store,p.code)
            results.append(replace(event,connected=bool(connected),
                outcome=event.outcome if connected else "error",
                message="품번 등록 및 공식 연결 완료" if connected else "품번 저장됨 · DB 연결 재수집 필요"))
        except Exception as exc:
            results.append(replace(event,outcome="error",message=f"등록 오류: {type(exc).__name__}"))
    return results
