"""v0.5: 서로 다른 외부 검색 결과에 담긴 *같은 작품 제목*만 보수적으로 통합.

공식 코드가 같거나, 공식 제목이 명시적으로 다른 언어/단축명을
병기한 경우에만 합친다. 번역 상품과 원작처럼 서로 다른 DLsite
상품코드는 설령 제목이 같아도 한 상품으로 합치지 않는다.
"""
from __future__ import annotations

import re
from typing import Sequence

from .detector import normalized_title

CJK = re.compile(r"[가-힣ぁ-んァ-ヶ一-龯]")
ENGLISH = re.compile(r"[A-Za-z]{3,}")
BILINGUAL = re.compile(r"\s+[-–—|/]\s+")
SUBTITLE = re.compile(r"^(.{6,90}?)\s*[~～]\s*[^~～]+[~～]?\s*$")
DISTRIBUTION_PREFIX = re.compile(
    r"^(?:【|\[)\s*(?:AI\s*번역|AI\s*翻訳|翻訳パッチ|번역\s*패치)"
    r"[^\]】]*(?:】|\])", re.I,
)


def explicit_title_keys(name: str) -> set[str]:
    full = normalized_title(name)
    result = {full} if full else set()
    parts = [s.strip(" -–—|/") for s in BILINGUAL.split(name)]
    if (len(parts) >= 2 and any(CJK.search(p) for p in parts)
            and any(ENGLISH.search(p) for p in parts)):
        # '게임 제목 - 영어 이름 -'처럼 정식 작품명에 실제로 병기된 항목만.
        result.update(
            normalized_title(p) for p in parts
            if len(p) >= 4 and (CJK.search(p) or ENGLISH.search(p))
        )
    match = SUBTITLE.fullmatch(name.strip())
    if match:
        title = match.group(1).strip()
        # 부제 삭제는 명시적으로 ~...~ 표기를 한 경우에만 수행.
        result.add(normalized_title(title))
    return {x for x in result if x}


def _ids(decision) -> tuple[str, str]:
    dlsite = (getattr(decision, "dlsite_code", "") or "").upper()
    steam = (getattr(decision, "source_id", "")
             if getattr(decision, "source_platform", "") in {"steam", "dlsite+steam"} else "")
    return dlsite, steam


def _can_merge(first, second) -> bool:
    a, b = _ids(first), _ids(second)
    # 두 *다른* 공식 상품 코드 또는 Steam ID는 절대 병합하지 않는다.
    if any(x and y and x != y for x, y in zip(a, b)):
        return False
    if a[0] and a[0] == b[0]:
        return True
    if a[1] and a[1] == b[1]:
        return True
    # DLsite↔Steam은 같은 제목이어도 공식 교차 링크 없이는 독립 상품이다.
    if (a[0] and b[1]) or (a[1] and b[0]):
        return False
    name_a = (getattr(first, "proposed_title", "") or "").strip()
    name_b = (getattr(second, "proposed_title", "") or "").strip()
    # 서로 다른 발매 작품을 패치/원작으로 잘못 합치지 않는다.
    if bool(DISTRIBUTION_PREFIX.match(name_a)) != bool(DISTRIBUTION_PREFIX.match(name_b)):
        return False
    keys_a, keys_b = explicit_title_keys(name_a), explicit_title_keys(name_b)
    if not keys_a or not keys_b:
        return False
    return bool(keys_a & keys_b)


def _linked_through_official_bridge(first, second, context: Sequence) -> bool:
    """공식 DLsite + Steam 원본을 둘 다 확인한 단일 조회만 교차 링크로 사용."""
    a, b = _ids(first), _ids(second)
    if any(x and y and x != y for x, y in zip(a, b)):
        return False
    name_a = (getattr(first, "proposed_title", "") or "").strip()
    name_b = (getattr(second, "proposed_title", "") or "").strip()
    if bool(DISTRIBUTION_PREFIX.match(name_a)) != bool(DISTRIBUTION_PREFIX.match(name_b)):
        return False
    for item in context:
        if getattr(item, "source_platform", "") != "dlsite+steam":
            continue
        dlsite, steam = _ids(item)
        if not (dlsite and steam):
            continue
        if ((a[0] == dlsite and b[1] == steam)
                or (a[1] == steam and b[0] == dlsite)):
            return True
    return False


def group_external_attempts(attempts: Sequence) -> tuple[tuple, ...]:
    """IdentityAttempt 목록을 제품 후보 그룹으로 병합. 대표는 공식 코드 우선.

    결과는 각 그룹에 속한 IdentityAttempt의 tuple. 같은 단축 제목이 다른
    공식 작품 코드로 나타나면 다른 그룹으로 남긴다.
    """
    found = [
        item for item in attempts
        if getattr(item.decision, "status", "") in {
            "confirmed_game", "platform_confirmed_game",
            "internet_confirmed_game", "internet_candidate",
        } and (getattr(item.decision, "proposed_title", "") or "").strip()
    ]
    groups: list[list] = []
    for item in found:
        matches = [g for g in groups
                   if any(_can_merge(item.decision, member.decision)
                          for member in g)]
        if not matches:
            groups.append([item])
            continue
        if len(matches) == 1:
            matches[0].append(item)
        else:
            # 무관한 그룹은 단순한 제목 유사성으로 합치지 않는다.
            # 공식에서 양쪽 코드/상품을 *각각* 확인한 결정만 중간 연결 가능.
            bridge_context = [item.decision] + [
                member.decision for group in matches for member in group
            ]
            def compatible(a, b):
                return (_can_merge(a, b) or
                        _linked_through_official_bridge(a, b, bridge_context))
            if all(compatible(item.decision, m.decision)
                   for group in matches for m in group) and all(
                    compatible(a.decision, b.decision)
                    for i, g in enumerate(matches) for other in matches[i + 1:]
                    for a in g for b in other
            ):
                main = matches[0]
                main.append(item)
                for other in matches[1:]:
                    main.extend(other)
                    groups.remove(other)
            else:
                groups.append([item])
    return tuple(tuple(g) for g in groups)


def representative(group: Sequence):
    """확인된 DLsite 번호/Steam ID → 공식 상태 → 더 자세한 제목 순."""
    return max(
        group,
        key=lambda a: (
            a.decision.status in {"confirmed_game", "platform_confirmed_game"},
            bool(a.decision.dlsite_code or a.decision.source_id),
            len(a.decision.proposed_title),
        ),
    )


def catalog_titles(attempts: Sequence) -> tuple[str, ...]:
    return tuple(representative(g).decision.proposed_title
                 for g in group_external_attempts(attempts))
