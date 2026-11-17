"""PlayDock 독립 게임 정체 조사: 파일명 → 웹 → 암호 확인 → 전체 목록 → 소형 메타데이터.

5단계까지는 근거 수집이 목적이다. 인터넷에서 작품명이 확인되어도 로컬
압축파일이 그 게임이라고 확정하지 않는다. 최종 근거 대조·자동 변경은
이 모듈의 범위가 아니다. 암호화된 압축파일은 이름 검색만 수행한다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from .archive_inspector import ArchiveInspection, inspect_archive
from .archive_encryption import probe_archive_encryption
from .detector import normalized_title
from .enhanced_search import enhanced_classify_game
from .identity_hints import extract_hints
from .internal_metadata import MetadataInspection, inspect_metadata
from .pipeline import SearchDecision


CONFIRMED = frozenset({"confirmed_game", "internet_confirmed_game", "platform_confirmed_game"})
CANDIDATES = frozenset({"internet_candidate"})
FOUND = CONFIRMED | CANDIDATES
ARCHIVE_EXTS = frozenset({".zip", ".7z", ".rar"})
MAX_TITLE_QUERIES = 4
MAX_CODE_QUERIES = 2
MAX_METADATA_TITLE_QUERIES = 3
MAX_METADATA_CODE_QUERIES = 2


@dataclass(frozen=True)
class IdentityAttempt:
    # 기존 호환: 1=파일명 검색, 2=내부 목록으로 재검색, 3=메타데이터로 재검색.
    stage: int
    basis: str
    query: str
    decision: SearchDecision


@dataclass(frozen=True)
class IdentityReport:
    archive_name: str
    status: str
    stage: int  # 최종 후보의 출처 단계 (실제 처리 진행 단계와 다름)
    proposed_title: str
    product_code: str
    reason: str
    inspection: ArchiveInspection | None
    attempts: tuple[IdentityAttempt, ...] = ()
    metadata: MetadataInspection | None = None
    encryption_state: str = "not_checked"
    # 실제 수행한 1~5단계. 1 파일명, 2 인터넷, 3 암호 확인,
    # 4 내부 목록, 5 선택적 메타데이터.
    completed_steps: tuple[int, ...] = ()
    evidence_conflict: bool = False

    @property
    def label(self) -> str:
        return {
            "confirmed_game": "외부 작품 확인 · 압축 내용 미검증",
            "suspected_non_game": "외부 비게임 추정 · 별도 검토",
            "candidate_found": "게임 후보 · 압축파일 동일성 검토 필요",
            "ambiguous": "외부 후보와 내부 근거 충돌 · 수동 검토",
            "lookup_unavailable": "정체 조회 불가 · 별도 보관",
            "invalid_archive": "지원하지 않거나 읽을 수 없는 압축파일",
            "unclassifiable": "분류 불가 · 암호화된 압축파일",
        }[self.status]

    def to_dict(self) -> dict:
        result = asdict(self)
        result["label"] = self.label
        result["archive_kind"] = extract_hints(self.archive_name).archive_kind
        result["inspection_complete"] = bool(
            self.inspection and self.inspection.state == "ok"
        )
        result["external_status"] = (self.attempts[0].decision.status
                                     if self.attempts else "")
        source = next((a.decision for a in reversed(self.attempts)
                       if a.decision.source_platform), None)
        result["source_platform"] = source.source_platform if source else ""
        result["source_id"] = source.source_id if source else ""
        result["source_url"] = source.source_url if source else ""
        return result


def _name_only_report(path: Path, first: SearchDecision,
                      attempts: tuple[IdentityAttempt, ...],
                      encryption_state: str, why: str) -> IdentityReport:
    """암호 보호 또는 상태 불명 파일에서 내부 단서를 전혀 사용하지 않는다."""
    if first.status in CONFIRMED:
        status = "confirmed_game"
    elif first.status == "suspected_non_game":
        status = "suspected_non_game"
    elif first.status in CANDIDATES:
        status = "candidate_found"
    elif encryption_state == "encrypted":
        status = "unclassifiable"
    else:
        status = "lookup_unavailable"
    return IdentityReport(
        path.name, status, 1,
        first.proposed_title if status in {"confirmed_game", "candidate_found", "suspected_non_game"} else "",
        first.dlsite_code, why,
        None, attempts, None, encryption_state, (1, 2, 3),
    )


def identify_archive(
    archive_path: Path,
    *,
    classifier: Callable[[str], SearchDecision] = enhanced_classify_game,
    inspector: Callable[[Path], ArchiveInspection] = inspect_archive,
    allow_metadata: bool = False,
    metadata_reader: Callable[[Path], MetadataInspection] = inspect_metadata,
) -> IdentityReport:
    """1~5단계 수집. allow_metadata=True면 필요한 소형 메타데이터도 확인한다.

    외부 검색은 압축파일명/정제된 내부 *제목 후보*와 품번만 전송한다.
    전체 로컬 경로·README 원문·압축파일 데이터는 웹으로 전송하지 않는다.
    UI·본체 DB·원본 파일 내용과 파일명은 변경하지 않는다.
    """
    path = Path(archive_path)
    if path.suffix.casefold() not in ARCHIVE_EXTS or not path.is_file() or path.is_symlink():
        return IdentityReport(path.name, "invalid_archive", 0, "", "",
                              "존재하는 일반 ZIP/7z/RAR 파일만 분석할 수 있습니다.", None)

    query = path.stem.strip()
    first = classifier(query)  # 1단계 이름 전처리 + 2단계 외부 검색
    attempts: list[IdentityAttempt] = [
        IdentityAttempt(1, "archive_filename", query, first),
    ]

    # 3단계: 외부 검색 성공 여부와 관계없이 암호 상태를 먼저 확인한다.
    probe = probe_archive_encryption(path)
    if probe.state == "encrypted":
        return _name_only_report(
            path, first, tuple(attempts), probe.state,
            "암호화된 압축파일은 파일명만 검색합니다. " +
            ("작품 후보는 압축파일 내부와 대조하지 않았습니다."
             if first.status in FOUND | {"suspected_non_game"}
             else "파일명 검색으로 정체를 찾지 못해 분류 불가입니다."),
        )
    if probe.state != "clear":
        report = _name_only_report(
            path, first, tuple(attempts), probe.state,
            "암호화 여부를 확인할 수 없어 내부 파일을 읽지 않았습니다. " + probe.reason,
        )
        # 이름 기반 외부 확인은 유지하되 내부 검사를 시도하지 않은 상태 표시.
        unavailable = ArchiveInspection(
            path.name, path.suffix.lstrip("."), "unavailable", 0, 0, None,
            False, (), (), (), (), probe.reason,
        )
        return IdentityReport(
            path.name, report.status, 1 if report.status != "lookup_unavailable" else 2,
            report.proposed_title, report.product_code, report.reason,
            unavailable, report.attempts, None, probe.state, (1, 2, 3),
        )

    # 4단계: 이름 검색이 성공한 게임도 내부 목록 전체를 검사한다.
    # 압축해제하지 않으며 inspector가 최대 항목 수 제한을 관리한다.
    inspection = inspector(path)
    steps = (1, 2, 3, 4)
    if inspection.state not in {"ok", "partial", "limit_exceeded"}:
        # 검사 중 암호 상태가 바뀌거나 다른 형식에서 암호가 발견된 경우도 중단.
        if inspection.encrypted or inspection.state in {"encrypted", "needs_password"}:
            return _name_only_report(
                path, first, tuple(attempts), "encrypted",
                "암호화 확인 후 내부 단서 사용을 중단했습니다. " + inspection.reason,
            )
        name_report = _name_only_report(
            path, first, tuple(attempts), "unknown",
            "내부 목록 분석 실패. 파일명 검색 결과만 보관합니다. " + inspection.reason,
        )
        return IdentityReport(
            name_report.archive_name, name_report.status, name_report.stage,
            name_report.proposed_title, name_report.product_code, name_report.reason,
            inspection, name_report.attempts, None, "unknown", steps,
        )

    candidates: dict[str, IdentityAttempt] = {}
    first_title = first.proposed_title.strip()
    if first.status in FOUND and first_title:
        key = normalized_title(first_title)
        if key:
            candidates[key] = attempts[0]

    seen = {normalized_title(query) or query.casefold().strip()}

    def search_hints(stage: int, hints: list[tuple[str, str]]) -> None:
        for basis, title in hints:
            key = normalized_title(title) or title.casefold().strip()
            if not key or key in seen:
                continue
            seen.add(key)
            decision = classifier(title)
            attempt = IdentityAttempt(stage, basis, title, decision)
            attempts.append(attempt)
            if decision.status in FOUND and decision.proposed_title.strip():
                title_key = normalized_title(decision.proposed_title)
                if title_key and title_key not in candidates:
                    candidates[title_key] = attempt

    # 외부 이름으로 작품을 이미 확인한 경우에는 불필요한 내부 이름별
    # 인터넷 재검색을 하지 않고 증거를 저장한다. 불확실한 경우에만 재검색.
    if first.status not in FOUND | {"suspected_non_game"}:
        index_hints = (
            [("internal_filename", v) for v in inspection.title_candidates[:MAX_TITLE_QUERIES]]
            + [("internal_product_code", v) for v in inspection.product_codes[:MAX_CODE_QUERIES]]
        )
        search_hints(2, index_hints)

    # 5단계: ZIP/RAR 및 안전한 비솔리드 7z의 제한된 설정 메타데이터.
    # 검색 성공이어도 사용자 요청 시 메타데이터를 확인해 추후
    # 최종 검증에 쓸 수 있게 수집한다.
    metadata = None
    if allow_metadata:
        metadata = metadata_reader(path)
        steps = (1, 2, 3, 4, 5)
        if metadata.state == "ok" and first.status not in FOUND | {"suspected_non_game"}:
            meta_hints = (
                [("internal_metadata_title", v)
                 for v in metadata.title_candidates[:MAX_METADATA_TITLE_QUERIES]]
                + [("internal_metadata_code", v)
                   for v in metadata.product_codes[:MAX_METADATA_CODE_QUERIES]]
            )
            search_hints(3, meta_hints)

    # 6단계의 최종 동일성 확인은 아직 수행하지 않는다. 명시적 설정파일
    # 제목이 외부 작품명과 충돌할 때만 안전하게 '보류'로 표시한다.
    conflicts = bool(
        first.status in FOUND and first_title and metadata
        and metadata.title_candidates
        and normalized_title(first_title) not in {
            normalized_title(v) for v in metadata.title_candidates
        }
    )
    note = ("내부 목록 분석이 항목 수 제한으로 중단됐으므로 전체 목록은 미검사입니다. "
            if inspection.state == "limit_exceeded" else
            "내부 목록은 확인했지만 일부 경로를 제외했습니다. "
            if inspection.state == "partial" else "")
    note += ("선택적 메타데이터도 확인했습니다. " if metadata else
             "작은 파일 내용은 읽지 않았습니다. ")
    note += "게임 정체의 최종 교차검증과 자동 연결은 아직 수행하지 않았습니다."

    if conflicts or len(candidates) > 1:
        return IdentityReport(
            path.name, "ambiguous", 3 if conflicts else 2, "", "",
            "외부 작품 후보와 내부 설정의 게임명이 다르거나 여러 작품 후보가 있습니다. "
            + note, inspection, tuple(attempts), metadata,
            "clear", steps, True,
        )
    if candidates:
        selected = next(iter(candidates.values()))
        return IdentityReport(
            path.name, "candidate_found", selected.stage,
            selected.decision.proposed_title, selected.decision.dlsite_code,
            "작품 후보를 찾았지만 압축파일의 동일 게임 여부는 미확정입니다. "
            "수동 확인이 필요합니다. " + note, inspection, tuple(attempts), metadata, "clear", steps,
        )
    if first.status == "suspected_non_game":
        return IdentityReport(
            path.name, "suspected_non_game", 1,
            first.proposed_title, first.dlsite_code,
            "DLsite 작품 유형은 비게임으로 추정되지만 로컬 압축파일의 실체는 미확인입니다. "
            + note, inspection, tuple(attempts), metadata, "clear", steps,
        )
    return IdentityReport(
        path.name, "lookup_unavailable", 3 if metadata else 2, "", "",
        "파일명과 내부 목록·제한된 메타데이터로 작품을 찾지 못했습니다. "
        + note, inspection, tuple(attempts), metadata, "clear", steps,
    )
