"""품번 → 공식 작품명 검사 후 제외 항목 AI 인계 파일 생성 (GUI/AI API 없음).

Scan: archive *filenames* only -> DLsite first -> Steam fallback.
Only after the whole scan completes, publish:
  PlayDock_Scan_Results.json
  PlayDock_Excluded_Games.json   (only excluded)
  PlayDock_AI_Prompt.txt         (only when there are exclusions)
No source control, developer identity, local absolute path, or credentials in AI artifacts.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable
import json
import os
import re
import shutil
import uuid

from .code_only import (
    MAX_BATCH, InputItem, Result, Work, archive_name, check, codes_in,
    steam_ids_in,
)

MAX_ARCHIVES = MAX_BATCH
RESULTS_DIR = "PlayDock_Results"
FULL_NAME = "PlayDock_Scan_Results.json"
EXCLUDED_NAME = "PlayDock_Excluded_Games.json"
PROMPT_NAME = "PlayDock_AI_Prompt.txt"


@dataclass(frozen=True)
class ScanReport:
    items: tuple[Result, ...]
    number_of_archives: int

    @property
    def counts(self) -> dict[str, int]:
        states = Counter(x.status for x in self.items)
        return {
            "total": self.number_of_archives,
            "confirmed": states["confirmed"],
            "partial": states["partial"],
            "excluded": states["excluded"],
        }


def find_archive_names(directory: str | Path, *, recursive: bool = True,
                       limit: int = MAX_ARCHIVES) -> tuple[str, ...]:
    """Enumerate without archive extraction and without following symlinks/junctions."""
    root = Path(directory)
    if not root.is_dir():
        raise ValueError("검사할 폴더가 존재하지 않습니다.")
    names: list[str] = []
    if recursive:
        for here, folders, filenames in os.walk(root, followlinks=False):
            folders[:] = [f for f in folders
                          if not (Path(here) / f).is_symlink()
                          and not (Path(here) / f).is_junction()]
            for filename in sorted(filenames, key=str.casefold):
                p = Path(here) / filename
                if p.is_symlink() or not p.is_file() or not archive_name(filename):
                    continue
                names.append(filename)
                if len(names) > limit:
                    raise ValueError(f"압축파일이 {limit}개를 넘습니다. 폴더를 나눠 검사하세요.")
    else:
        names = [p.name for p in sorted(root.iterdir(), key=lambda p: p.name.casefold())
                 if p.is_file() and not p.is_symlink() and archive_name(p.name)]
        if len(names) > limit:
            raise ValueError(f"압축파일이 {limit}개를 넘습니다. 폴더를 나눠 검사하세요.")
    return tuple(names)


def scan_folder(directory: str | Path, *, recursive: bool = True,
                checker: Callable[..., Result] = check,
                progress: Callable[[int, int, Result], None] | None = None,
                ) -> ScanReport:
    names = find_archive_names(directory, recursive=recursive)
    if not names:
        raise ValueError("선택한 폴더에 ZIP/7z/RAR 게임 압축파일이 없습니다.")
    cache: dict[str, Work] = {}
    results = []
    for i, name in enumerate(names, 1):
        try:
            result = checker(InputItem(name, "archive"), cache=cache)
        except Exception as exc:
            result = Result(name, "archive", "excluded",
                            warnings=(f"공식 검사 예외: {type(exc).__name__}",))
        results.append(result)
        if progress:
            progress(i, len(names), result)
    return ScanReport(tuple(results), len(names))


def _reason(result: Result) -> str:
    if not codes_in(result.query) and not steam_ids_in(result.query):
        return "no_identifier"
    return "official_lookup_failed"


def build_full(report: ScanReport) -> dict:
    return {
        "program": "PlayDock DLsite-Steam Code to Official Name",
        "mode": "dlsite_then_steam",
        "created_at_local": datetime.now().astimezone().isoformat(),
        "api_key_used": False,
        "archive_contents_inspected": False,
        "files_only_no_paths": True,
        "summary": report.counts,
        "results": [r.to_dict() for r in report.items],
    }


def build_excluded(report: ScanReport) -> dict:
    all_names = Counter(r.query.casefold() for r in report.items)
    rows = []
    for index, r in enumerate(report.items, 1):
        if r.status != "excluded":
            continue
        rows.append({
            "item_id": index,
            "original_filename": r.query,
            "dlsite_codes": list(codes_in(r.query)),
            "steam_app_ids": list(steam_ids_in(r.query)),
            "attempted_stores": list(r.attempted_stores),
            "exclusion_reason": _reason(r),
            "duplicate_filename": all_names[r.query.casefold()] > 1,
            "warnings": list(r.warnings),
        })
    return {
        "schema": "playdock-excluded-v1",
        "mode": "dlsite_then_steam",
        "privacy": "filenames_only_no_local_paths",
        "excluded_count": len(rows),
        "excluded": rows,
    }


def make_ai_prompt(excluded_count: int) -> str:
    """User-facing handoff instructions, never developer/repo/private details."""
    if excluded_count < 1:
        return ""
    return f"""# PlayDock — 자동 검사 실패 게임 조사 및 파일명 변경

1단계 DLsite → Steam 자동 검사가 끝났습니다.
공식 품번을 확인하지 못한 게임 {excluded_count}개가 있습니다.

이 요청을 받으면 첨부된 `{EXCLUDED_NAME}`의 `excluded` 배열만 조사하세요.
목록에 없는 파일을 추가하거나 임의의 식별번호를 만들어 내지 마세요.

## 2단계 — 이 이용자 본인의 AI가 조사하는 작업

1. 게임 파일명에서 작품명과 버전·번역·패치·DLC·합본 표기를 구별하세요.
2. 기존 DLsite 품번이 있다면 그 작품의 공식 페이지부터 확인하세요.
3. DLsite의 등록 작품을 먼저 조사하고, 확실하지 않으면 Steam을 조사하세요.
4. 한국어·영어·일본어 표기, 제작자, 공식 작품명, 시리즈 번호를 교차검증하세요.
5. 게임 본편과 DLC, 번역 패치, 합본을 혼동하지 마세요. 작품번호가 존재한다는 것만으로 파일과 같은 게임이라고 확정하지 마세요.
6. 판매 종료·성인 인증·차단 등으로 열리지 않는 공식 페이지는 미등록이라고 단정하지 마세요.
7. 작품 동일성까지 근거가 충분하면 `official_confirmed`, 불확실하면 `candidate`, 찾지 못하면 `unknown`으로 분류하세요.
8. 가능한 경우 공식 작품 URL과 근거 URL을 남기세요.
9. 아래 JSON으로 모든 제외 항목을 빠짐없이 정리해 제공하세요. `original_filename` 및 `item_id`는 원문과 동일하게 보존하세요.

```json
{{
  "schema": "playdock-ai-review-v1",
  "results": [
    {{
      "item_id": 1,
      "original_filename": "원본 게임 파일명.7z",
      "store": "dlsite",
      "code": "RJ123456",
      "official_title": "공식 작품명",
      "official_url": "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html",
      "evidence_url": "동일 게임 근거 URL",
      "verification": "official_confirmed",
      "note": "게임 동일성 판단 근거"
    }}
  ]
}}
```

Steam 작품번호는 `store: "steam"`, `code: "1091500"`처럼 기록하세요.
품번이 확인되지 않은 작품은 `store`, `code`, `official_url`을 빈 문자열로 하고 `verification: "unknown"`으로 기록하세요.

## 3단계 — 이 이용자의 AI가 파일명 변경 도구를 제공

조사 결과를 토대로 **이 이용자의 Windows PC에서 직접 실행할 수 있는 간단한 이름 변경 도구**를 제공하세요.
PlayDock 자동 검사 프로그램은 이름을 바꾸지 않습니다. 이 단계는 이용자와 이용자의 AI가 수행합니다.

- 사용자가 게임 압축파일 폴더 하나만 선택하도록 하세요.
- 조사 결과 중 `official_confirmed`이며 동일 작품임을 검토한 항목만 변경 후보로 표시하세요.
- 변경 전 `원래 파일명 → 새 파일명` 미리보기를 보여주고 사용자 승인을 받아야 합니다.
- 예: `Game [v1.2] [한국어].7z` → `Game [v1.2] [한국어] [RJ123456].7z`.
- Steam이라면 `[Steam 1091500]`을 붙입니다. 원본의 버전/번역/DLC 표기와 ZIP/7z/RAR 확장자는 유지하세요.
- 기존 품번 중복 추가, 다른 게임 번호 삽입, 동일 이름 덮어쓰기, 폴더 경로 탈출을 막으세요.
- 같은 파일명이 여러 곳에 있거나 DLC/합본 동일성이 불확실하면 변경하지 마세요.
- 변경 기록과 원상복구 기능을 제공하고, 압축파일의 내부 내용을 변경하거나 풀지 마세요.
- AI 환경에서 EXE 빌드가 가능하면 간단한 Windows 실행파일을 제공하세요.
  불가능하다면 별도 Python 설치가 필요 없는 PowerShell 스크립트와 실행용 BAT를 제공하세요.
- 사용자 승인 전에는 실제 파일을 수정하지 말고, 임의 파일 실행이나 다운로드를 강요하지 마세요.

## 4단계 — 끝내 못 찾은 항목

`candidate`/ `unknown`/검증 실패 항목은 수동 처리 목록(CSV 또는 표)으로 제공하세요.
해당 이용자가 DLsite·Steam 공식 사이트에서 직접 확인하도록 안내하세요.
찾지 못하면 파일명을 원래대로 유지해야 합니다.

개인정보: AI에 파일명과 품번 등 조사에 필요한 정보만 전달합니다.
로컬 절대경로, 개인 자격증명, 파일 내용 등을 요구하지 마세요.
"""


def publish_after_scan(report: ScanReport, directory: str | Path) -> Path:
    """All-or-nothing publishing; no outputs written during the scan.

    Success: always full scan JSON; if exclusions exist, excluded JSON + AI prompt.
    """
    parent = Path(directory)
    parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = parent / stamp
    increment = 1
    while target.exists():
        target = parent / f"{stamp}_{increment}"
        increment += 1
    temp = parent / f".playdock-writing-{uuid.uuid4().hex}"
    temp.mkdir()
    try:
        (temp / FULL_NAME).write_text(
            json.dumps(build_full(report), ensure_ascii=False, indent=2),
            encoding="utf-8")
        if report.counts["excluded"]:
            (temp / EXCLUDED_NAME).write_text(
                json.dumps(build_excluded(report), ensure_ascii=False, indent=2),
                encoding="utf-8")
            # UTF-8 BOM lets standard Windows Notepad open Korean TXT correctly.
            (temp / PROMPT_NAME).write_text(
                make_ai_prompt(report.counts["excluded"]),
                encoding="utf-8-sig")
        temp.rename(target)
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    return target
