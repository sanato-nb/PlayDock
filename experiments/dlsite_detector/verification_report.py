"""6-E: 게임 정체 검증 결과는 수정 가능한 사용자 DB와 분리된 불변 보고서다."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .evidence_normalizer import EvidenceRecord
from .identity_matcher import CandidateComparison


VERDICT_LABELS = {
    "matched": "일치 확인 (근거 기준·진위 미보증)",
    "likely_candidate": "유력 후보",
    "needs_review": "확인 필요",
    "conflict": "근거 충돌",
    "unclassifiable": "분류 불가",
}


@dataclass(frozen=True)
class VerificationReport:
    archive_name: str
    verdict: str
    proposed_title: str
    candidate_titles: tuple[str, ...]
    archive_kind: str
    package_assessment: str
    localization_assessment: str
    encryption_state: str
    inspection_state: str
    metadata_state: str
    comparison: tuple[CandidateComparison, ...]
    evidence: tuple[EvidenceRecord, ...]
    matched_rules: tuple[str, ...]
    blockers: tuple[str, ...]
    limitations: tuple[str, ...]
    requires_manual_review: bool = True
    automatic_binding_allowed: bool = False

    @property
    def label(self) -> str:
        return VERDICT_LABELS[self.verdict]

    def to_dict(self) -> dict:
        result = asdict(self)
        result["label"] = self.label
        # 별도 확인 없이 원본 압축파일/PlayDock 표시 이름/DB를 수정하는 기능은 없음.
        result["read_only"] = True
        return result
