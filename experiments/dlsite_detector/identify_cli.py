"""압축파일 이름 검색 → 실패 시 내부 목록 재검색 실험 프로그램.

--online 없이 호출하면 압축파일 목록만 확인하고 외부 네트워크에 연결하지 않는다.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .archive_inspector import inspect_archive
from .archive_identity import identify_archive


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PlayDock 게임 정체 2단계 검색 실험 (본체 미연결)")
    parser.add_argument("archive", type=Path, help="ZIP/7z/RAR 압축파일의 로컬 경로")
    parser.add_argument("--online", action="store_true",
                        help="1차 이름 검색 및 2차 재검색을 실제 인터넷에 요청")
    parser.add_argument("--json", action="store_true", help="JSON 결과 출력")
    args = parser.parse_args(argv)

    if args.online:
        result = identify_archive(args.archive)
        output = result.to_dict()
        exit_code = 0 if result.status in ("confirmed_game", "suspected_non_game", "candidate_found") else 1
    else:
        inspection = inspect_archive(args.archive)
        output = {"mode": "offline_inventory", **inspection.to_dict()}
        exit_code = 0 if inspection.state in ("ok", "partial", "limit_exceeded") else 1

    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    elif args.online:
        print(f"[{result.label}] {result.archive_name}")
        print(f"진행 단계: {result.stage} · 제안 작품명: {result.proposed_title or '미확인'}")
        for attempt in result.attempts:
            print(f" {attempt.stage}단계: {attempt.query} ({attempt.basis}) → {attempt.decision.label}")
        print(result.reason)
    else:
        print(f"[오프라인 내부 목록] {inspection.archive_name}")
        print(f"상태: {inspection.state}, 파일 항목: {inspection.member_count}")
        print("게임명 후보:", ", ".join(inspection.title_candidates) or "없음")
        print("품번 후보:", ", ".join(inspection.product_codes) or "없음")
        print("엔진 단서:", ", ".join(inspection.engine_hints) or "없음")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
