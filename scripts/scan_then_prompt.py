"""PlayDock Windows console EXE: official ID→name scan, then AI handoff.

No Tkinter, no AI services, no rename operation. Users enter a folder once.
Double-click interactive mode pauses at the end so the completion files are visible.
"""
from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import sys

from experiments.dlsite_detector.scan_handoff import (
    RESULTS_DIR, FULL_NAME, EXCLUDED_NAME, PROMPT_NAME,
    find_archive_names, scan_folder, publish_after_scan,
)


def _progress(done: int, total: int, result):
    # Print an occasional progress line. Never log sensitive absolute paths.
    if done == 1 or done == total or done % max(1, total // 20) == 0:
        pct = 100 * done // total
        print(f"[{pct:3d}%] {done}/{total} 검사 완료 | 최근 상태: {result.status}", flush=True)


def run(folder: str | Path, *, output_dir: str | Path | None = None,
        recursive: bool = True) -> int:
    root = Path(str(folder).strip().strip('"'))
    print("\nPlayDock — DLsite → Steam 공식 품번·작품명 검사", flush=True)
    print("검사는 압축파일 이름만 사용합니다. 압축 내부 및 일반 제목 검색은 하지 않습니다.")
    try:
        report = scan_folder(root, recursive=recursive, progress=_progress)
        # Output generation begins only after successful full scan.
        destination = publish_after_scan(
            report, output_dir if output_dir is not None else root / RESULTS_DIR
        )
    except (OSError, ValueError, PermissionError) as exc:
        print(f"\n[오류] 검사를 완료하지 못했습니다: {exc}", file=sys.stderr)
        print("중간 결과를 성공으로 표시하거나 AI 프롬프트를 생성하지 않았습니다.")
        return 1
    stats = report.counts
    print("\n====== 모든 파일 검사 완료 ======")
    print(f"전체 {stats['total']}개 | 공식 확인 {stats['confirmed']}개 | "
          f"일부 확인 {stats['partial']}개 | 제외 {stats['excluded']}개")
    print(f"저장 폴더: {destination}")
    print(f"  - {FULL_NAME}")
    if stats["excluded"]:
        print(f"  - {EXCLUDED_NAME}")
        print(f"  - {PROMPT_NAME}")
        print("\n다음 단계 (이용자의 AI로 진행)")
        print(f"1. 위 저장 폴더의 {EXCLUDED_NAME}과 {PROMPT_NAME}을 엽니다.")
        print("2. 두 파일을 본인의 ChatGPT 또는 다른 AI에 첨부해 조사 요청.")
        print("3. AI가 제공하는 이름 변경 미리보기와 파일명 변경 도구를 검토해 실행.")
        print("4. 끝까지 못 찾은 게임은 수동 확인하고 파일 이름을 유지.")
    else:
        print("\n실패한 게임이 없습니다. AI 조사용 프롬프트는 생성하지 않았습니다.")
    return 0


def main(argv=None) -> int:
    parser = ArgumentParser(
        prog="PlayDock-ID-Scan-And-Prompt",
        description="ZIP/7z/RAR 파일명에서 DLsite→Steam 식별번호로 공식 작품명 확인 후 AI 인계 파일을 만듭니다."
    )
    parser.add_argument("folder", nargs="?", help="검사할 게임 압축파일 폴더")
    parser.add_argument("--output", help="결과 저장 위치 (기본: 검사 폴더/PlayDock_Results)")
    parser.add_argument("--top-level", action="store_true", help="하위 폴더 제외")
    parser.add_argument("--self-test", action="store_true", help="로컬 무네트워크 자체 검사")
    args = parser.parse_args(argv)
    if args.self_test:
        from experiments.dlsite_detector.scan_handoff import make_ai_prompt
        assert "DLsite" in make_ai_prompt(2)
        assert "Steam" in make_ai_prompt(2)
        assert not make_ai_prompt(0)
        print("PlayDock scan→prompt EXE self-test: PASS")
        return 0

    interactive = not bool(args.folder)
    if interactive:
        print("게임 압축파일이 있는 폴더의 전체 경로를 붙여넣어 주세요.")
        print("예: C:\\Games\\Archives")
        try:
            selected = input("게임 폴더 경로 > ").strip()
        except (EOFError, KeyboardInterrupt):
            return 130
        if not selected:
            print("폴더가 선택되지 않았습니다.")
            return 1
    else:
        selected = args.folder
    try:
        return run(selected, output_dir=args.output,
                   recursive=not args.top_level)
    except KeyboardInterrupt:
        print("\n사용자가 검사를 중단했습니다. 프롬프트를 생성하지 않습니다.")
        return 130
    finally:
        if interactive:
            try:
                input("\n종료하려면 Enter 키를 누르세요...")
            except (EOFError, KeyboardInterrupt):
                pass


if __name__ == "__main__":
    sys.exit(main())
