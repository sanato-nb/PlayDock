"""6-D: 다섯 가지 정체 판정. 임의 점수/퍼센트 없이 보수적 규칙만 사용한다.

입력은 1~5단계의 읽기 전용 결과이며 원본 파일·UI·사용자 DB는 변경하지 않는다.
"""
from __future__ import annotations

import re
import time
from typing import Mapping, Sequence

from .archive_identity import IdentityReport
from .detector import normalized_title
from .evidence_normalizer import EvidenceRecord, normalize_evidence
from .identity_hints import extract_hints
from .search_terms import cleaned_search_title
from .search_plan import _useful_title
from .catalog_aliases import (
    DISTRIBUTION_PREFIX, group_external_attempts, representative,
)
from .identity_matcher import (
    CandidateComparison, candidates_from_report, compare_candidate,
    compatible_title_keys, title_key,
)
from .verification_report import VerificationReport

FILE_ONLY = frozenset({
    "patch_candidate", "dlc_candidate", "server_package_candidate",
    "modpack_candidate", "bundle_candidate",
})

TRANSLATION_PRODUCT = re.compile(
    r"(?i)(?:【\s*(?:AI\s*)?(?:번역|翻訳)\s*패치|翻訳パッチ"
    r"|\[\s*translation\s*patch\s*\])"
)
DLC_PRODUCT = re.compile(r"(?i)(?:\bDLC\b|ダウンロードコンテンツ|추가\s*콘텐츠)")


def _catalog_release_type(title: str) -> str:
    if TRANSLATION_PRODUCT.search(title):
        return "translation_patch"
    if DLC_PRODUCT.search(title):
        return "dlc"
    return "unspecified"


def _possible_translation_relations(report: IdentityReport) -> tuple[str, ...]:
    """다른 공식 코드의 본편/번역 패치 '연관 가능성'만 별도 표시.

    동일 제목은 상품 동일성의 증거가 아니다. 공식 링크를 실제 검증하기
    전까지 서로 다른 제품을 병합하거나 자동 선택하지 않는다.
    """
    items = []
    for group in group_external_attempts(report.attempts):
        item = representative(group).decision
        if not (item.status == "confirmed_game" and item.dlsite_code):
            continue
        kind = _catalog_release_type(item.proposed_title)
        cleaned = DISTRIBUTION_PREFIX.sub("", item.proposed_title).strip()
        if kind == "translation_patch":
            key = normalized_title(cleaned)
        elif kind == "unspecified":
            key = normalized_title(item.proposed_title)
        else:
            continue
        if key:
            items.append((kind, key, item.dlsite_code.upper()))
    relations = []
    for kind, key, patch_code in items:
        if kind != "translation_patch":
            continue
        for other, other_key, original_code in items:
            if (other == "unspecified" and key == other_key
                    and patch_code != original_code):
                relations.append(
                    f"번역 패치 후보 {patch_code} ↔ 원작 후보 {original_code}: "
                    "공식 상품명 기반 연관 가능성 (공식 상호 링크 미검증)"
                )
    return tuple(dict.fromkeys(relations))

GAME_DATA_SIGNALS = frozenset({
    "Ren'Py 게임 데이터 파일 존재",
    "RPG Maker 게임 데이터 파일 존재",
    "Godot 게임 데이터 파일 후보",
    "NW.js/Electron 패키지 데이터 존재",
    "RPG Maker MV/MZ 게임 데이터 존재",
})


def _package_assessment(report: IdentityReport, filename_kind: str) -> str:
    """파일 구성 *추정*은 게임 정체 판정과 분리한다."""
    if filename_kind in FILE_ONLY:
        return filename_kind
    if report.encryption_state != "clear" or not report.inspection:
        return "unverified"
    signals = set(report.inspection.package_signals)
    exe = "Windows 실행파일 존재" in signals
    data = bool(signals & GAME_DATA_SIGNALS) or (
        "Unity" in report.inspection.engine_hints
    )
    if exe and data:
        return "game_payload_candidate"
    if exe:
        return "executable_only"
    if data:
        return "game_data_without_executable"
    return "unknown"


def _resolve_alias_candidates(candidates: tuple[str, ...],
                              verified_aliases: Mapping[str, Sequence[str]] | None) -> tuple[str, ...]:
    """검증된 별칭으로 표현만 다른 같은 외부 후보를 접되, 추측으로 합치지 않는다."""
    if not verified_aliases:
        return candidates
    groups: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = title_key(candidate)
        group_key = key
        for primary, aliases in verified_aliases.items():
            if key in {title_key(primary)} | {
                title_key(a) for a in aliases if isinstance(a, str)
            }:
                group_key = title_key(primary)
                break
        if group_key not in seen:
            seen.add(group_key)
            groups.append(candidate)
    return tuple(groups)


def verify_identity(
    report: IdentityReport,
    *,
    verified_aliases: Mapping[str, Sequence[str]] | None = None,
) -> VerificationReport:
    """수집 근거로만 판정. verified_aliases는 검증된 출처의 별칭만 전달.

    같은 제목, 파일명 코드, README 여러 개, 작품 페이지 검색 성공만으로
    '일치 확인'을 절대 만들지 않는다. 암호 파일은 오직 이름 근거만 평가.
    """
    verification_start = time.perf_counter()
    hints = extract_hints(report.archive_name)
    records = normalize_evidence(report)
    external = candidates_from_report(report, records)
    candidates = _resolve_alias_candidates(external, verified_aliases)
    comparisons = tuple(
        compare_candidate(
            title, records, verified_aliases=verified_aliases, report=report,
        )
        for title in candidates
    )
    kind = hints.archive_kind
    candidate_relationships = _possible_translation_relations(report)
    package = _package_assessment(report, kind)
    localized = (
        "korean_files_present_unverified"
        if report.encryption_state == "clear" and report.inspection
        and report.inspection.localization_signals else "not_verified"
    )
    index_state = report.inspection.state if report.inspection else "not_inspected"
    meta_state = report.metadata.state if report.metadata else "not_inspected"

    limitations: list[str] = ["압축파일과 공식 작품의 진위는 암호학적으로 인증되지 않았습니다."]
    blockers: list[str] = []
    applied: list[str] = []
    verdict = "needs_review"
    selected = ""

    if report.encryption_state == "encrypted":
        limitations.append("암호화된 압축파일: 내부 파일명과 메타데이터를 이용하지 않았습니다.")
        if not candidates:
            verdict = "unclassifiable"
            blockers.append("파일명 기반 작품 검색 결과가 없습니다.")
        else:
            verdict = "needs_review"
            selected = candidates[0] if len(candidates) == 1 else ""
            blockers.append("파일명 조회 결과만 있고 내부 근거를 확인할 수 없습니다.")
        applied.append("encrypted_filename_only")
    elif report.encryption_state != "clear":
        limitations.append("암호화 상태가 불명확하여 내부 정보로 대조하지 못했습니다.")
        verdict = "needs_review" if candidates else "unclassifiable"
        selected = candidates[0] if len(candidates) == 1 else ""
        blockers.append("내부 검사 불가")
        applied.append("unreadable_archive")
    else:
        # 별칭이 동일하더라도 같은 플랫폼의 서로 다른 *공식* 상품 ID를
        # 하나의 게임으로 자동 합쳐서는 안 된다.
        conflicting_official_platforms = [
            platform for platform in ("steam_app_id", "dlsite_code")
            if len({e.value for e in records if e.kind == platform
                    and e.origin == "official"}) > 1
        ]
        if index_state != "ok":
            limitations.append(f"내부 목록 검사 완전성 부족: {index_state}")
        failed_queries = [
            attempt for attempt in report.attempts
            if any(token in attempt.decision.reason for token in (
                "검색 오류", "조회 실패", "RuntimeError", "TimeoutError",
                "ConnectionError", "HTTPError",
            ))
        ]
        if failed_queries:
            limitations.append(
                f"검색 서비스 오류/차단 {len(failed_queries)}회: 정체가 존재하지 않음을 뜻하지 않습니다."
            )
        if meta_state not in {"ok", "no_metadata"}:
            limitations.append(f"메타데이터 미검사·부분 검사: {meta_state}")
        if kind in FILE_ONLY:
            blockers.append(f"본편으로 단정할 수 없는 배포 유형: {kind}")
            applied.append("non_base_distribution_guard")

        # 여러 게임이 포함되거나 검색 결과가 서로 다른 작품인 경우
        # 한 작품으로 자동 병합하지 않는다.
        strong_titles = {title_key(e.value) for e in records
                         if e.kind == "title" and e.origin == "internal_metadata"
                         and e.strength == "strong" and title_key(e.value)}
        known_aliases: set[str] = set()
        if len(candidates) == 1:
            selected = candidates[0]
            primary = title_key(selected)
            known_aliases.update(compatible_title_keys(selected, verified_aliases))
        distinct_internal = strong_titles - known_aliases
        # 같은 이름이 내부에서만 발견되어도 외부 작품 검증을 대체할 수 없다.
        external_candidate_present = any(
            e.kind == "title" and e.origin in {"official", "web_candidate"}
            and title_key(e.value) in known_aliases
            for e in records
        )
        # ID와 제목이 서로 다른 루트 게임 폴더에 있을 때는 독립적으로
        # 한 게임의 동일성 증명에 사용하지 않는다.
        matching_id_groups = set()
        matching_title_groups = set()
        if len(comparisons) == 1:
            matching_ids = set(comparisons[0].id_matches)
            matched_titles = {title_key(v) for v in comparisons[0].strong_title_matches}
            for evidence in records:
                if evidence.origin != "internal_metadata" or evidence.strength != "strong":
                    continue
                if (evidence.kind in {"dlsite_code", "steam_app_id"}
                        and f"{evidence.kind}:{evidence.value}" in matching_ids):
                    matching_id_groups.add(evidence.independence_group)
                if evidence.kind == "title" and title_key(evidence.value) in matched_titles:
                    matching_title_groups.add(evidence.independence_group)
        id_and_title_same_root = bool(matching_id_groups & matching_title_groups)

        if conflicting_official_platforms and candidate_relationships:
            # 원작과 별도 판매되는 번역 패치가 공식 제목상 관련되어도
            # 실제 같은 게임 파일이라고 확정하거나 두 코드를 합치지 않는다.
            verdict = "needs_review"
            blockers.append(
                "서로 다른 공식 작품번호가 본편·번역 패치 관계일 가능성이 "
                "있습니다. 실제 등록 관계와 로컬 배포 구성을 확인하세요."
            )
            applied.append("possible_translation_patch_relation")
            selected = ""
        elif conflicting_official_platforms:
            verdict = "conflict"
            blockers.append("동일 플랫폼에서 서로 다른 공식 작품 ID가 조회되었습니다: "
                            + ", ".join(conflicting_official_platforms))
            applied.append("multiple_official_product_ids")
            selected = ""
        elif len(candidates) > 1:
            verdict = "needs_review"
            blockers.append("서로 다른 외부 작품 후보가 복수 발견되었습니다.")
            applied.append("multiple_external_candidates")
            selected = ""
        elif len(strong_titles) > 1 and kind == "bundle_candidate":
            verdict = "needs_review"
            blockers.append("여러 게임 제목 근거가 있는 합본 후보입니다.")
            applied.append("bundle_multiple_titles")
            selected = ""
        elif not comparisons:
            verdict = "needs_review" if (strong_titles or failed_queries or any(
                e.kind in {"dlsite_code", "steam_app_id"} for e in records
            )) else "unclassifiable"
            blockers.append("외부에서 확인된 게임 정체 후보가 없습니다.")
            applied.append("no_external_match")
            selected = candidates[0] if len(candidates) == 1 else ""
        else:
            item = comparisons[0]
            # 일부 강한 이름이 다른 경우 별도 게임/번역명/프로젝트 이름일
            # 가능성이 있으므로 단일 게임으로 확정하지 않는다.
            if item.id_conflicts:
                verdict = "conflict"
                blockers.extend(item.id_conflicts)
                applied.append("same_platform_official_id_conflict")
            elif item.strong_title_disagreements:
                if len(strong_titles) > 1:
                    verdict = "needs_review"
                    blockers.append("서로 다른 내부 게임 제목이 여러 개 있습니다.")
                    applied.append("possible_multiple_games_or_aliases")
                    selected = ""
                else:
                    # ID가 일치하지 않는 단일 설정 제목 차이는 버전/부제/
                    # 개발 시 프로젝트명 가능성이 있어 곧바로 다른 작품 확정 금지.
                    verdict = "needs_review"
                    blockers.append("내부 게임 제목과 외부 작품 제목이 다릅니다. "
                                    "버전·개발용 프로젝트명·별칭인지 확인이 필요합니다.")
                    applied.append("strong_title_disagreement_review")
            elif kind in FILE_ONLY:
                verdict = "needs_review"
                applied.append("file_type_blocks_game_confirmation")
            elif (item.official and item.id_matches and item.has_exact_strong_title
                  and id_and_title_same_root
                  and package == "game_payload_candidate"
                  and index_state == "ok" and meta_state == "ok"):
                verdict = "matched"
                applied.extend((
                    "official_id_matches_internal_explicit_id",
                    "strong_internal_title_matches",
                    "game_executable_and_engine_payload_present",
                    "complete_internal_index",
                ))
            elif (external_candidate_present and item.has_exact_strong_title and
                  package == "game_payload_candidate" and index_state == "ok"):
                verdict = "likely_candidate"
                applied.append("title_and_game_payload_correlate")
                if item.id_matches:
                    applied.append("explicit_id_correlates")
            else:
                verdict = "needs_review"
                blockers.append("독립적인 내부 작품 ID·강한 제목·게임 구성 근거가 충분하지 않습니다.")
                applied.append("insufficient_identity_evidence")

        if index_state != "ok" and verdict in {"matched", "likely_candidate"}:
            verdict = "needs_review"
            blockers.append("내부 파일 목록 검사가 끝나지 않았습니다.")
        if meta_state != "ok" and verdict == "matched":
            verdict = "needs_review"
            blockers.append("내부 메타데이터 검사가 완료되지 않았습니다.")

    # '공식 작품을 찾음'은 '내 압축파일이 그 작품임'과 별개의 판단.
    catalog_ids = tuple(sorted({
        f"{e.kind}:{e.value}"
        for e in records if e.origin == "official"
        and e.kind in {"steam_app_id", "dlsite_code"}
    }))
    official_titles = tuple(
        a.decision.proposed_title
        for a in report.attempts
        if (a.decision.status in {
            "confirmed_game", "platform_confirmed_game", "internet_confirmed_game"
        } or a.decision.official_code_verified) and a.decision.proposed_title
    )
    web_found = any(
        a.decision.status == "internet_candidate" for a in report.attempts
    )
    skipped = any(a.decision.search_state == "cooldown_skipped"
                  for a in report.attempts)
    search_failure = any(
        a.decision.search_state == "network_error" or
        any(term in a.decision.reason for term in (
            "검색 오류", "조회 실패", "RuntimeError", "TimeoutError",
            "연속 장애", "ConnectionError",
        )) for a in report.attempts
    )
    unverified_web = any(a.decision.search_state == "unverified_evidence"
                         for a in report.attempts)
    official_id_conflict = any(
        len({e.value for e in records if e.origin == "official"
             and e.kind == platform}) > 1
        for platform in ("dlsite_code", "steam_app_id")
    )
    if official_id_conflict and candidate_relationships:
        catalog_status = "related_products_review"
    elif official_id_conflict:
        catalog_status = "conflicting_official_ids"
    elif len(candidates) > 1:
        catalog_status = "multiple_candidates"
    elif official_titles:
        catalog_status = "official_game_found"
    elif web_found:
        catalog_status = "web_candidate"
    elif skipped:
        catalog_status = "skipped_due_to_cooldown"
    elif search_failure:
        catalog_status = "lookup_error"
    elif unverified_web:
        catalog_status = "unverified_evidence"
    else:
        catalog_status = "not_found"
    catalog_title = candidates[0] if len(candidates) == 1 and (
        official_titles or web_found) else ""
    catalog_release_type = _catalog_release_type(
        official_titles[0] if len(official_titles) == 1 else catalog_title
    )
    if candidate_relationships:
        catalog_release_type = "mixed_related_products"
    if catalog_release_type in {"translation_patch", "dlc"}:
        blockers.append(
            "외부 조회 작품이 본편과 별도 등록된 번역 패치/DLC일 수 있습니다. "
            "원작과 동일한 상품으로 자동 연결하지 않습니다."
        )
        if verdict in {"matched", "likely_candidate"}:
            verdict = "needs_review"
            applied.append("non_base_catalog_product_guard")

    if any(a.decision.official_code_verified for a in report.attempts):
        limitations.append(
            "웹 검색의 작품번호를 통해 공식 등록을 확인했으나 "
            "로컬 배포 파일과 같은 작품이라는 증거는 아닙니다."
        )
        if verdict in {"matched", "likely_candidate"}:
            verdict = "needs_review"
            blockers.append("웹 검색 유래 작품번호만으로 로컬 정체를 확정할 수 없습니다.")

    # v0.7의 기본 파일명 중심 모드에서 확보할 수 있는 독립 대조 근거.
    # 정식 작품 제목이 다국어여서 이름이 달라도 곧바로 '충돌'이라 하지 않음.
    local_name_support: list[str] = []
    if len(candidates) == 1 and report.encryption_state == "clear":
        title_keys = compatible_title_keys(candidates[0], verified_aliases)
        archive_name_key = title_key(cleaned_search_title(report.archive_name))
        if archive_name_key and archive_name_key in title_keys:
            local_name_support.append("압축파일명 제목과 외부 후보 제목 일치")
        if report.inspection and report.inspection.state == "ok":
            local_titles = {
                title_key(_useful_title(name))
                for name in report.inspection.title_candidates
                if _useful_title(name)
            }
            if local_titles & title_keys:
                local_name_support.append("압축 내부 EXE·폴더 이름과 외부 후보 제목 일치")
        official_for_this_candidate = comparisons[0].official_ids if comparisons else ()
        declared = {
            f"dlsite_code:{v.upper()}" for v in hints.dlsite_codes
        } | {f"steam_app_id:{v}" for v in hints.steam_app_ids}
        if declared & set(official_for_this_candidate):
            local_name_support.append(
                "압축파일명에 적힌 작품번호가 외부 공식 상품번호와 일치함 "
                "(파일명 자체의 진위는 미검증)"
            )

    # 독립적인 파일 쓰기·DB 수정 기능은 제공하지 않음. matched도 사용자
    # 확인이 필요한 '근거 일치'라는 의미일 뿐 자동 연결 권한이 아니다.
    verified = VerificationReport(
        archive_name=report.archive_name,
        verdict=verdict,
        proposed_title=selected,
        candidate_titles=candidates,
        archive_kind=kind,
        package_assessment=package,
        localization_assessment=localized,
        encryption_state=report.encryption_state,
        inspection_state=index_state,
        metadata_state=meta_state,
        comparison=comparisons,
        evidence=records,
        matched_rules=tuple(dict.fromkeys(applied)),
        blockers=tuple(dict.fromkeys(blockers)),
        limitations=tuple(dict.fromkeys(limitations)),
        catalog_status=catalog_status,
        catalog_title=catalog_title,
        catalog_product_ids=catalog_ids,
        catalog_release_type=catalog_release_type,
        local_identity_status=verdict,
        local_name_support=tuple(local_name_support),
        candidate_relationships=candidate_relationships,
    )
    report.stage_timings_ms["verification_ms"] = round(
        (time.perf_counter() - verification_start) * 1000, 3,
    )
    return verified
