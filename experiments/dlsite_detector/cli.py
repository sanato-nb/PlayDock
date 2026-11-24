"""독립 DLsite 판별기: 사용자 요청 없이 네트워크 요청을 실행하지 않는다."""
from __future__ import annotations

import argparse
import json

from .detector import Detection, detect_dlsite_game, extract_code


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PlayDock DLsite 게임 등록 여부 실험 도구 (본체 미연결)")
    parser.add_argument("title", nargs="?", default="", help="게임 이름 또는 압축파일명")
    parser.add_argument("--code", default="", help="사용자가 확인한 RJ/VJ/BJ/EJ 작품 코드")
    parser.add_argument("--online", action="store_true", help="실제 DLsite 단일 작품 조회 허용")
    parser.add_argument("--search-title", action="store_true", help="품번이 없으면 공개 웹 검색으로 후보 찾기 (--online 필요)")
    parser.add_argument("--json", action="store_true", help="JSON 형식 출력")
    args = parser.parse_args(argv)

    if not args.online:
        result = Detection(
            "unverified", args.title,
            code=args.code.strip().upper() or extract_code(args.title),
            reason="오프라인 모드입니다. --online을 추가해야 사이트 등록 여부를 조회합니다.",
        )
    else:
        result = detect_dlsite_game(args.title, code=args.code,
                                    allow_title_search=args.search_title)
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"[{result.label}] {result.query}")
        if result.code:
            print(f"작품 코드: {result.code}")
        if result.work_title:
            print(f"확인한 제목: {result.work_title}")
        if result.work_type:
            print(f"작품 유형: {result.work_type}")
        if result.page_url:
            print(f"원본 페이지: {result.page_url}")
        if result.possible_codes:
            print("추가 후보: " + ", ".join(result.possible_codes))
        print(result.reason)
    return 0 if result.status in ("confirmed_game", "registered_non_game", "registered_type_unknown") else 1


if __name__ == "__main__":
    raise SystemExit(main())
