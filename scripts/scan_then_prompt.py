"""PlayDock Windows console EXE: official ID→name scan, then AI handoff.

No Tkinter or AI services. Renaming bare-ID files is strictly opt-in.
Double-click interactive mode pauses at the end so the completion files are visible.
"""
from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import sqlite3
import sys

from scripts.folder_picker import pick_windows_folder
# The standalone scanner shares PlayDock's Python service modules but does not
# import any Qt UI package or create a second metadata database.
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "playdock"))
from database.official_catalog import (
    OfficialWorkCatalog, default_catalog_path, remember_install_folder,
)
from experiments.dlsite_detector.code_only_renamer import (
    apply_code_only_renames, undo_last_auto_rename,
)

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
        recursive: bool = True, rename_code_only: bool = False) -> int:
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
    # Keep the existing single-TXT handoff unchanged. Verified metadata
    # goes to installed PlayDock/data/playdock.db, never a second SQLite DB.
    catalog = OfficialWorkCatalog()
    try:
        saved = catalog.save_verified_results(report.items)
        print(f"PlayDock 공용 works 테이블: {saved}건 저장/갱신")
        if saved:
            print(f"DB 위치: {catalog.path}")
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"[안내] 공용 DB 저장 생략 ({exc}). 통합 TXT는 정상 생성했습니다.")
    if rename_code_only:
        try:
            changed, changes = apply_code_only_renames(root, report.items, recursive=recursive)
            print(f"\n[품번 파일 이름 변경] {changed}개 변경 (시작 옵션 2 적용)")
            for item in changes:
                print("  " + item)
            if changed:
                print("복구하려면 다음 실행 시 시작 옵션 3을 선택하세요.")
        except (OSError, ValueError) as exc:
            print(f"[경고] 자동 이름 변경을 진행하지 못했습니다: {type(exc).__name__}")
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
    parser.add_argument("--playdock-folder", help="DB 저장을 위해 PlayDock 설치 폴더 지정 (설치 표식 필요)")
    parser.add_argument("--top-level", action="store_true", help="하위 폴더 제외")
    parser.add_argument("--rename-code-only", action="store_true",
                        help="시작 시 품번만 있는 압축파일 이름 변경 옵션 2 선택 (폴더 Y 확인 필요)")
    parser.add_argument("--undo-renames", action="store_true",
                        help="이전 자동 이름 변경을 UNDO 복구 (폴더 Y 확인 필요)")
    parser.add_argument("--self-test-renames", action="store_true",
                        help="네트워크 없는 임시 파일로 자동 이름 변경과 복구 자체 검사")
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

    if args.self_test_renames:
        from tempfile import TemporaryDirectory
        from experiments.dlsite_detector.code_only import Result, Work
        with TemporaryDirectory(prefix="PlayDock_Rename_Test_") as tmp:
            folder = Path(tmp) / "games"
            folder.mkdir()
            source = folder / "RJ123456.zip"
            source.write_bytes(b"FAKE ARCHIVE - NO EXTRACTION")
            work = Work("RJ123456", "검증된 게임", "maniax",
                        "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html",
                        "verified", "dlsite")
            report = (Result(source.name, "archive", "confirmed", (work,),
                             selected_store="dlsite"),)
            changed, _ = apply_code_only_renames(
                folder, report, journal_directory=Path(tmp) / "journals")
            target = folder / "검증된 게임 [RJ123456].zip"
            assert changed == 1 and target.read_bytes() == b"FAKE ARCHIVE - NO EXTRACTION"
            restored, _ = undo_last_auto_rename(
                folder, journal_directory=Path(tmp) / "journals")
            assert restored == 1 and source.read_bytes() == b"FAKE ARCHIVE - NO EXTRACTION"
        print("PlayDock code-only rename and UNDO EXE self-test: PASS")
        return 0

    interactive = not bool(args.folder)
    rename_enabled = bool(args.rename_code_only)
    operation = "undo" if args.undo_renames else "scan"
    initial_path = ""
    pause_after_scan = False
    try:
        if interactive:
            print("\n====== PlayDock 시작 옵션 ======")
            print("1. 품번 검사만 진행 (기본값, 파일 이름 유지)")
            print("2. 품번만 있는 파일: 검사 후 공식 작품명으로 자동 이름 변경")
            print("3. 이전 자동 이름 변경 UNDO 복구")
            try:
                choice = input("옵션 선택 (1/2/3, Enter: 1) > ").strip()
            except EOFError:
                print("시작 옵션 입력이 없어 종료합니다.")
                return 0
            except KeyboardInterrupt:
                print("\n시작 옵션을 취소했습니다.")
                return 130
            if choice == "2":
                rename_enabled = True
            elif choice == "3":
                operation = "undo"
            elif choice not in ("", "1"):
                # Backward compatibility with old builds: a user may paste
                # the folder path immediately, before noticing the new menu.
                initial_path = choice
            if not initial_path:
                print("게임 압축파일이 있는 폴더 경로를 입력하세요.")
                print("예: C:\\Games\\Archives")
                print("경로 없이 Enter를 누르면 Windows 폴더 선택창이 열립니다.")
                try:
                    initial_path = input("게임 폴더 경로 (Enter: 폴더 선택창) > ").strip()
                except EOFError:
                    print("검사를 취소했습니다.")
                    return 0
                except KeyboardInterrupt:
                    print("\n검사를 취소했습니다.")
                    return 130
            if not initial_path:
                try:
                    initial_path = pick_windows_folder()
                except RuntimeError as exc:
                    print(f"[오류] {exc}", file=sys.stderr)
                    return 1
                if not initial_path:
                    print("폴더 선택을 취소했습니다. 검사 및 결과 TXT 생성은 하지 않았습니다.")
                    return 0
            selected = initial_path
        else:
            selected = args.folder

        try:
            chosen = Path(str(selected).strip().strip('"')).expanduser()
            if not chosen.is_dir():
                print(f"[오류] 게임 폴더를 찾을 수 없습니다: {chosen}")
                return 1
            chosen = chosen.resolve(strict=True)
            print(f"\n선택한 검사 폴더: {chosen}", flush=True)
            mode = "원상복구" if operation == "undo" else (
                "품번만 있는 파일 자동 이름 변경" if rename_enabled else "검사만 진행")
            print(f"선택한 작업: {mode}", flush=True)
            answer = input("이 폴더가 맞습니까? (Y: 진행 / N: 취소) > ").strip()
        except EOFError:
            print("\n확인 입력이 없어 취소했습니다. 파일은 변경하지 않았습니다.")
            return 0
        except KeyboardInterrupt:
            print("\n폴더 확인이 취소되었습니다.")
            return 130
        except (OSError, ValueError) as exc:
            print(f"[오류] 폴더를 확인하지 못했습니다: {exc}")
            return 1
        if answer.upper() != "Y":
            print("검사를 취소했습니다. 파일 검사 및 결과 TXT 생성은 하지 않았습니다.")
            return 0
        pause_after_scan = interactive
        if operation != "undo":
            if args.playdock_folder:
                try:
                    db_path = remember_install_folder(args.playdock_folder)
                    print(f"PlayDock 공용 DB 위치: {db_path}")
                except (OSError, ValueError) as exc:
                    print(f"[경고] PlayDock DB 위치를 저장하지 못했습니다: {exc}")
                    print("검사 TXT는 계속 생성되지만 공용 DB에는 쓰지 않습니다.")
            elif default_catalog_path() is None and interactive and sys.stdin.isatty():
                print("\nPlayDock 공용 작품 DB가 아직 연결되지 않았습니다.")
                print("설치된 PlayDock 폴더를 지정하면 data\\playdock.db 한 곳에만 공식정보를 저장합니다.")
                try:
                    install_choice = input("설치 폴더 경로 (F: 폴더 선택 / Enter: DB 저장 건너뛰기) > ").strip().strip('"')
                except (EOFError, KeyboardInterrupt):
                    install_choice = ""
                if install_choice.upper() == "F":
                    try:
                        install_choice = pick_windows_folder() or ""
                    except RuntimeError as exc:
                        print(f"[경고] 폴더 선택 불가: {exc}")
                        install_choice = ""
                if install_choice:
                    try:
                        db_path = remember_install_folder(install_choice)
                        print(f"공용 DB 위치: {db_path}")
                    except (OSError, ValueError) as exc:
                        print(f"[경고] PlayDock 설치 경로 확인 실패: {exc}")
                        print("검사는 계속하며 DB 파일을 별도로 생성하지 않습니다.")
        if operation == "undo":
            try:
                confirmed = input("자동 이름 변경을 복구하려면 UNDO 입력 > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n복구를 취소했습니다.")
                return 0
            if confirmed != "UNDO":
                print("복구를 취소했습니다. 파일을 변경하지 않았습니다.")
                return 0
            try:
                restored, messages = undo_last_auto_rename(chosen)
            except (OSError, ValueError) as exc:
                print(f"[오류] 자동 이름 변경 복구 실패: {type(exc).__name__}")
                return 1
            for message in messages:
                print("  " + message)
            print(f"자동 이름 변경 복구 완료: {restored}개")
            return 0
        return run(chosen, output_dir=args.output,
                   recursive=not args.top_level, rename_code_only=rename_enabled)
    except KeyboardInterrupt:
        print("\n사용자가 검사를 중단했습니다. 프롬프트를 생성하지 않습니다.")
        return 130
    finally:
        if pause_after_scan:
            try:
                input("\n종료하려면 Enter 키를 누르세요...")
            except (EOFError, KeyboardInterrupt):
                pass

if __name__ == "__main__":
    sys.exit(main())
