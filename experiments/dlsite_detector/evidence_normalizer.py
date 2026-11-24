"""6-A: 서로 다른 출처의 근거를 손실 없이 표준화한다.

신뢰 등급은 근거 필드의 출처 성격이지 실제 게임이 진품일 확률이 아니다.
검색결과와 압축파일명, 압축 내부 설정/파일 목록을 서로 다른 출처로 기록한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from .archive_identity import IdentityReport
from .identity_hints import extract_hints


@dataclass(frozen=True)
class EvidenceRecord:
    kind: str  # title, dlsite_code, steam_app_id, package, localization, engine, publisher, project_name
    value: str
    origin: str  # official, web_candidate, filename, internal_metadata, internal_index
    strength: str  # official, strong, supporting, weak
    member: str = ""
    field: str = ""
    parser: str = ""
    independence_group: str = ""


def _metadata_group(member: str) -> str:
    """여러 설정이 같은 루트 게임을 가리킬 수 있으므로 서로 독립이라고 단정하지 않는다."""
    parts = PurePosixPath(member.replace("\\", "/")).parts
    if len(parts) <= 1:
        return "archive_root"
    if parts[0].casefold() in {"game", "data", "www", "assets", "files"}:
        return "archive_root"
    return parts[0].casefold()


def normalize_evidence(report: IdentityReport) -> tuple[EvidenceRecord, ...]:
    evidence: list[EvidenceRecord] = []
    hints = extract_hints(report.archive_name)

    # 이름 자체에 적힌 코드/표기는 절대 독립적인 공식 작품 증거가 아님.
    for code in hints.dlsite_codes:
        evidence.append(EvidenceRecord("dlsite_code", code, "filename", "weak",
                                       field="archive_name", independence_group="filename"))
    for appid in hints.steam_app_ids:
        evidence.append(EvidenceRecord("steam_app_id", appid, "filename", "weak",
                                       field="archive_name", independence_group="filename"))

    for idx, attempt in enumerate(report.attempts):
        decision = attempt.decision
        if not decision.proposed_title.strip():
            continue
        official = decision.status in {
            "confirmed_game", "platform_confirmed_game"
        } or decision.official_code_verified
        # 인터넷 검색만으로 찾은 '공식 사이트 추정'은 공식 API 검증과 동일시하지 않음.
        evidence.append(EvidenceRecord(
            "title", decision.proposed_title.strip(),
            "official" if official else "web_candidate",
            "official" if official else "supporting",
            field=attempt.basis, parser=decision.source_platform or "external_search",
            independence_group=f"external:{idx}",
        ))
        if official and (decision.status == "confirmed_game"
                         or decision.official_code_verified) and decision.dlsite_code:
            evidence.append(EvidenceRecord(
                "dlsite_code", decision.dlsite_code.upper(), "official", "official",
                field="dlsite_code", parser="dlsite",
                independence_group=f"external:{idx}",
            ))
        if (official and decision.source_platform in {"steam", "dlsite+steam"}
                and decision.source_id.isascii() and decision.source_id.isdecimal()):
            evidence.append(EvidenceRecord(
                "steam_app_id", decision.source_id, "official", "official",
                field="source_id", parser="steam",
                independence_group=f"external:{idx}",
            ))

    # 웹 페이지의 코드 힌트는 공식 조회 성공 여부와 무관하게 약한 근거.
    for attempt in report.attempts:
        for code in attempt.decision.web_code_hints:
            evidence.append(EvidenceRecord(
                "dlsite_code", code, "web_candidate", "weak",
                field="web_code_hints", parser="web_search",
                independence_group="web_code_hints",
            ))

    # 암호화 파일의 어떤 내부 근거도 받아들이지 않는다. 가짜 보고서에
    # inspection/metadata가 있어도 암호 상태를 최우선으로 검사한다.
    if report.encryption_state != "clear":
        return tuple(evidence)

    if report.metadata is not None:
        for item in report.metadata.evidence:
            if item.kind not in {
                "title", "product_code", "steam_app_id", "publisher", "project_name"
            }:
                continue
            kind = "dlsite_code" if item.kind == "product_code" else item.kind
            evidence.append(EvidenceRecord(
                kind, item.candidate_title, "internal_metadata", item.strength,
                member=item.member, field=item.field, parser=item.parser,
                independence_group=_metadata_group(item.member),
            ))

    if report.inspection is not None:
        inspection = report.inspection
        for signal in inspection.package_signals:
            evidence.append(EvidenceRecord(
                "package", signal, "internal_index", "supporting",
                field="package_signals", independence_group="file_layout",
            ))
        for signal in inspection.localization_signals:
            evidence.append(EvidenceRecord(
                "localization", signal, "internal_index", "supporting",
                field="localization_signals", independence_group="file_layout",
            ))
        for hint in inspection.engine_hints:
            evidence.append(EvidenceRecord(
                "engine", hint, "internal_index", "supporting",
                field="engine_hints", independence_group="file_layout",
            ))
        # 내부 목록의 경로에 존재하는 작품 코드 문자열은 직접 선언한
        # 작품 식별자가 아니라 약한 검색 힌트다.
        for code in inspection.product_codes:
            evidence.append(EvidenceRecord(
                "dlsite_code", code, "internal_index", "weak",
                field="product_codes", independence_group="file_layout",
            ))
        for value in inspection.title_candidates:
            evidence.append(EvidenceRecord(
                "title", value, "internal_index", "weak",
                field="title_candidates", independence_group="file_layout",
            ))

    return tuple(evidence)
