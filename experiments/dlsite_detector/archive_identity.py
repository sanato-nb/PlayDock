"""PlayDock 독립 게임 정체 조사: 이름 준비 → 암호 → 내부 목록/설정 → 통합 웹검색.

검색 성공 여부와 상관없이 비암호화 압축파일에서 가능한 단서를 *먼저*
전부 모은다. 검색은 모은 단서의 우선순위에 따라서 나중에 수행한다.
암호화된 압축파일은 기존 정책대로 파일명 검색만 수행한다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Callable
import time

from .archive_inspector import ArchiveInspection, inspect_archive
from .archive_encryption import probe_archive_encryption
from .catalog_aliases import group_external_attempts, representative
from .detector import normalized_title
from .enhanced_search import enhanced_classify_game
from .identity_hints import extract_hints
from .internal_metadata import (
    MetadataInspection, inspect_metadata, inspect_readme_metadata,
)
from .pipeline import SearchDecision
from .search_plan import build_search_plan


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
    # 단계 번호는 기존 호환을 위해 오름차순. 실제 시간순 실행은 execution_order.
    completed_steps: tuple[int, ...] = ()
    evidence_conflict: bool = False
    execution_order: tuple[int, ...] = ()
    stage_timings_ms: dict[str, float] = field(default_factory=dict)
    local_evidence_reused: bool = False

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
        result["external_status"] = next(
            (a.decision.status for a in self.attempts
             if a.decision.status in FOUND),
            self.attempts[0].decision.status if self.attempts else "",
        )
        result["search_errors"] = tuple(
            {"query": a.query, "reason": a.decision.reason[:300]}
            for a in self.attempts
            if any(term in a.decision.reason for term in (
                "검색 오류", "조회 실패", "RuntimeError", "TimeoutError",
                "ConnectionError", "HTTPError",
            ))
        )
        source = next((a.decision for a in reversed(self.attempts)
                       if a.decision.source_platform), None)
        result["source_platform"] = source.source_platform if source else ""
        result["source_id"] = source.source_id if source else ""
        result["source_url"] = source.source_url if source else ""
        return result


def _name_only_report(path: Path, first: SearchDecision,
                      attempts: tuple[IdentityAttempt, ...],
                      encryption_state: str, why: str,
                      timings: dict[str, float] | None = None) -> IdentityReport:
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
        path.name, status, 1 if status != "lookup_unavailable" else 2,
        first.proposed_title if status in {"confirmed_game", "candidate_found", "suspected_non_game"} else "",
        first.dlsite_code, why,
        None, attempts, None, encryption_state, (1, 2, 3),
        execution_order=(1, 3, 2), stage_timings_ms=timings or {},
    )


def identify_archive(
    archive_path: Path,
    *,
    classifier: Callable[[str], SearchDecision] = enhanced_classify_game,
    inspector: Callable[[Path], ArchiveInspection] = inspect_archive,
    allow_metadata: bool = False,
    metadata_reader: Callable[[Path], MetadataInspection] = inspect_readme_metadata,
    progress_callback: Callable[[int, str], None] | None = None,
    max_search_queries: int = 6,
) -> IdentityReport:
    """비암호화 파일: 1→3→4→5→2→6단계 순서로 근거를 수집해 돌려준다.

    1~5단계 보고서는 입력 파일을 수정하지 않는다. 전체 로컬 경로,
    README 원문, 압축파일 바이트는 인터넷으로 전송하지 않는다.
    각 검색 요청은 검색 계획기가 고른 짧은 제목/공식 식별자 문자열뿐이다.

    암호화 또는 암호화 여부 불명 파일: 1→3→2단계, 파일명 검색만 실행.
    """
    def notify(stage: int, label: str) -> None:
        if progress_callback is not None:
            try:
                progress_callback(stage, label)
            except Exception:
                # 화면의 상태 표시 기능 장애가 분석 결과를 바꾸면 안 된다.
                pass

    started = time.perf_counter()
    timings = {
        "archive_name_parse_ms": 0.0,
        "encryption_probe_ms": 0.0,
        "index_scan_ms": 0.0,
        "metadata_read_ms": 0.0,
        "search_plan_ms": 0.0,
        "search_ms": 0.0,
        "verification_ms": 0.0,
    }
    def stamp(key: str, since: float) -> None:
        timings[key] += round((time.perf_counter() - since) * 1000, 3)

    notify(1, "압축파일 이름에서 제목·작품 코드·번역 표기 수집")
    path = Path(archive_path)
    if path.suffix.casefold() not in ARCHIVE_EXTS or not path.is_file() or path.is_symlink():
        return IdentityReport(
            path.name, "invalid_archive", 0, "", "",
            "존재하는 일반 ZIP/7z/RAR 파일만 분석할 수 있습니다.", None,
            execution_order=(1,), stage_timings_ms=timings,
        )

    query = path.stem.strip()
    stamp("archive_name_parse_ms", started)
    notify(3, "암호화 여부 확인 중")
    probe_start = time.perf_counter()
    probe = probe_archive_encryption(path)
    stamp("encryption_probe_ms", probe_start)
    if probe.state != "clear":
        # 원본 압축 내부 경로에 접근하지 않으며 검색은 오직 파일명 한 번.
        notify(2, "암호 보호/확인 불가 파일: 파일명만 인터넷 검색 중")
        search_start = time.perf_counter()
        first = classifier(query)
        stamp("search_ms", search_start)
        attempt = (IdentityAttempt(1, "archive_filename", query, first),)
        why = ("암호화 파일은 내부를 읽지 않고 파일명만 검색합니다. "
               if probe.state == "encrypted" else
               "암호 상태를 확인할 수 없어 파일명만 검색합니다. ")
        why += ("파일명 검색 결과는 압축 내용과 대조하지 않았습니다."
                if first.status in FOUND | {"suspected_non_game"}
                else "작품을 조회하지 못했습니다.")
        base = _name_only_report(path, first, attempt, probe.state, why,
                                 timings=timings)
        if probe.state == "encrypted":
            return base
        unavailable = ArchiveInspection(
            path.name, path.suffix.lstrip("."), "unavailable", 0, 0, None,
            False, (), (), (), (), probe.reason,
        )
        return IdentityReport(
            base.archive_name, base.status, base.stage,
            base.proposed_title, base.product_code, base.reason,
            unavailable, attempt, None, probe.state, (1, 2, 3),
            execution_order=(1, 3, 2), stage_timings_ms=timings,
        )

    # 4단계: 실제 목록 검사. 검색은 아직 1회도 하지 않았다.
    notify(4, "압축파일 내부 전체 파일·폴더 목록 수집 중")
    # 같은 헤더의 암호화 상태를 반복 읽지 않도록 신뢰 가능한 검사 결과 전달.
    # 기존 사용자 정의 inspector 콜백 인터페이스는 변경하지 않음.
    index_start = time.perf_counter()
    inspection = (inspector(path, encryption_probe=probe)
                  if inspector is inspect_archive else inspector(path))
    stamp("index_scan_ms", index_start)
    if inspection.encrypted or inspection.state in {"encrypted", "needs_password"}:
        # 잘못된 암호 판정 이후에도 내부 단서를 누출하지 않는다.
        notify(2, "암호화가 확인되어 파일명만 검색 중")
        search_start = time.perf_counter()
        first = classifier(query)
        stamp("search_ms", search_start)
        return _name_only_report(
            path, first, (IdentityAttempt(1, "archive_filename", query, first),),
            "encrypted", "목록 검사 중 암호 보호를 확인하여 파일명만 검색했습니다.",
            timings=timings,
        )

    metadata = None
    actual_order = [1, 3, 4]
    if allow_metadata and inspection.state in {"ok", "partial", "limit_exceeded"}:
        notify(5, "README 제한 필드 수집 중 (기타 설정파일 내용 미조회)")
        metadata_start = time.perf_counter()
        metadata = (metadata_reader(path, encryption_probe=probe)
                    if metadata_reader in (inspect_metadata, inspect_readme_metadata)
                    else metadata_reader(path))
        stamp("metadata_read_ms", metadata_start)
        actual_order.append(5)

    # 모든 *안전하게 읽을 수 있는* 근거를 확보한 이후에만 검색한다.
    # 실패한 내부 목록은 추측으로 대체하지 않고 파일명만 검색한다.
    plan_start = time.perf_counter()
    plan = build_search_plan(
        path.name,
        inspection if inspection.state in {"ok", "partial", "limit_exceeded"} else None,
        metadata,
        max_queries=max(1, min(max_search_queries, 12)),
    )
    stamp("search_plan_ms", plan_start)
    search_start = time.perf_counter()
    notify(2, f"모은 근거 {len(plan)}개를 우선순위대로 인터넷 조회 중")
    actual_order.append(2)
    attempts: list[IdentityAttempt] = []
    non_game: IdentityAttempt | None = None
    for hint in plan:
        # 공식 작품 ID가 이미 확인됐으면 파일명/실행파일의 약한
        # 제목으로 다시 검색해 동일 작품 별칭을 중복 생성하지 않는다.
        # 단, 다른 명시적 작품 ID 및 내부 설정의 강한 제목은 계속 검사.
        if (any(a.decision.status in CONFIRMED and a.decision.dlsite_code
                for a in attempts)
                and hint.basis in {
                    "archive_filename_alias",
                    "internal_filename", "internal_metadata_supporting_title",
                }):
            continue
        notify(2, f"인터넷 조회 중: {hint.basis} ({len(attempts) + 1}/{len(plan)})")
        try:
            decision = classifier(hint.query)
        except Exception as exc:
            # 검색 장애와 실제 검색 결과 없음은 분리해 보고한다.
            decision = SearchDecision(
                "lookup_unavailable", hint.query,
                reason="인터넷 조회 실패: " + type(exc).__name__,
                web_checked=True,
            )
        attempt = IdentityAttempt(hint.stage, hint.basis, hint.query, decision)
        attempts.append(attempt)
        if decision.status == "suspected_non_game" and non_game is None:
            non_game = attempt
    stamp("search_ms", search_start)
    # 제목이 다른 판매처의 공식 병기/별칭이라도 동일 작품인 경우만 묶는다.
    # 다른 공식 상품 ID는 같은 작품명처럼 보여도 절대 자동 병합하지 않는다.
    candidate_groups = group_external_attempts(attempts)

    steps = (1, 2, 3, 4, 5) if metadata is not None else (1, 2, 3, 4)
    note = ""
    if inspection.state != "ok":
        note += f"내부 목록 분석 제한/실패({inspection.state}). "
    if metadata is None:
        note += "내부 메타데이터는 읽지 않았습니다. "
    elif metadata.state != "ok":
        note += f"메타데이터 판독 제한({metadata.state}). "
    error_count = sum(
        "검색 오류" in a.decision.reason or "조회 실패" in a.decision.reason
        for a in attempts
    )
    if error_count:
        note += f"인터넷 검색 오류/차단 {error_count}건: 단순 미검색과 구분해야 합니다. "
    note += "게임 정체의 최종 교차검증과 자동 연결은 별도 6단계에서 수행합니다."

    # 전 단계에서 검증된 작품명 후보가 2종류 이상 나온 경우 보류.
    # 일반적인 내부 프로젝트명 차이는 6단계에서 판단한다.
    if len(candidate_groups) > 1:
        return IdentityReport(
            path.name, "ambiguous", 2, "", "",
            "독립된 외부 검색에서 서로 다른 작품 후보가 발견됐습니다. " + note,
            inspection, tuple(attempts), metadata, "clear", steps,
            evidence_conflict=True, execution_order=tuple(actual_order),
            stage_timings_ms=timings,
        )
    if candidate_groups:
        selected = representative(candidate_groups[0])
        return IdentityReport(
            path.name, "candidate_found", selected.stage,
            selected.decision.proposed_title,
            selected.decision.dlsite_code,
            "내부 목록·설정·파일명을 모아 검색한 작품 후보입니다. "
            "압축파일과 동일 작품인지 미확정입니다. " + note,
            inspection, tuple(attempts), metadata, "clear", steps,
            execution_order=tuple(actual_order),
            stage_timings_ms=timings,
        )
    if non_game is not None:
        return IdentityReport(
            path.name, "suspected_non_game", non_game.stage,
            non_game.decision.proposed_title, non_game.decision.dlsite_code,
            "웹 등록 유형은 비게임 추정이지만 로컬 배포물 내용은 미검증입니다. " + note,
            inspection, tuple(attempts), metadata, "clear", steps,
            execution_order=tuple(actual_order),
            stage_timings_ms=timings,
        )
    return IdentityReport(
        path.name, "lookup_unavailable", 3 if metadata is not None else 2, "", "",
        "모은 내부 근거와 파일명으로 검색했으나 작품을 확인하지 못했습니다. "
        + note, inspection, tuple(attempts), metadata, "clear", steps,
        execution_order=tuple(actual_order), stage_timings_ms=timings,
    )



def search_recheck_needed(report: IdentityReport) -> bool:
    """이전에 검색하지 못했거나 공식 번호 재확인이 남은 항목만 재검사."""
    for attempt in report.attempts:
        item = attempt.decision
        if item.search_state in {"network_error", "cooldown_skipped"}:
            return True
        if item.web_code_hints and not item.official_code_verified:
            return True
        if item.status == "lookup_unavailable" and any(
            token in item.reason for token in ("검색 오류", "조회 실패", "연속 장애")
        ):
            return True
    return False


def recheck_archive_search(
    archive_path: Path,
    previous: IdentityReport,
    *,
    classifier: Callable[[str], SearchDecision],
    expected_stat: tuple[int, int] | None = None,
    progress_callback: Callable[[int, str], None] | None = None,
    max_search_queries: int = 6,
    metadata_reader: Callable[[Path], MetadataInspection] = inspect_readme_metadata,
) -> IdentityReport:
    """검색 오류 파일의 재조사: 안전한 파일 상태 확인 뒤 로컬 근거를 재사용.

    이전 검색 성공/정상 미발견은 재요청하지 않고 실패·생략·미확인
    작품번호만 다시 조회한다. 원본 파일의 크기/mtime이 달라졌거나
    캐시가 없으면 내부를 정상 재검사한다. 자동 파일 수정 없음.
    """
    path = Path(archive_path)
    if not path.is_file() or path.is_symlink() or path.name != previous.archive_name:
        raise ValueError("재검사 원본 파일이 없거나 기존 압축파일과 다릅니다.")
    st = path.stat()
    signature = (st.st_size, st.st_mtime_ns)
    reuse = (
        expected_stat is not None and signature == expected_stat
        and previous.encryption_state == "clear"
        and previous.inspection is not None
    )
    if not reuse:
        return identify_archive(
            path, classifier=classifier, allow_metadata=True,
            metadata_reader=metadata_reader,
            max_search_queries=max_search_queries, progress_callback=progress_callback,
        )

    stable: dict[str, SearchDecision] = {
        attempt.query: attempt.decision
        for attempt in previous.attempts
        if not (
            attempt.decision.search_state in {"network_error", "cooldown_skipped"}
            or attempt.decision.web_code_hints
               and not attempt.decision.official_code_verified
            or attempt.decision.status == "lookup_unavailable" and any(
                word in attempt.decision.reason
                for word in ("검색 오류", "조회 실패", "연속 장애")
            )
        )
    }

    def retry_only(query: str) -> SearchDecision:
        cached = stable.get(query)
        return cached if cached is not None else classifier(query)

    result = identify_archive(
        path,
        classifier=retry_only,
        inspector=lambda _: previous.inspection,
        allow_metadata=previous.metadata is not None,
        metadata_reader=lambda _: previous.metadata,
        max_search_queries=max_search_queries,
        progress_callback=progress_callback,
    )
    return replace(result, local_evidence_reused=True)
