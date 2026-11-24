"""Produce user-neutral PlayDock releases from *freshly built* Windows executables.

No installed application directories, user AppData folders, credential stores,
user ZIP/7z games, or pre-existing `data/` are ever read or copied.
Only explicitly allowlisted EXEs + a known manual are packaged.

Usage (on Windows after build):
  .venv\\Scripts\\python.exe make_public_release.py --dist dist --out public_release
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

VERSION = "0.8.3"
EXECUTABLES = (
    "PlayDock.exe",
    "PlayDock_Uninstall.exe",
    "PlayDock_Setup.exe",
)
INSTALL_MARKER = "PlayDock.install.json"
MANUAL_FILENAME = "PlayDock_사용자설명서_v0.7.7.pdf"
GUIDE_FILENAME = "처음사용법.txt"
DB_GUIDE_FILENAME = "PlayDock_DB_Guide_KO.txt"
SUMS_FILENAME = "SHA256SUMS.txt"
REQUIRED_ZIP = frozenset((*EXECUTABLES, INSTALL_MARKER, MANUAL_FILENAME,
                          GUIDE_FILENAME, DB_GUIDE_FILENAME, SUMS_FILENAME, "data/"))
# Search only the release source, never an entire drive or a developer's profile.
CREDENTIAL_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"sk-(?:proj-|ant-|or-v1-)?[0-9a-zA-Z_\-]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest().upper()


def check_source_no_hardcoded_secrets(source_root: Path) -> None:
    """Catch common literal credential leaks; not a replacement for code review."""
    excluded = {'.git', '.venv', 'venv', 'build', 'dist', 'data', '__pycache__'}
    for path in source_root.rglob('*.py'):
        if any(part in excluded for part in path.relative_to(source_root).parts):
            continue
        if path.is_symlink():
            raise ValueError(f"Symlinked source is not allowed: {path.name}")
        content = path.read_text(encoding='utf-8')
        for rx in CREDENTIAL_PATTERNS:
            if rx.search(content):
                raise ValueError(f"배포 소스에 실제 키처럼 보이는 값이 있습니다: {path.name}")


def build_public_release(dist: Path, out: Path, manual: Path, *, source: Path | None = None) -> dict:
    """Never read application data. Produce standalone installer and clean ZIP."""
    dist = Path(dist)
    out = Path(out)
    manual = Path(manual)
    if source is not None:
        check_source_no_hardcoded_secrets(Path(source))
    if not dist.is_dir() or dist.is_symlink():
        raise FileNotFoundError(f"빌드 EXE 폴더를 찾지 못했습니다: {dist}")
    verified: dict[str, Path] = {}
    for filename in EXECUTABLES:
        path = dist / filename
        if path.is_symlink() or not path.is_file() or path.stat().st_size < 100_000:
            raise FileNotFoundError(f"Windows 빌드 EXE가 없거나 너무 작습니다: {path}")
        with path.open('rb') as handle:
            if handle.read(2) != b'MZ':
                raise ValueError(f"Windows EXE 형식이 아닙니다: {filename}")
        verified[filename] = path
    if manual.is_symlink() or not manual.is_file():
        raise FileNotFoundError(f"배포 설명서가 없습니다: {manual}")
    with manual.open('rb') as handle:
        if handle.read(5) != b'%PDF-':
            raise ValueError("사용자 설명서는 PDF 파일이어야 합니다.")
    out.mkdir(parents=True, exist_ok=True)
    # Never reuse the user's installed program folder. Stage clean files in a
    # unique temporary directory containing only the whitelist.
    with tempfile.TemporaryDirectory(prefix="PlayDock_public_") as temporary:
        stage = Path(temporary)
        (stage / 'data').mkdir()   # Explicitly empty: NO settings/caches/collections.
        for filename, path in verified.items():
            shutil.copyfile(path, stage / filename)
        shutil.copyfile(manual, stage / MANUAL_FILENAME)
        # A fixed non-personal marker makes PlayDock.exe write data beside itself
        # if somebody uses this ZIP directly instead of running Setup.exe.
        (stage / INSTALL_MARKER).write_text(
            json.dumps({"id": "playdock-installed-v1", "data_directory": "data", "version": VERSION},
                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (stage / DB_GUIDE_FILENAME).write_text(
            'PlayDock 공식 작품정보 DB\n\n'
            '1. 상단 게임 정보 수집으로 압축파일명에 있는 DLsite 품번과 Steam App ID를 공식 정보와 대조합니다.\n'
            '2. 품번이 없거나 확인하지 못한 게임은 제외 목록에 표시됩니다. 수집 후 AI 조사용 TXT를 저장할 수 있습니다.\n'
            '3. 공식 작품정보와 게임 연결은 data/playdock.db에 저장됩니다.\n'
            '4. 상단 기능 메뉴의 공식 게임명 설정에서 저장된 DB를 기반으로 미리보기 후 선택 적용합니다.\n'
            '5. 공식 배너·아이콘 적용은 검증된 이미지 후보가 있을 때 활성화되며 선택한 이미지만 변경합니다.\n'
            '6. 공식 사이트의 차단이나 응답 변경으로 조회에 실패할 수 있습니다.\n'
            '7. 공개 배포용 data 폴더는 비어 있으며 개인 작품 DB는 포함되지 않습니다.\n',
            encoding='utf-8')
        (stage / GUIDE_FILENAME).write_text(
            "PlayDock - 처음 사용법\n\n"
            "[권장: 일반 설치]\n"
            "1. PlayDock_Setup.exe를 실행합니다.\n"
            "2. 프로그램 위치, 압축파일 보관 폴더, 게임 설치 폴더를 지정합니다.\n"
            "3. 상단 게임 정보 수집으로 공식 작품정보를 가져옵니다.\n"
            "4. 상단 기능에서 공식 이름 및 이미지를 선택 적용합니다.\n"
            "5. 게임 상세 화면의 게임 관리에서 수동 이름, 배너·아이콘, 실행 옵션, 공식 페이지를 관리합니다.\n\n"
            "[기존 사용자 업데이트]\n"
            "PlayDock을 종료하고 앱 데이터 백업 후 기존 PlayDock.exe만 교체합니다. data/와 게임 폴더는 유지합니다.\n\n"
            "[설치하지 않고 직접 실행]\n"
            "전체 ZIP을 새 폴더에 풀고 PlayDock.exe를 실행합니다. 현재 폴더의 data/에 설정이 저장됩니다.\n"
            "직접 실행본에는 Windows 제거 등록이 없습니다. 개인 데이터를 백업한 후 프로그램 파일만 정리합니다.\n\n"
            "[데이터와 API 키]\n"
            "배포 ZIP의 data/는 비어 있습니다. 개인 설정, 게임 목록, 모음집, 캐시, API 키는 포함되지 않습니다.\n"
            "기존 Windows 계정의 자격 증명이나 이전 AppData는 호환 처리로 인식될 수 있습니다.\n"
            "신규 상태 확인은 새 Windows 계정 또는 Windows Sandbox를 이용하세요.\n"
            "현재 공식 정보 수집과 공식 이름·이미지 적용에는 AI API 키가 필요하지 않습니다.\n\n"
            "[참고]\n"
            "동봉 PDF는 v0.7.7 당시의 과거 설명서입니다. 최신 메뉴는 이 TXT 안내를 우선 참고하세요.\n"
            "PlayDock_Uninstall.exe는 설치형 프로그램 제거용이며 게임 폴더는 보존합니다.\n",
            encoding='utf-8')
        lines = [f"{sha256(stage / filename)}  {filename}" for filename in EXECUTABLES]
        lines.append(f"{sha256(stage / MANUAL_FILENAME)}  {MANUAL_FILENAME}")
        (stage / SUMS_FILENAME).write_text("\n".join(lines) + "\n", encoding="ascii" if all(x.isascii() for x in lines) else "utf-8")
        expected_files = set(REQUIRED_ZIP) - {"data/"}
        actual_files = {p.name for p in stage.iterdir() if p.is_file()}
        if actual_files != expected_files or any((stage / 'data').iterdir()):
            raise RuntimeError("배포 staging에 예상하지 못한 파일이나 개인 데이터가 발견되었습니다.")
        archive = out / f"PlayDock_Public_v{VERSION}.zip"
        # Write to a separate tmp file so an interrupted build cannot leave a
        # seemingly finished ZIP in the final output directory.
        tmp_zip = out / (archive.name + '.tmp')
        try:
            with ZipFile(tmp_zip, 'w', compression=ZIP_DEFLATED, compresslevel=8, allowZip64=True) as zf:
                zf.writestr('data/', b'')
                for filename in sorted(expected_files):
                    zf.write(stage / filename, arcname=filename)
            with ZipFile(tmp_zip, 'r') as zf:
                names = zf.namelist()
                if len(names) != len(REQUIRED_ZIP) or set(names) != REQUIRED_ZIP:
                    raise RuntimeError(f"배포 ZIP에 허용하지 않은 파일이 있습니다: {names}")
                if zf.testzip() is not None:
                    raise RuntimeError("배포 ZIP 손상 검사 실패")
                marker = json.loads(zf.read(INSTALL_MARKER))
                if marker.get('id') != 'playdock-installed-v1' or marker.get('data_directory') != 'data':
                    raise RuntimeError("배포 초기화 표식 검사 실패")
                if any(n.startswith('data/') and n != 'data/' for n in names):
                    raise RuntimeError("배포 ZIP에 개인 data 파일이 들어 있습니다")
            os.replace(tmp_zip, archive)
        finally:
            tmp_zip.unlink(missing_ok=True)
        setup = out / f"PlayDock_Setup_v{VERSION}.exe"
        shutil.copyfile(stage / 'PlayDock_Setup.exe', setup)
        if sha256(setup) != sha256(verified['PlayDock_Setup.exe']):
            raise RuntimeError("설치 파일 SHA256 확인 실패")
    summary = (out / f"PlayDock_Public_v{VERSION}_검사결과.txt")
    summary.write_text(
        f"PlayDock v{VERSION} 공개 배포 패키지 검사\n"
        f"- ZIP 항목: {', '.join(sorted(REQUIRED_ZIP))}\n"
        "- data 폴더: 비어 있음\n"
        "- 개인 설정/모음집/이미지 캐시/API 키: 패키징하지 않음\n"
        "- 실제 Windows 실행과 백신 검사: 배포자가 별도 확인해야 함\n"
        "- 기존 설치 이력/자격 증명이 있는 같은 PC에서는 초기 상태로 보이지 않을 수 있음\n",
        encoding='utf-8')
    return {"zip": archive, "setup": setup, "report": summary}


def main() -> int:
    # A Windows EXE/PowerShell host may redirect stdout to cp1252. Korean
    # report filenames are valid; never treat console encoding as packaging
    # failure after the ZIP and SHA256 checks have already succeeded.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(encoding='utf-8', errors='replace')
            except (OSError, ValueError):
                pass
    parser = argparse.ArgumentParser(description='Build privacy-clean PlayDock public distribution from Windows EXEs')
    parser.add_argument('--dist', type=Path, default=Path('dist'))
    parser.add_argument('--out', type=Path, default=Path('public_release'))
    parser.add_argument('--manual', type=Path, default=Path('docs') / "PlayDock_UserManual_KO_v0.7.7.pdf")
    parser.add_argument('--source', type=Path, default=Path('.'))
    args = parser.parse_args()
    try:
        result = build_public_release(args.dist, args.out, args.manual, source=args.source)
    except Exception as exc:
        print(f"[FAIL] 공개 배포 생성 실패: {exc}", file=sys.stderr)
        return 1
    print("[OK] No user data included; verified ZIP contents and binary signatures.")
    for label, path in result.items():
        print(f"  {label}: {path.resolve()}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
