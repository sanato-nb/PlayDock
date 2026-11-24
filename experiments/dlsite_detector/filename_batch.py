"""PowerShell ls 텍스트로 게임 검색기를 대량 검증하는 독립 CLI.

- --online 미지정: 파일명/품번/배포 태그 분석만 실행. 실제 웹 요청 없음.
- --online: 사용자 명시 동의 시 해당 파일명으로 외부 작품을 조회.
- 사용자 원본 목록·실제 압축파일·PlayDock 데이터베이스 수정 없음.
- 별도 CSV/JSON 보고서는 명시적으로 경로를 지정했을 때만 저장.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import sys
import time

from .identity_hints import extract_hints
from .search_terms import cleaned_search_title


ARCHIVE_EXT = (".zip", ".7z", ".rar")
# 표준 Windows PowerShell 5.1 'ls' 출력: 날짜, 오전/오후, 시각, 바이트, 파일명
POWERSHELL_ROW = re.compile(
    r"^-a----\s+\d{4}-\d{2}-\d{2}\s+(?:오전|오후|AM|PM)\s+"
    r"\d{1,2}:\d{2}\s+(\d+)\s+(.+)$",
    re.I,
)


@dataclass(frozen=True)
class ArchiveRow:
    original_filename: str
    file_size: int


def parse_powershell_listing(content: str) -> list[ArchiveRow]:
    """PowerShell이 긴 한글 파일명을 다음 줄로 감싼 출력도 원본 그대로 복원."""
    rows: list[ArchiveRow] = []
    pending_name = ""
    pending_size = 0

    def flush():
        nonlocal pending_name, pending_size
        if pending_name and pending_name.casefold().endswith(ARCHIVE_EXT):
            rows.append(ArchiveRow(pending_name, pending_size))
        pending_name = ""
        pending_size = 0

    for line in content.splitlines():
        match = POWERSHELL_ROW.match(line)
        if match:
            flush()
            pending_size, pending_name = int(match.group(1)), match.group(2).strip()
        elif pending_name and line.startswith(" " * 20):
            # 줄이 끝나기도 전에 파일명이 잘린 경우에만 이어 붙인다.
            # PowerShell은 줄을 이어 인쇄할 때 실제 이름에 공백을 넣지 않는다.
            if not pending_name.casefold().endswith(ARCHIVE_EXT):
                pending_name += line.strip()
    flush()
    return rows


def read_listing(path: Path) -> list[ArchiveRow]:
    raw = Path(path).read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        content = raw.decode("utf-16")
    else:
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeError:
            content = raw.decode("cp949")
    return parse_powershell_listing(content)


def inspect_filename(row: ArchiveRow) -> dict:
    """검색어 추출 수준에서만 평가. 이 결과를 게임 정체 확정률로 사용하면 안 됨."""
    hints = extract_hints(row.original_filename)
    title = cleaned_search_title(row.original_filename)
    code_only = not title or bool(re.fullmatch(r"(?:RJ|VJ|BJ|EJ)\d{6,8}", title, re.I))
    result = {
        "original_filename": row.original_filename,
        "size_bytes": row.file_size,
        "search_title": title,
        "dlsite_codes": list(hints.dlsite_codes),
        "steam_app_ids": list(hints.steam_app_ids),
        "archive_kind": hints.archive_kind,
        "archive_kind_reason": hints.kind_reason,
        "aliases": list(hints.title_aliases),
        "offline_status": (
            "direct_id_lookup" if code_only and hints.dlsite_codes
            else "review_search_title" if code_only
            else "title_and_id_lookup" if hints.dlsite_codes or hints.steam_app_ids
            else "title_search"
        ),
    }
    return result


def analyze_listing(rows: list[ArchiveRow], *, excluded: tuple[str, ...] = ()):
    omit = {name.casefold() for name in excluded}
    selected = [item for item in rows if item.original_filename.casefold() not in omit]
    records = [inspect_filename(row) for row in selected]
    counts = Counter(item["offline_status"] for item in records)
    kinds = Counter(item["archive_kind"] for item in records)
    extensions = Counter(Path(item["original_filename"]).suffix.lower() for item in records)
    codes = Counter(code for item in records for code in item["dlsite_codes"])
    totals = {
        "input_files": len(rows),
        "excluded_files": len(rows) - len(selected),
        "analyzed_files": len(selected),
        "extension_counts": dict(sorted(extensions.items())),
        "name_analysis": dict(sorted(counts.items())),
        "archive_kinds": dict(sorted(kinds.items())),
        "dlsite_code_files": sum(bool(r["dlsite_codes"]) for r in records),
        "steam_id_files": sum(bool(r["steam_app_ids"]) for r in records),
        "missing_title_files": sum(not r["search_title"] for r in records),
        "duplicate_dlsite_codes": {k: v for k, v in sorted(codes.items()) if v > 1},
    }
    return totals, records


def _flatten(item: dict) -> dict:
    copy = dict(item)
    for key in ("dlsite_codes", "steam_app_ids", "aliases"):
        copy[key] = " | ".join(copy.get(key, []))
    return copy


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="AI 없는 PlayDock 파일명 검색기 전수 검사 (PowerShell ls 출력)"
    )
    parser.add_argument("listing", type=Path, help="PowerShell ls 텍스트 파일")
    parser.add_argument("--exclude", action="append", default=[], help="제외할 정확한 원본 파일명 (반복 가능)")
    parser.add_argument("--online", action="store_true",
                        help="사용자가 명시적으로 허용할 때만 외부 사이트 검색")
    parser.add_argument("--max-online", type=int, default=0,
                        help="온라인 최대 건수; 0이면 제한 없이 전체")
    parser.add_argument("--delay", type=float, default=1.0, help="온라인 검색 간 대기 초")
    parser.add_argument("--csv", type=Path, help="CSV 보고서를 지정 경로에 저장")
    parser.add_argument("--json-output", type=Path, help="JSON 보고서를 지정 경로에 저장")
    args = parser.parse_args(argv)

    if args.max_online < 0 or args.delay < 0:
        parser.error("최대 건수와 대기 초는 음수일 수 없습니다.")
    rows = read_listing(args.listing)
    if not rows:
        parser.error("PowerShell ls 출력에서 ZIP·7z·RAR 파일을 찾지 못했습니다.")
    totals, records = analyze_listing(rows, excluded=tuple(args.exclude))
    if args.online:
        from .enhanced_search import enhanced_classify_game
        for idx, record in enumerate(records):
            if args.max_online and idx >= args.max_online:
                break
            decision = enhanced_classify_game(record["original_filename"])
            record["online_status"] = decision.status
            record["online_proposed_title"] = decision.proposed_title
            record["online_source_platform"] = decision.source_platform
            record["online_source_id"] = decision.source_id
            record["online_reason"] = decision.reason
            # 공개 검색에 대한 요청을 연속해서 과도하게 보내지 않는다.
            if idx < len(records) - 1 and (not args.max_online or idx < args.max_online - 1):
                time.sleep(args.delay)
        totals["online_checked"] = sum("online_status" in row for row in records)
        totals["online_status_counts"] = dict(Counter(
            r["online_status"] for r in records if "online_status" in r))
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", encoding="utf-8-sig", newline="") as stream:
            flattened = [_flatten(r) for r in records]
            fieldnames = list(dict.fromkeys(k for row in flattened for k in row))
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(flattened)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps({"summary": totals, "files": records}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(json.dumps(totals, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
