"""PlayDock 1~5단계 독립 검색 실험 CLI.

--online 시 비암호화 압축파일은 검색 성공 여부와 관계없이 목록/소형
메타데이터를 확인한다. --online 없이는 외부 인터넷을 사용하지 않는다.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .archive_inspector import inspect_archive
from .archive_identity import identify_archive
from .identity_hints import extract_hints
from .internal_metadata import inspect_metadata


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PlayDock 게임 정체 1~5단계 검색 실험 (본체 미연결)")
    parser.add_argument("archive", type=Path, help="ZIP/7z/RAR 압축파일의 로컬 경로")
    parser.add_argument("--online", action="store_true",
                        help="1차 이름 검색 및 2차 재검색을 실제 인터넷에 요청")
    parser.add_argument("--json", action="store_true", help="JSON 결과 출력")
    parser.add_argument("--metadata", action="store_true",
                        help="오프라인 검사에서도 작은 README·INI·JSON 제목 필드를 확인")
    parser.add_argument("--no-metadata", action="store_true",
                        help="온라인 분석에서 작은 파일 내용 읽기를 생략 (1~4단계만)")
    args = parser.parse_args(argv)

    if args.online:
        result = (identify_archive(args.archive)
                  if args.no_metadata else
                  identify_archive(args.archive, allow_metadata=True))
        output = result.to_dict()
        exit_code = 0 if result.status in ("confirmed_game", "suspected_non_game", "candidate_found") else 1
    else:
        inspection = inspect_archive(args.archive)
        output = {"mode": "offline_inventory", **inspection.to_dict(),
                  "filename_hints": extract_hints(args.archive.name).to_dict()}
        if args.metadata:
            output["metadata"] = inspect_metadata(args.archive).to_dict()
        exit_code = 0 if inspection.state in ("ok", "partial", "limit_exceeded") else 1

    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    elif args.online:
        print(f"[{result.label}] {result.archive_name}")
        print(f"수행한 단계: {', '.join(str(s) for s in result.completed_steps)}")
        print(f"후보 근거 단계: {result.stage} · 제안 작품명: {result.proposed_title or '미확인'}")
        print(f"암호화 상태: {result.encryption_state}")
        info = result.to_dict()
        if info["source_id"]:
            print(f"원본 출처: {info['source_platform']} / {info['source_id']}")
        print(f"파일 종류 추정: {info['archive_kind']}")
        if result.inspection is not None:
            print(f"내부 목록: {result.inspection.state} / "
                  f"{result.inspection.member_count}개 항목 검사")
        for attempt in result.attempts:
            print(f" {attempt.stage}단계: {attempt.query} ({attempt.basis}) → {attempt.decision.label}")
        if result.metadata is not None:
            print(f"내부 메타데이터: {result.metadata.state}, "
                  f"{result.metadata.inspected_files}개 항목에서 제목 단서 "
                  f"{len(result.metadata.title_candidates)}개")
        print(result.reason)
    else:
        print(f"[오프라인 내부 목록] {inspection.archive_name}")
        print(f"상태: {inspection.state}, 파일 항목: {inspection.member_count}")
        print("게임명 후보:", ", ".join(inspection.title_candidates) or "없음")
        print("품번 후보:", ", ".join(inspection.product_codes) or "없음")
        print("엔진 단서:", ", ".join(inspection.engine_hints) or "없음")
        if args.metadata:
            metadata = output["metadata"]
            print("내부 제목 단서:", ", ".join(metadata["title_candidates"]) or "없음")
            print("메타데이터 읽기 상태:", metadata["state"])
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
