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
from .pipeline import SearchDecision, classify_game

CONFIRMED = frozenset({"confirmed_game", "internet_confirmed_game"})
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

    @property
    def label(self) -> str:
        return {
            "confirmed_game": "게임 정체 확인 · 압축파일명",
            "suspected_non_game": "비게임으로 추정 · 별도 분류",
            "candidate_found": "게임 정체 후보 발견 · 수동 확인 필요",
            "ambiguous": "여러 게임 정체 후보 · 수동 확인 필요",
            "lookup_unavailable": "정체 조회 불가 · 별도 보관",
            "invalid_archive": "지원하지 않거나 읽을 수 없는 압축파일",
        }[self.status]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["label"] = self.label
        return data


def identify_archive(
    archive_path: Path,
    *,
    classifier: Callable[[str], SearchDecision] = classify_game,
    inspector: Callable[[Path], ArchiveInspection] = inspect_archive,
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
        if outcome.status in CONFIRMED and outcome.proposed_title.strip():
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
    return IdentityReport(
        path.name, "lookup_unavailable", 2, "", "",
        "압축파일명과 내부 파일 목록을 이용한 재검색에서도 동일 게임을 확인하지 못했습니다.",
        inspection, tuple(attempts),
    )
