"""Independent PlayDock rename companion: scan JSON + AI review JSON -> controlled actions.

Does not search titles or mutate files. GUI owns the explicit rename approval.
Never trusts AI-supplied paths, scripts, filenames outside the scan's excluded set,
or the AI's 'official_confirmed' label as proof of an actual store lookup.
"""
from __future__ import annotations

from dataclasses import dataclass
import csv
import json
from pathlib import Path
import re
from typing import Iterable

from .research_handoff import (
    MAX_IMPORT_BYTES, SCHEMA, ResearchSuggestion, _public_basename,
    read_ai_response, excluded_from_results, load_previous_excluded,
    proposed_filename,
)

@dataclass(frozen=True)
class ReviewRow:
    filename: str
    ai_status: str           # claimed_confirmed / candidate / unknown / invalid
    suggestion: ResearchSuggestion | None
    proposed: str
    note: str
    exclusion_reason: str


def _read_json(path: str | Path, cap: int = MAX_IMPORT_BYTES * 5) -> dict:
    path = Path(path)
    if path.stat().st_size > cap:
        raise ValueError("파일이 너무 큽니다.")
    obj = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(obj, dict):
        raise ValueError("JSON 최상위는 객체여야 합니다.")
    return obj


def load_exclusions(path: str | Path) -> list[dict]:
    """Accept either PlayDock scanner results or PlayDock_Excluded_Research JSON."""
    doc = _read_json(path)
    if doc.get("schema") == SCHEMA and isinstance(doc.get("excluded"), list):
        entries = doc["excluded"]
    elif doc.get("results") is not None:
        entries = excluded_from_results(load_previous_excluded(path))
    else:
        raise ValueError("검사 결과/제외 목록 JSON이 아닙니다.")
    if len(entries) > 5000:
        raise ValueError("제외 목록이 너무 많습니다.")
    output, seen = [], set()
    for row in entries:
        if not isinstance(row, dict):
            continue
        name = _public_basename(row.get("original_filename"))
        if not name or name in seen:
            continue
        seen.add(name)
        reason = str(row.get("exclusion_reason") or "no_identifier")
        output.append({"original_filename": name, "exclusion_reason": reason})
    return output


def requires_manual_identity_check(filename: str) -> bool:
    """DLC or multiple products are intrinsically ambiguous even if a store ID exists.

    An ID for the base game must not be appended to a DLC archive.
    A single product ID must not silently identify a bundle of distinct works.
    """
    stem = Path(filename).stem
    return bool(
        re.search(r"(?i)(?<![a-z0-9])DLC(?:[ _-]*[0-9]+)?(?![a-z0-9])", stem)
        or re.search(r"\s[+＋]\s", stem)
    )


def load_review(scan_path: str | Path, ai_path: str | Path) -> tuple[list[ReviewRow], list[str]]:
    excluded = load_exclusions(scan_path)
    if not excluded:
        raise ValueError("검사 결과에 제외된 압축파일이 없습니다.")
    ai_doc = _read_json(ai_path, MAX_IMPORT_BYTES)
    if ai_doc.get("schema") != SCHEMA or not isinstance(ai_doc.get("results"), list):
        raise ValueError("AI 조사 응답은 playdock-ai-review-v1 결과 JSON이어야 합니다.")
    allowed = [x["original_filename"] for x in excluded]
    suggestions, warnings = read_ai_response(ai_path, allowed)
    chosen = {s.original_filename: s for s in suggestions}
    raw = {}
    for row in ai_doc["results"]:
        if isinstance(row, dict):
            name = row.get("original_filename")
            if name in allowed and name not in raw:
                raw[name] = row

    result = []
    for x in excluded:
        name = x["original_filename"]
        item = chosen.get(name)
        original = raw.get(name, {})
        claimed = str(original.get("verification") or "unknown").lower()
        if item is None:
            status = "invalid" if claimed in ("candidate", "official_confirmed") else "unknown"
        elif item.verification == "official_confirmed":
            status = ("identity_ambiguous" if requires_manual_identity_check(name)
                      else "claimed_confirmed")
        else:
            status = "candidate"
        if item is None:
            proposal = name
        else:
            try:
                proposal = proposed_filename(name, item.store, item.code)
            except ValueError:
                status, proposal = "invalid", name
        note = str(original.get("note") or "")[:400]
        if status == "identity_ambiguous":
            note = ("DLC/복수 작품 합본 가능성: 해당 품번이 정확히 이 파일의 작품을 "
                    "가리키는지 본편·DLC·합본을 구별해 수동 확인 필요. " + note)[:400]
        if status == "invalid":
            note = ("AI가 제안한 품번·URL·파일명 중 하나를 사용할 수 없습니다. "
                    + note).strip()
        result.append(ReviewRow(name, status, item, proposal, note,
                                x["exclusion_reason"]))
    return result, warnings


def manual_rows(rows: Iterable[ReviewRow], verified_names: set[str] | None = None
                ) -> list[ReviewRow]:
    """Everything without *successful official re-verification* is manual."""
    good = verified_names or set()
    return [r for r in rows if r.filename not in good]


def write_manual_csv(path: str | Path, rows: Iterable[ReviewRow],
                     verified_names: set[str] | None = None) -> int:
    pending = manual_rows(rows, verified_names)
    with Path(path).open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["원본 파일명", "AI 상태", "후보 스토어", "후보 품번",
                         "제외 사유", "수동 확인 안내", "조사 메모"])
        for r in pending:
            s = r.suggestion
            instructions = (
                "후보 작품이 파일 속 게임과 같은지 공식 페이지·제작자·시리즈 번호로 "
                "직접 확인하고, 맞으면 파일명에 품번을 추가하세요."
                if s else
                "공식 DLsite 또는 Steam에서 해당 게임을 직접 찾으세요. "
                "등록 정보가 없으면 파일명은 그대로 두세요."
            )
            writer.writerow([r.filename, r.ai_status, s.store if s else "",
                             s.code if s else "", r.exclusion_reason,
                             instructions, r.note])
    return len(pending)
