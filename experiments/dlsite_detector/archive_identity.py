"""압축파일 1개로 정체를 조사하는 독립 2단계 프로그램.

1단계: 압축파일 '이름'으로 DLsite→일반 웹 검색.
2단계: 미확인일 때만 압축 안의 파일 목록을 읽어 새 후보명/품번으로 재검색.

파일 목록 단서는 로컬 게임과 작품의 동일성을 증명하지 않으므로 2단계
결과를 자동 확정하지 않는다. 본체 UI/DB/게임 파일을 변경하지 않는다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from .archive_inspector import ArchiveInspection, inspect_archive
from .detector import normalized_title
from .pipeline import SearchDecision
from .enhanced_search import enhanced_classify_game
from .identity_hints import extract_hints
from .internal_metadata import MetadataInspection, inspect_metadata
from .archive_encryption import probe_archive_encryption

CONFIRMED = frozenset({"confirmed_game", "internet_confirmed_game", "platform_confirmed_game"})
CANDIDATES = frozenset({"internet_candidate"})
ARCHIVE_EXTS = frozenset({".zip", ".7z", ".rar"})
MAX_TITLE_QUERIES = 4
MAX_CODE_QUERIES = 2


@dataclass(frozen=True)
class IdentityAttempt:
    stage: int
    basis: str
    query: str
    decision: SearchDecision


@dataclass(frozen=True)
class IdentityReport:
    archive_name: str
    status: str
    stage: int
    proposed_title: str
    product_code: str
    reason: str
    inspection: ArchiveInspection | None
    attempts: tuple[IdentityAttempt, ...] = ()
    metadata: MetadataInspection | None = None

    @property
    def label(self) -> str:
        return {
            "confirmed_game": "게임 정체 확인 · 압축파일명",
            "suspected_non_game": "비게임으로 추정 · 별도 분류",
            "candidate_found": "게임 정체 후보 발견 · 수동 확인 필요",
            "ambiguous": "여러 게임 정체 후보 · 수동 확인 필요",
            "lookup_unavailable": "정체 조회 불가 · 별도 보관",
            "invalid_archive": "지원하지 않거나 읽을 수 없는 압축파일",
            "unclassifiable": "분류 불가 · 암호화된 압축파일",
        }[self.status]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["label"] = self.label
        data["archive_kind"] = extract_hints(self.archive_name).archive_kind
        source = next((x.decision for x in reversed(self.attempts)
                       if x.decision.source_platform), None)
        data["source_platform"] = source.source_platform if source else ""
        data["source_id"] = source.source_id if source else ""
        data["source_url"] = source.source_url if source else ""
        return data


def identify_archive(
    archive_path: Path,
    *,
    classifier: Callable[[str], SearchDecision] = enhanced_classify_game,
    inspector: Callable[[Path], ArchiveInspection] = inspect_archive,
    allow_metadata: bool = False,
    metadata_reader: Callable[[Path], MetadataInspection] = inspect_metadata,
) -> IdentityReport:
    """압축파일 1개를 검사. 외부 요청은 주입된 classifier만 수행.

    검색 실패 시에만 목록을 읽으며 멤버 내용은 열거나 실행하지 않는다.
    내부 파일에서 나온 제목·코드는 사용자 검토 전에는 '후보'로만 처리한다.
    """
    path = Path(archive_path)
    if path.suffix.casefold() not in ARCHIVE_EXTS or not path.is_file() or path.is_symlink():
        return IdentityReport(path.name, "invalid_archive", 0, "", "",
                              "존재하는 일반 ZIP/7z/RAR 파일만 분석할 수 있습니다.", None)

    attempts: list[IdentityAttempt] = []
    # 검색어는 로컬 파일 전체 경로가 아니라 확장자를 제외한 파일명만 사용.
    first_query = path.stem.strip()
    first = classifier(first_query)
    attempts.append(IdentityAttempt(1, "archive_filename", first_query, first))
    if first.status in CONFIRMED:
        return IdentityReport(path.name, "confirmed_game", 1,
                              first.proposed_title, first.dlsite_code,
                              "압축파일 이름으로 외부 작품 정보를 확인했습니다.", None, tuple(attempts))
    if first.status == "suspected_non_game":
        return IdentityReport(path.name, "suspected_non_game", 1,
                              first.proposed_title, first.dlsite_code,
                              "DLsite 작품 유형에 따라 비게임으로 추정합니다.", None, tuple(attempts))
    if first.status in CANDIDATES:
        if allow_metadata:
            probe = probe_archive_encryption(path)
            if probe.state != "clear":
                return IdentityReport(
                    path.name, "candidate_found", 1,
                    first.proposed_title, first.dlsite_code,
                    "파일명으로 작품 후보는 찾았지만 내부 정보는 사용하지 않았습니다. "
                    + probe.reason, None, tuple(attempts),
                )
            # 사용자가 내용 검사를 명시한 경우에는 1차 웹 후보도 내부 단서와
            # 교차 확인한다. 상충된 제목은 자동 통합하지 않는다.
            inspection = inspector(path)
            metadata = metadata_reader(path)
            candidate_key = normalized_title(first.proposed_title)
            internal_keys = {normalized_title(t) for t in metadata.title_candidates}
            differs = bool(candidate_key and internal_keys and
                           candidate_key not in internal_keys)
            return IdentityReport(
                path.name, "ambiguous" if differs else "candidate_found", 3,
                "" if differs else first.proposed_title, first.dlsite_code,
                ("웹 검색 후보와 내부 제목 메타데이터가 달라 수동 검토가 필요합니다."
                 if differs else "웹 검색 후보를 유지하며 내부 이름 단서도 확인했습니다. "
                 "동일 게임 여부는 확정하지 않았습니다."),
                inspection, tuple(attempts), metadata,
            )
        return IdentityReport(path.name, "candidate_found", 1,
                              first.proposed_title, first.dlsite_code,
                              "압축파일명 검색에서 게임 작품 후보를 찾았습니다. "
                              "검색 결과만으로 동일 작품인지 확정하지 않고 사용자 확인을 기다립니다.",
                              None, tuple(attempts))

    # 1차 검색 실패 후에는 암호 상태만 먼저 확인한다. 암호화된 아카이브는
    # 설령 멤버명 목록이 노출돼도 단서 수집 및 2·3차 검색을 하지 않는다.
    probe = probe_archive_encryption(path)
    if probe.is_encrypted:
        return IdentityReport(
            path.name, "unclassifiable", 1, "", "",
            "암호화된 압축파일은 파일명으로만 검색합니다. "
            "파일명 검색으로 확인하지 못해 분류 불가로 남겼습니다.",
            None, tuple(attempts),
        )
    if probe.state != "clear":
        return IdentityReport(
            path.name, "lookup_unavailable", 2, "", "",
            "암호화 여부를 확인할 수 없어 내부 분석을 생략했습니다. " + probe.reason,
            ArchiveInspection(
                path.name, path.suffix.lstrip("."), "unavailable",
                0, 0, None, False, (), (), (), (), probe.reason,
            ), tuple(attempts),
        )

    inspection = inspector(path)
    if inspection.state not in {"ok", "partial", "limit_exceeded"}:
        return IdentityReport(path.name, "lookup_unavailable", 2, "", "",
                              f"1차 검색이 실패했고 내부 목록도 확인할 수 없습니다: {inspection.reason}",
                              inspection, tuple(attempts))

    seen = {normalized_title(first_query)}
    verified: dict[str, list[IdentityAttempt]] = {}
    # EXE 이름 → 최상위 폴더 이름 순서. 이름 없는 코드 재검색은 후순위.
    suggestions = [
        ("internal_filename", candidate)
        for candidate in inspection.title_candidates[:MAX_TITLE_QUERIES]
    ] + [
        ("internal_product_code", code)
        for code in inspection.product_codes[:MAX_CODE_QUERIES]
    ]
    for basis, query in suggestions:
        normalized = normalized_title(query)
        # 같은 검색어를 반복하지 않고, 숫자/코드만 있을 땐 품번 기준으로 중복 방지.
        key = normalized or query.casefold()
        if key in seen:
            continue
        seen.add(key)
        outcome = classifier(query)
        attempt = IdentityAttempt(2, basis, query, outcome)
        attempts.append(attempt)
        if outcome.status in CONFIRMED | CANDIDATES and outcome.proposed_title.strip():
            title_key = normalized_title(outcome.proposed_title)
            if title_key:
                verified.setdefault(title_key, []).append(attempt)

    if len(verified) == 1:
        best = next(iter(verified.values()))[0]
        return IdentityReport(
            path.name, "candidate_found", 2,
            best.decision.proposed_title, best.decision.dlsite_code,
            "내부 파일 목록의 단서로 외부 게임 작품을 찾았습니다. "
            "해당 압축파일이 같은 게임인지 수동 확인 후 적용해야 합니다.",
            inspection, tuple(attempts),
        )
    if len(verified) > 1:
        return IdentityReport(
            path.name, "ambiguous", 2, "", "",
            "내부 파일 단서로 서로 다른 작품이 발견되어 자동 선택하지 않았습니다.",
            inspection, tuple(attempts),
        )
    # 이 단계까지 작품이 발견되지 않았을 때만 사용자가 허용한 소형 메타데이터를 확인.
    # 원문 전체나 파일 경로는 웹에 전달하지 않고, 제목 필드에서 얻은 후보만 사용.
    if allow_metadata:
        metadata = metadata_reader(path)
        if metadata.state == "ok":
            suggestions = [
                ("internal_metadata_title", candidate)
                for candidate in metadata.title_candidates[:3]
            ] + [
                ("internal_metadata_code", code)
                for code in metadata.product_codes[:2]
            ]
            for basis, query in suggestions:
                key = normalized_title(query) or query.casefold()
                if not key or key in seen:
                    continue
                seen.add(key)
                outcome = classifier(query)
                attempt = IdentityAttempt(3, basis, query, outcome)
                attempts.append(attempt)
                if outcome.status in CONFIRMED | CANDIDATES and outcome.proposed_title.strip():
                    title_key = normalized_title(outcome.proposed_title)
                    if title_key:
                        verified.setdefault(title_key, []).append(attempt)

            if len(verified) == 1:
                best = next(iter(verified.values()))[0]
                return IdentityReport(
                    path.name, "candidate_found", 3,
                    best.decision.proposed_title, best.decision.dlsite_code,
                    "내부 README·설정파일 제목 단서로 작품 후보를 찾았습니다. "
                    "압축파일과 같은 게임인지는 아직 확정하지 않았습니다.",
                    inspection, tuple(attempts), metadata,
                )
            if len(verified) > 1:
                return IdentityReport(
                    path.name, "ambiguous", 3, "", "",
                    "내부 메타데이터에서 서로 다른 게임 후보를 찾아 수동 선택이 필요합니다.",
                    inspection, tuple(attempts), metadata,
                )
        return IdentityReport(
            path.name, "lookup_unavailable", 3, "", "",
            "파일명·내부 목록·제한된 메타데이터로도 게임 정체를 확인하지 못했습니다. "
            + metadata.reason,
            inspection, tuple(attempts), metadata,
        )
    return IdentityReport(
        path.name, "lookup_unavailable", 2, "", "",
        "압축파일명과 내부 파일 목록을 이용한 재검색에서도 동일 게임을 확인하지 못했습니다.",
        inspection, tuple(attempts),
    )
