"""6-B/C: 작품 후보별 공식 ID·설정 제목·명시적 별칭을 정확히 비교한다.

모호한 유사도/fuzzy match/자동 번역을 사용하지 않는다.
verified_aliases는 출처가 확인된 별칭을 호출자가 명시한 경우에만 사용한다.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping, Sequence

from .archive_identity import IdentityReport
from .catalog_aliases import (
    catalog_titles, explicit_title_keys, group_external_attempts, representative,
)
from .detector import normalized_title
from .evidence_normalizer import EvidenceRecord


@dataclass(frozen=True)
class CandidateComparison:
    title: str
    official: bool
    official_ids: tuple[str, ...]
    id_matches: tuple[str, ...]
    id_conflicts: tuple[str, ...]
    strong_title_matches: tuple[str, ...]
    strong_title_disagreements: tuple[str, ...]
    supporting_title_matches: tuple[str, ...]
    independent_internal_groups: tuple[str, ...]
    verified_alias_matches: tuple[str, ...]

    @property
    def has_exact_strong_title(self) -> bool:
        return bool(self.strong_title_matches)

    @property
    def has_matching_official_id(self) -> bool:
        return bool(self.id_matches)


def title_key(value: str) -> str:
    return normalized_title(value or "")


def _official_ids(records: tuple[EvidenceRecord, ...], platform: str) -> set[str]:
    return {
        e.value.upper() if platform == "dlsite_code" else e.value
        for e in records if e.kind == platform and e.origin == "official"
    }


BILINGUAL_SEPARATOR = re.compile(r"\s+[-–—|]\s+")
CJK = re.compile(r"[가-힣ぁ-んァ-ヶ一-龯]")


def _bilingual_title_parts(title: str) -> set[str]:
    """'プロジェクトセナ - Project Sena -'의 명시적 병기 제목만 분리.

    'Adventure - Episode 2'와 같은 후속작·부제에는 적용하지 않는다.
    공식 제목의 CJK 부분과 영문 부분이 명확하게 나뉠 때만 허용한다.
    """
    parts = [part.strip(" -–—|") for part in BILINGUAL_SEPARATOR.split(title)]
    parts = [part for part in parts if part]
    if len(parts) < 2:
        return set()
    if (not any(CJK.search(part) for part in parts)
            or not any(re.search(r"[a-zA-Z]{3}", part) and not CJK.search(part)
                       for part in parts)):
        return set()
    return {title_key(part) for part in parts if len(part) >= 4}


def _explicit_alias_keys(title: str,
                         verified_aliases: Mapping[str, Sequence[str]] | None) -> set[str]:
    keys = {title_key(title)} | _bilingual_title_parts(title) | explicit_title_keys(title)
    if not verified_aliases:
        return keys
    # 키가 정규화된 정식 제목에 정확히 대응하는 경우만 신뢰.
    for primary, synonyms in verified_aliases.items():
        group = {title_key(primary)} | {
            title_key(v) for v in synonyms if isinstance(v, str)
        }
        if title_key(title) in group:
            keys.update(group)
            keys.update(_bilingual_title_parts(primary))
    return {key for key in keys if key}


def compatible_title_keys(
    title: str, verified_aliases: Mapping[str, Sequence[str]] | None = None,
) -> set[str]:
    return _explicit_alias_keys(title, verified_aliases)


def candidates_from_report(report: IdentityReport,
                           records: tuple[EvidenceRecord, ...]) -> tuple[str, ...]:
    external = catalog_titles(report.attempts)
    if external:
        return external
    # 외부에서 후보를 찾지 못했다면 신뢰할 수 있는 내부 설정 제목을
    # 미확인 후보로 보고할 수는 있지만 일치 확인으로 승격하지 않는다.
    internal: dict[str, str] = {}
    for e in records:
        if e.origin == "internal_metadata" and e.kind == "title" and e.strength == "strong":
            key = title_key(e.value)
            if key and key not in internal:
                internal[key] = e.value
    if internal:
        return tuple(internal.values())
    # 7z 솔리드처럼 설정을 읽을 수 없지만 파일명과 실제 EXE/루트명이
    # 일치하면 '확인 필요'용 로컬 후보로만 보존 (정식 작품 확인 아님).
    # 파일명만으로는 후보 생성하지 않음.
    from .search_terms import cleaned_search_title

    filename_key = title_key(cleaned_search_title(report.archive_name))
    for entry in records:
        if (entry.origin == "internal_index" and entry.kind == "title"
                and filename_key and title_key(entry.value) == filename_key):
            return (cleaned_search_title(report.archive_name),)
    return ()


def _candidate_official_ids(
    title: str, report: IdentityReport,
) -> tuple[set[str], set[str]]:
    """서로 다른 외부 후보 사이에서 공식 작품번호가 섞이지 않도록 보존."""
    dlsite: set[str] = set()
    steam: set[str] = set()
    # normalized_title은 버전 표기 등을 제거한다. 다른 상품 두 개가
    # 정규화 과정에서 같은 키가 되더라도 공식 번호를 서로 복사하면 안 된다.
    exact = title.strip().casefold()
    for group in group_external_attempts(report.attempts):
        if representative(group).decision.proposed_title.strip().casefold() != exact:
            continue
        for attempt in group:
            d = attempt.decision
            if (d.dlsite_code
                    and (d.status == "confirmed_game" or d.official_code_verified)):
                dlsite.add(d.dlsite_code.upper())
            if (d.source_platform in {"steam", "dlsite+steam"}
                    and d.source_id and d.status == "platform_confirmed_game"):
                steam.add(d.source_id)
        break
    return dlsite, steam


def compare_candidate(title: str, records: tuple[EvidenceRecord, ...],
                      *, verified_aliases: Mapping[str, Sequence[str]] | None = None,
                      report: IdentityReport | None = None) -> CandidateComparison:
    allowed = _explicit_alias_keys(title, verified_aliases)
    primary = title_key(title)
    own_official = any(e.kind == "title" and e.origin == "official"
                       and title_key(e.value) == primary for e in records)
    # 외부 비교는 같은 플랫폼 ID끼리만 한다.
    if report is None:
        official_dlsite = _official_ids(records, "dlsite_code")
        official_steam = _official_ids(records, "steam_app_id")
    else:
        official_dlsite, official_steam = _candidate_official_ids(title, report)
    # 명시적 공식 제목 후보가 여러 개인 경우, 다른 후보의 공식 ID를
    # 이 후보에 억지로 붙이지 않도록 6-D에서 복수후보 상태를 별도 처리.
    matches: list[str] = []
    conflicts: list[str] = []
    for platform, verified in (
        ("dlsite_code", official_dlsite), ("steam_app_id", official_steam)
    ):
        if not verified:
            continue
        inside = [
            e.value.upper() if platform == "dlsite_code" else e.value
            for e in records
            if e.kind == platform and e.origin == "internal_metadata"
            and e.strength == "strong"
        ]
        for value in sorted(set(inside)):
            label = f"{platform}:{value}"
            if value in verified:
                matches.append(label)
            else:
                conflicts.append(
                    f"{platform} 외부 공식 ID {','.join(sorted(verified))} != 내부 {value}"
                )

    strong: list[str] = []
    disagree: list[str] = []
    weak: list[str] = []
    groups: set[str] = set()
    aliases: list[str] = []
    for record in records:
        if record.origin != "internal_metadata" or record.kind != "title":
            continue
        key = title_key(record.value)
        if not key:
            continue
        if key in allowed:
            if record.strength == "strong":
                strong.append(record.value)
                groups.add(record.independence_group)
            else:
                weak.append(record.value)
            if key != primary:
                aliases.append(record.value)
        elif record.strength == "strong":
            disagree.append(record.value)

    return CandidateComparison(
        title, own_official,
        tuple(sorted(
            f"dlsite_code:{v}" for v in official_dlsite
        )) + tuple(sorted(f"steam_app_id:{v}" for v in official_steam)),
        tuple(sorted(set(matches))), tuple(sorted(set(conflicts))),
        tuple(dict.fromkeys(strong)), tuple(dict.fromkeys(disagree)),
        tuple(dict.fromkeys(weak)), tuple(sorted(groups)),
        tuple(dict.fromkeys(aliases)),
    )
