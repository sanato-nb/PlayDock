"""본체를 열지 않고 압축파일 내부 목록에서 정체 단서를 확인한다."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .archive_inspector import inspect_archive


def main(argv=None):
    parser = argparse.ArgumentParser(description="압축 해제 없이 ZIP/7z/RAR 내부 파일명으로 게임 식별 단서 확인")
    parser.add_argument("archive", type=Path, help="확인할 로컬 압축파일 경로")
    parser.add_argument("--json", action="store_true", help="JSON 구조화 출력")
    args = parser.parse_args(argv)
    result = inspect_archive(args.archive)
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print("압축파일:", result.archive_name)
        print("상태:", result.state, "| 내부 파일 항목:", result.member_count)
        print("작품 코드 후보:", ", ".join(result.product_codes) or "없음")
        print("게임 이름 후보:", ", ".join(result.title_candidates) or "없음")
        print("엔진 단서:", ", ".join(result.engine_hints) or "없음")
        print("근거:")
        for item in result.evidence:
            print(f" - {item.path} : {item.reason}")
        print(result.reason)
    return 0 if result.state in ("ok", "partial") else 1


if __name__ == "__main__":
    raise SystemExit(main())
