"""6-B/C: 작품 후보별 공식 ID·설정 제목·명시적 별칭을 정확히 비교한다.

모호한 유사도/fuzzy match/자동 번역을 사용하지 않는다.
verified_aliases는 출처가 확인된 별칭을 호출자가 명시한 경우에만 사용한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .archive_identity import IdentityReport
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


def _explicit_alias_keys(title: str,
                         verified_aliases: Mapping[str, Sequence[str]] | None) -> set[str]:
    keys = {title_key(title)}
    if not verified_aliases:
        return keys
    # 키가 정규화된 정식 제목에 정확히 대응하는 경우만 신뢰.
    for primary, synonyms in verified_aliases.items():
        group = {title_key(primary)} | {
            title_key(v) for v in synonyms if isinstance(v, str)
        }
        if title_key(title) in group:
            keys.update(group)
    return {key for key in keys if key}


def candidates_from_report(report: IdentityReport,
                           records: tuple[EvidenceRecord, ...]) -> tuple[str, ...]:
    external: dict[str, str] = {}
    # 1~5단계의 검색 시도 결과를 전부 보존 (첫 결과만 쓰지 않음).
    for attempt in report.attempts:
        d = attempt.decision
        if d.status not in {
            "confirmed_game", "internet_confirmed_game",
            "platform_confirmed_game", "internet_candidate",
        }:
            continue
        value = d.proposed_title.strip()
        key = title_key(value)
        if key and key not in external:
            external[key] = value
    if external:
        return tuple(external.values())
    # 외부에서 후보를 찾지 못했다면 신뢰할 수 있는 내부 설정 제목을
    # 미확인 후보로 보고할 수는 있지만 일치 확인으로 승격하지 않는다.
    internal: dict[str, str] = {}
    for e in records:
        if e.origin == "internal_metadata" and e.kind == "title" and e.strength == "strong":
            key = title_key(e.value)
            if key and key not in internal:
                internal[key] = e.value
    return tuple(internal.values())


def compare_candidate(title: str, records: tuple[EvidenceRecord, ...],
                      *, verified_aliases: Mapping[str, Sequence[str]] | None = None,
                      report: IdentityReport | None = None) -> CandidateComparison:
    allowed = _explicit_alias_keys(title, verified_aliases)
    primary = title_key(title)
    own_official = any(e.kind == "title" and e.origin == "official"
                       and title_key(e.value) == primary for e in records)
    # 외부 비교는 같은 플랫폼 ID끼리만 한다.
    official_dlsite = _official_ids(records, "dlsite_code")
    official_steam = _official_ids(records, "steam_app_id")
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
