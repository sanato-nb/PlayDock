"""PlayDock excluded-file AI handoff, verification, safe rename and undo.

Pure standard library. No AI provider, account, API key or background upload.
An AI answer is an *untrusted suggestion*: store identifiers MUST be verified
against the official store before any archive can be renamed.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
from typing import Callable, Iterable

from .code_only import InputItem, Result, Work, archive_name, codes_in, steam_ids_in, check
from .detector import EXACT_CODE, product_page_candidate
from .steam_client import STEAM_ID

SCHEMA = "playdock-ai-review-v1"
MAX_IMPORT_BYTES = 2_000_000
MAX_IMPORT_ROWS = 1000
INVALID_WINDOWS = re.compile(r'[\x00-\x1f<>:"/\\|?*]')
RESERVED = re.compile(r"(?i)^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)")
CODE_PATTERN_STR = r"(?:RJ|VJ|BJ|EJ)\d{6,8}"


@dataclass(frozen=True)
class ResearchSuggestion:
    original_filename: str
    store: str
    code: str
    official_title: str = ""
    official_url: str = ""
    evidence_url: str = ""
    verification: str = "candidate"
    note: str = ""


@dataclass(frozen=True)
class VerifiedSuggestion:
    suggestion: ResearchSuggestion
    verified: bool
    official_title: str = ""
    official_url: str = ""
    reason: str = ""


def _public_basename(value: object) -> str:
    raw = str(value or "").strip()
    if (not raw or len(raw) > 255 or "\x00" in raw or
            "/" in raw or "\\" in raw or raw in (".", "..")):
        return ""
    return raw if archive_name(raw) == raw else ""


def excluded_from_results(results: Iterable[Result | dict]) -> list[dict]:
    """Export only excluded filenames; never local paths or other user data."""
    found: list[dict] = []
    seen = set()
    for source in results:
        if isinstance(source, Result):
            raw = source.to_dict()
        elif isinstance(source, dict):
            raw = source
        else:
            continue
        if raw.get("status") != "excluded":
            continue
        name = _public_basename(raw.get("query", ""))
        if not name or name in seen:
            continue
        seen.add(name)
        found.append({
            "original_filename": name,
            "dlsite_codes": list(codes_in(name)),
            "steam_app_ids": list(steam_ids_in(name)),
            "exclusion_reason": (
                "official_lookup_failed" if
                (codes_in(name) or steam_ids_in(name)) else "no_identifier"
            ),
        })
    return found


def research_export(results: Iterable[Result | dict]) -> dict:
    return {
        "schema": SCHEMA,
        "task": "research_excluded_identifiers",
        "privacy": "filename_only_no_local_paths",
        "excluded": excluded_from_results(results),
        "expected_ai_response": {
            "schema": SCHEMA,
            "results": [{
                "original_filename": "Original Game [v1.0].zip",
                "store": "dlsite",
                "code": "RJ123456",
                "official_title": "Official Title",
                "official_url": "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html",
                "evidence_url": "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html",
                "verification": "official_confirmed",
                "note": "같은 게임인 근거(번역명·개발자·시리즈 번호)"
            }],
        },
    }


def research_prompt() -> str:
    return """# PlayDock — 제외 게임 공식 품번 조사

첨부한 PlayDock_Excluded_Research.json에서 excluded 배열만 조사해 주세요.
이 목록에는 로컬 폴더 경로가 없으며 파일을 변경할 권한을 부여하지 않습니다.

검색 순서 및 검증:
1. 기존 DLsite 품번(RJ/VJ/BJ/EJ)이 있으면 그 번호의 공식 페이지부터 검증.
2. 그렇지 않으면 파일명 속 제목(한국어/영문/일본어 병기)을 조사해 DLsite 공식 작품 페이지 탐색.
3. DLsite에서 동일 게임을 확인하지 못하면 Steam 공식 스토어 App ID 조사.
4. 작품 번호가 실제 해당 게임과 같은 것인지 공식 작품명·제작자·시리즈 번호 등 독립 근거로 확인.
5. 이름이 유사한 다른 게임·DLC·다른 시리즈 번호는 같은 작품으로 단정하지 말 것.
6. 확인하지 못한 후보는 verification='candidate'로, 근거 없으면 'unknown'으로 표시.
7. RJ 품번/App ID를 임의 생성하거나 신뢰할 수 없는 비공식 링크만으로 확인 판정하지 말 것.
8. 출력에 로컬 전체 경로, 개인 데이터, 암호, 파일 내용이나 실행명령을 포함하지 말 것.
9. 실제 파일명은 변경하지 말 것. PlayDock에서 공식 사이트 재검증 후 사용자가 승인합니다.

출력은 아래 JSON 형식의 단일 객체만 작성하세요. JSON 마크다운 코드블록 없이:
{
  "schema": "playdock-ai-review-v1",
  "results": [
    {
      "original_filename": "첨부된 제외 목록에 있는 파일명과 정확히 동일",
      "store": "dlsite 또는 steam",
      "code": "RJ123456 또는 1091500 (확인 못하면 빈 문자열)",
      "official_title": "공식 작품명 (모르면 빈 문자열)",
      "official_url": "식별번호와 일치하는 해당 공식 스토어 작품 URL",
      "evidence_url": "판별 근거가 있는 공개 출처 URL (모르면 빈 문자열)",
      "verification": "official_confirmed 또는 candidate 또는 unknown",
      "note": "간단한 연결 근거 또는 실패 이유"
    }
  ]
}

모든 excluded 항목을 results에 포함하세요. official_confirmed는 사이트에
작품이 존재한다는 사실뿐 아니라 *제공한 파일명과 같은 작품*이라는 연결
근거가 있을 때만 사용하세요. 확실하지 않으면 candidate를 쓰세요.
"""


def _store_url_matches(store: str, code: str, url: str) -> bool:
    from urllib.parse import urlsplit
    if not url:
        return False
    try:
        if store == "dlsite":
            got = product_page_candidate(url)
            return got is not None and got[0] == code
        if store == "steam":
            parts = urlsplit(url)
            return (
                parts.scheme == "https" and parts.hostname == "store.steampowered.com"
                and not parts.username and not parts.password
                and re.fullmatch(r"/app/" + re.escape(code) + r"(?:/[^/]*)?/?", parts.path)
                is not None
            )
    except (ValueError, TypeError):
        pass
    return False


def read_ai_response(path: str | Path, excluded_names: Iterable[str]) -> tuple[list[ResearchSuggestion], list[str]]:
    """Strictly parse untrusted AI results; unknown/unsafe results are not actionable."""
    path = Path(path)
    if path.stat().st_size > MAX_IMPORT_BYTES:
        raise ValueError("AI 결과 JSON이 허용 크기를 초과했습니다.")
    obj = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(obj, dict) or obj.get("schema") != SCHEMA:
        raise ValueError("PlayDock AI 조사 결과 JSON 형식(schema)이 아닙니다.")
    rows = obj.get("results")
    if not isinstance(rows, list) or len(rows) > MAX_IMPORT_ROWS:
        raise ValueError("AI 조사 결과 목록 형식 또는 항목 수가 올바르지 않습니다.")
    allowed = set(excluded_names)
    found, errors, seen = [], [], set()
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"{i+1}번: 결과가 JSON 객체가 아닙니다")
            continue
        raw_name = row.get("original_filename", "")
        name = _public_basename(raw_name)
        store = str(row.get("store") or "").strip().lower()
        code = str(row.get("code") or "").strip().upper()
        title = str(row.get("official_title") or "").strip()[:240]
        url = str(row.get("official_url") or "").strip()[:500]
        evidence_url = str(row.get("evidence_url") or "").strip()[:500]
        verification = str(row.get("verification") or "candidate").strip().lower()
        if not name or name not in allowed:
            errors.append(f"{i+1}번: 제외 목록에 없는 파일명 또는 안전하지 않은 파일명")
            continue
        if name in seen:
            errors.append(f"{i+1}번: 동일 파일명 중복 (중복 건은 사용하지 않음)")
            continue
        seen.add(name)
        if verification not in ("official_confirmed", "candidate", "unknown"):
            errors.append(f"{i+1}번: 검증 상태 값이 올바르지 않음")
            continue
        if verification == "unknown" or not code:
            continue  # Keep unknown records in original excluded list, not rename candidates.
        if not ((store == "dlsite" and EXACT_CODE.fullmatch(code)) or
                (store == "steam" and STEAM_ID.fullmatch(code))):
            errors.append(f"{i+1}번: 공식 식별번호 형식이 아님")
            continue
        if url and not _store_url_matches(store, code, url):
            errors.append(f"{i+1}번: 공식 URL이 해당 스토어/식별번호와 불일치")
            continue
        found.append(ResearchSuggestion(
            name, store, code, title, url, evidence_url, verification,
            str(row.get("note") or "")[:400],
        ))
    return found, errors


def reverify(
    suggestion: ResearchSuggestion,
    *, dlsite_check: Callable[[str], object] | None = None,
    steam_check: Callable[[str], object] | None = None,
) -> VerifiedSuggestion:
    """Always verify fresh official data, never trust AI's word or URL alone.

    A candidate remains non-actionable even if its ID exists unless the user
    confirmed it represents the correct local game (official_confirmed state).
    """
    if suggestion.verification != "official_confirmed":
        return VerifiedSuggestion(suggestion, False, reason="AI 결과가 동일 작품 확인 상태가 아닙니다")
    if not _public_basename(suggestion.original_filename):
        return VerifiedSuggestion(suggestion, False, reason="파일명 형식 오류")
    if not _store_url_matches(suggestion.store, suggestion.code, suggestion.official_url):
        return VerifiedSuggestion(suggestion, False, reason="정확한 공식 작품 URL 필요")
    from .code_only import fetch_steam_public
    from .no_api_html import fetch_dlsite_html
    try:
        if suggestion.store == "dlsite":
            checker = dlsite_check or fetch_dlsite_html
            product = checker(suggestion.code)
            if (product is None or getattr(product, "code", "") != suggestion.code or
                    not getattr(product, "title", "").strip() or
                    not _store_url_matches("dlsite", suggestion.code, product.url)):
                return VerifiedSuggestion(suggestion, False, reason="DLsite 공식 작품 재조회 불일치")
            title, url = product.title, product.url
        elif suggestion.store == "steam":
            checker = steam_check or fetch_steam_public
            product = checker(suggestion.code)
            if (product is None or getattr(product, "app_id", "") != suggestion.code or
                    not getattr(product, "title", "").strip() or
                    not _store_url_matches("steam", suggestion.code, product.url)):
                return VerifiedSuggestion(suggestion, False, reason="Steam 공식 작품 재조회 불일치")
            title, url = product.title, product.url
        else:
            return VerifiedSuggestion(suggestion, False, reason="지원하지 않는 플랫폼")
    except Exception as exc:
        return VerifiedSuggestion(suggestion, False, reason=f"공식 조회 실패: {type(exc).__name__}")
    # No strict cross-language comparison: translated Korean archive names are legitimate.
    # The user still must choose the archive and approve the suggested rename.
    return VerifiedSuggestion(suggestion, True, title, url,
                              "공식 식별번호/작품명 재확인됨 · 파일 동일성은 사용자 검수 필요")


def proposed_filename(old_name: str, store: str, code: str) -> str:
    """Keep every existing version/translation/DLC tag; append identifier only."""
    if not _public_basename(old_name):
        raise ValueError("유효한 압축파일 이름이 아닙니다.")
    if not ((store == "dlsite" and EXACT_CODE.fullmatch(code)) or
            (store == "steam" and STEAM_ID.fullmatch(code))):
        raise ValueError("공식 식별번호가 올바르지 않습니다.")
    if store == "dlsite" and code in codes_in(old_name):
        return old_name
    if store == "steam" and code in steam_ids_in(old_name):
        return old_name
    path = Path(old_name)
    mark = f"[{code}]" if store == "dlsite" else f"[Steam {code}]"
    return f"{path.stem} {mark}{path.suffix}"


def _safe_name(value: str) -> bool:
    if not isinstance(value, str) or not value or value in (".", ".."):
        return False
    if value.strip() != value or value.endswith(".") or INVALID_WINDOWS.search(value):
        return False
    if RESERVED.match(value) or len(value) > 250:
        return False
    return True


def safe_rename(old_path: Path, new_filename: str, journal: Path) -> tuple[Path, str]:
    """Local archive only; never clobber existing file. Log and recover after failure."""
    old_path = Path(old_path)
    if old_path.is_symlink() or not old_path.is_file():
        raise ValueError("원본 파일이 없거나 심볼릭 링크입니다.")
    if not archive_name(old_path.name) or not _safe_name(new_filename):
        raise ValueError("압축파일명/새 이름이 유효하지 않습니다.")
    if new_filename.casefold() == old_path.name.casefold():
        raise ValueError("파일명이 변경되지 않습니다.")
    if Path(new_filename).suffix.casefold() != old_path.suffix.casefold():
        raise ValueError("원본 압축 확장자는 변경할 수 없습니다.")
    dest = old_path.with_name(new_filename)
    # Reject Windows-insensitive collision even on case-sensitive test runner.
    if any(p.name.casefold() == new_filename.casefold()
           for p in old_path.parent.iterdir()):
        raise FileExistsError("변경할 이름의 파일이 이미 있습니다.")
    if dest.exists() or dest.is_symlink():
        raise FileExistsError("동일 이름 대상 파일이 존재합니다.")
    journal = Path(journal)
    journal.parent.mkdir(parents=True, exist_ok=True)
    # A preflight writable check prevents unlogged mutations due to permissions.
    with journal.open("a", encoding="utf-8"):
        pass
    old_path.rename(dest)
    event = {"event": "rename", "at": datetime.now(timezone.utc).isoformat(),
             "before": str(old_path.resolve(strict=False)),
             "after": str(dest.resolve(strict=False))}
    try:
        with journal.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        # In case of failed journaling, restore the file when safe.
        if dest.is_file() and not old_path.exists():
            dest.rename(old_path)
        raise
    return dest, "파일명 변경 완료 · 로컬 기록 저장"


def undo_last(journal: Path) -> tuple[Path, Path]:
    """Undo most recently active rename only, refuse overwrites and missing files."""
    journal = Path(journal)
    if not journal.is_file():
        raise ValueError("복구할 파일명 변경 기록이 없습니다.")
    events = []
    for line in journal.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    # Each rename is uniquely identified by index; reverse only the latest
    # rename not already cancelled by a later undo.
    cancelled = {r.get("rename_index") for r in events if r.get("event") == "undo"}
    for i in range(len(events)-1, -1, -1):
        event = events[i]
        if event.get("event") != "rename" or i in cancelled:
            continue
        before, after = Path(event["before"]), Path(event["after"])
        if before.parent != after.parent:
            raise ValueError("서로 다른 폴더 간 이동은 복구할 수 없습니다.")
        if before.exists() or before.is_symlink() or not after.is_file() or after.is_symlink():
            raise FileExistsError("원래 이름에 파일이 있거나 변경된 파일을 찾지 못해 복구 중단")
        after.rename(before)
        try:
            with journal.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"event":"undo", "rename_index":i,
                                    "at":datetime.now(timezone.utc).isoformat()},
                                   ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
        except OSError:
            if before.is_file() and not after.exists():
                before.rename(after)
            raise
        return after, before
    raise ValueError("원상복구할 변경 기록이 없습니다.")


def default_journal() -> Path:
    root = os.environ.get("LOCALAPPDATA", "")
    if root:
        return Path(root) / "PlayDock" / "rename-history.jsonl"
    return Path.home() / ".playdock" / "rename-history.jsonl"



def load_previous_excluded(path: str | Path) -> list[Result]:
    """Read an earlier PlayDock scan solely to recover excluded filenames.

    Does not import candidates, filesystem paths, scripts, or automatic rename
    authority from that JSON.
    """
    file = Path(path)
    if file.stat().st_size > MAX_IMPORT_BYTES * 4:
        raise ValueError("이전 검사 JSON 파일이 너무 큽니다.")
    obj = json.loads(file.read_text(encoding="utf-8-sig"))
    if not isinstance(obj, dict) or not isinstance(obj.get("results"), list):
        raise ValueError("PlayDock 검사 결과 JSON 형식이 아닙니다.")
    if len(obj["results"]) > 5000:
        raise ValueError("검사 결과가 너무 많습니다.")
    out: list[Result] = []
    for entry in obj["results"]:
        if not isinstance(entry, dict) or entry.get("status") != "excluded":
            continue
        name = _public_basename(entry.get("query"))
        if not name:
            continue
        out.append(Result(
            name,
            "archive" if entry.get("input_origin") == "archive" else "manual",
            "excluded",
            warnings=tuple(str(x)[:200] for x in entry.get("warnings", [])
                           if isinstance(x, str))[:5],
            attempted_stores=tuple(s for s in entry.get("attempted_stores", [])
                                   if s in ("dlsite", "steam"))[:2],
        ))
    return out
