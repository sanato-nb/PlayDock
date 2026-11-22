"""PlayDock Windows console EXE: official ID→name scan, then AI handoff.

No Tkinter, no AI services, no rename operation. Users enter a folder once.
Double-click interactive mode pauses at the end so the completion files are visible.
"""
from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import sys

from experiments.dlsite_detector.scan_handoff import (
    RESULTS_DIR, COMBINED_NAME,
    scan_folder, publish_after_scan,
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
    print(f"생성된 파일: {COMBINED_NAME} (TXT 하나)")
    if stats["excluded"]:
        print("\n==== 통합 TXT 한 개만 복사하면 됩니다 ====")
        print("1. 위 TXT 파일을 메모장으로 엽니다.")
        print("2. Ctrl+A -> Ctrl+C로 전체를 복사해 본인의 ChatGPT/Claude 등에 붙여넣습니다.")
        print("3. 파일에는 조사 지침, 제외 게임 목록, 전체 검사 결과가 모두 들어 있습니다.")
        print("4. AI가 만든 이름 변경 도구는 미리보기와 사용자 승인 후 사용합니다.")
        print("5. 끝까지 품번을 찾지 못한 게임은 수동 확인하고 기존 이름을 유지합니다.")
    else:
        print("\n실패한 게임이 없습니다. 이 TXT에는 전체 검사 결과만 기록했습니다.")
    return 0


def main(argv=None) -> int:
    # Windows PowerShell/영문 로캘은 cp1252로 리디렉션될 수 있으므로
    # PyInstaller 콘솔 실행 파일에서 한국어 출력으로 인한 크래시를 막는다.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    parser = ArgumentParser(
        prog="PlayDock-ID-Scan-And-Prompt",
        description="ZIP/7z/RAR 파일명에서 DLsite→Steam 식별번호로 공식 작품명 확인 후 AI 인계 파일을 만듭니다."
    )
    parser.add_argument("folder", nargs="?", help="검사할 게임 압축파일 폴더")
    parser.add_argument("--output", help="결과 저장 위치 (기본: 검사 폴더/PlayDock_Results)")
    parser.add_argument("--top-level", action="store_true", help="하위 폴더 제외")
    parser.add_argument("--self-test", action="store_true", help="로컬 무네트워크 자체 검사")
    parser.add_argument("--verify-rename-script", metavar="PS1",
                        help="AI가 완성한 PS1의 고정 코드·JSON 이름 변경 목록을 독립 검증")
    args = parser.parse_args(argv)
    if args.verify_rename_script:
        from experiments.dlsite_detector.rename_validation import verify_rename_script
        try:
            result = verify_rename_script(args.verify_rename_script)
        except (OSError, ValueError, RuntimeError) as exc:
            print(f"[검증 실패] 이름 변경 PS1을 실행하지 마세요: {exc}", file=sys.stderr)
            return 1
        print(f"[검증 통과] 고정 PowerShell 코드 일치 · 이름 변경 목록 {result.number_of_rules}건")
        print("검증은 코드 구조와 데이터 형식을 확인한 것입니다. 작품 품번의 정확성은 별도 확인하세요.")
        return 0
    if args.self_test:
        from experiments.dlsite_detector.rename_template import PS1_TEMPLATE
        from experiments.dlsite_detector.rename_validation import verify_rename_script
        assert verify_rename_script(PS1_TEMPLATE, from_text=True).number_of_rules == 0
        from experiments.dlsite_detector.scan_handoff import make_ai_prompt
        assert "DLsite" in make_ai_prompt(2)
        assert "Steam" in make_ai_prompt(2)
        assert not make_ai_prompt(0)
        assert "PlayDock_Excluded_Games.txt" not in make_ai_prompt(2)
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
