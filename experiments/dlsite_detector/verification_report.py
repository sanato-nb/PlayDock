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
    # 작품 카탈로그에서 제목/등록번호를 찾는 일과 로컬 파일이 그 작품인지
    # 증명하는 일은 서로 다른 질문이다. 아래 상태를 독립적으로 기록한다.
    catalog_status: str = "not_checked"
    catalog_title: str = ""
    catalog_product_ids: tuple[str, ...] = ()
    catalog_release_type: str = "unknown"
    local_identity_status: str = "unverified"
    # 압축 이름/내부 경로와 *외부 후보 이름*의 독립 대조 신호.
    # 단순 이름·파일명에 불과하므로 결코 자동 일치 확인의 근거가 아니다.
    local_name_support: tuple[str, ...] = ()
    # 다른 공식 상품의 연관 가능성을 명시. 제품 동일성 확정 아님.
    candidate_relationships: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return VERDICT_LABELS[self.verdict]

    def to_dict(self) -> dict:
        result = asdict(self)
        result["label"] = self.label
        # 별도 확인 없이 원본 압축파일/PlayDock 표시 이름/DB를 수정하는 기능은 없음.
        result["read_only"] = True
        return result
