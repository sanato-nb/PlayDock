# PlayDock v0.8.2 — UI·Controller·Service 코드 분리 + SQLite 작품 DB

- **`data/playdock.db` 자동 생성:** 기존 게임 목록과 작품 코드 연결, 한국어·일본어·영어 제목, 제작사, 발매일, 장르, 표지/샘플 이미지 URL, 작품 원본 URL 저장.
- **게임 관리 / 우클릭 → DLsite 작품 정보 조회·DB 저장:** 사용자가 선택한 한 작품만 사이트 내부 JSON에 조회. 저장 전 결과 검토, 표시 이름은 선택 시에만 변경.
- **조회 기록 재사용:** DB에 있던 작품 정보는 오프라인에서도 표시. 자동 대량 수집은 하지 않음.
- **백업·복원 지원:** 데이터 백업에 DB 추가. 기존 설정·이름·모음집·게임 ZIP/7z/RAR 보존.
- **개인정보 제외 공개 배포:** `public_release/` ZIP에는 사용자의 DB가 포함되지 않으며, 빈 data 폴더만 포함됨.
- **API 안내:** DLsite의 해당 JSON은 사이트 내부용 비공식 연동이며, 정식 공개 API나 공식 전체 작품 DB가 확인된 것은 아님.
- **설명서:** [DB 사용 안내](README_DB_KO.md). 기존 PDF 설명서는 v0.7.7 기본 기능 안내로 유지.

Windows에서 소스 ZIP을 풀고 **`00_BUILD_WINDOWS_EXE.bat`**으로 새 PlayDock v0.8.2 EXE와 `public_release` 파일들을 생성하세요. 이전 0.7.7 EXE는 DB 기능이 포함되지 않아 반드시 새로 빌드해야 합니다.

---

# 공개 배포 BAT 실행 오류 수정 (2026-11-15)

- Windows cmd.exe의 한글 BAT 인코딩 오류를 수정했습니다. 두 BAT 파일을 ASCII/CRLF로 변경했습니다.
- 이전에 잘못 지정한 설명서 경로 `PlayDock_사용자설명서_v0.7.7.pdf`를 실제 파일명 `docs/PlayDock_UserManual_KO_v0.7.7.pdf`로 통일했습니다.
- GitHub Actions의 배포 스크립트 인자도 함께 수정했습니다.
- **이미 EXE 네 개가 `dist/`에 모두 있다면**, 이 수정 패키지를 새 폴더에 풀고 기존 `dist/`와 `.venv/`를 그대로 복사한 다음 **`01_REPACKAGE_EXISTING_EXES.bat`**을 실행하면 됩니다. 이 방법은 EXE를 다시 빌드하지 않습니다.
- EXE가 없거나 소스가 달라진 경우 **`00_BUILD_WINDOWS_EXE.bat`**을 실행하세요.
- 검증 없이 현재 설치된 앱 폴더의 `data/`를 배포하지 마세요.

---

# PlayDock v0.7.7 — 깨끗한 공개 배포 자동 생성

> **이 버전에서 공개 배포는 반드시 `00_BUILD_WINDOWS_EXE.bat`으로 만들어진 `public_release/` 안의 파일을 사용하세요.** 이미 설치된 PlayDock 폴더를 압축하면 개인 `data/`가 함께 포함될 수 있습니다.

Windows에서 자동 빌드하면 아래 배포 파일 2개와 검사 결과가 생성됩니다.

- `public_release/PlayDock_Public_v0.7.7.zip`: 게임 목록·설정·캐시·API 키가 없는 ZIP (실행 EXE + 설치 EXE + 설명서 + 빈 data/)
- `public_release/PlayDock_Setup_v0.7.7.exe`: 다른 PC에 전달할 독립 실행형 설치 프로그램
- `public_release/PlayDock_Public_v0.7.7_검사결과.txt`: 검사 요약

Windows 설치 EXE는 이 Linux 환경에서 생성할 수 없습니다. **새 Windows 사용자 계정 또는 Windows Sandbox에서 최초 설치 후 API 미등록·게임 목록 비어 있음 여부를 확인하세요.** 네 PC에서 기존 계정으로 실행하면 Windows 자격 증명과 과거 데이터가 여전히 인식될 수 있지만, 그것이 배포 파일에 포함된 것은 아닙니다.

[자세한 배포 안내](공개배포_안내.md)

---

# PlayDock v0.7.7 — Windows 실행 파일 / 설치 프로그램 빌드 패키지

> 이름 변경 릴리스: Local Game Shelf → **PlayDock**. 기존 게임 설치·모음집·캐시·이름 관리자 기능은 유지합니다.

## 정식 파일 명칭

| 용도 | 이름 |
|---|---|
| 본체 | `PlayDock.exe` |
| 게임 이름 관리자 | `PlayDock_TitleEditor.exe` |
| 설치 마법사 | `PlayDock_Setup.exe` |
| 제거 프로그램 | `PlayDock_Uninstall.exe` |
| Windows 배포용 압축파일 | `PlayDock_Windows_Release.zip` |
| 빌드 프로젝트 | `PlayDock_v0.7.7_Windows_ReleaseKit.zip` |

Windows 설치된 앱, 창 제목, 시작 메뉴 바로가기, 바탕화면 바로가기 이름도 **PlayDock**을 사용합니다.

## Windows에서 설치 EXE 만들기

1. 이 프로젝트 ZIP을 적절한 폴더에 압축 해제합니다.
2. Windows에서 `00_BUILD_WINDOWS_EXE.bat`을 더블클릭합니다. 처음에는 인터넷과 Python 3.12/3.13 설치가 필요할 수 있습니다.
3. 자동 테스트와 EXE 빌드가 성공하면 `dist\PlayDock_Setup.exe`가 생성됩니다.
4. 설치 마법사를 실행하고 **프로그램 설치 위치**, **게임 압축파일 폴더**, **게임 설치 폴더**를 지정합니다.
5. 설치된 PlayDock과 이름 관리자를 시작 메뉴 또는 바탕화면에서 실행합니다.

설치가 완료되면 일반 사용자는 Python이나 빌드 스크립트 없이 프로그램을 이용할 수 있습니다. `dist\PlayDock_Setup.exe`를 다른 Windows PC에 전달해 설치할 수 있습니다.

## 기존 Local Game Shelf에서 업데이트하기

- 게임 라이브러리와 이름 관리자 실행을 먼저 종료합니다.
- 기존 설치 위치가 Windows에 등록되어 있으면 설치 마법사에서 이전 위치를 우선 제안합니다.
- 설치 폴더 내 `data/`는 그대로 사용합니다. 게임 압축파일·실제 설치된 게임은 이동·삭제하지 않습니다.
- 이미 저장한 한국어/영어/일본어 게임 이름, 모음집, 이미지 캐시와 백업을 유지합니다.
- 기존 설치 폴더가 아닌 새 폴더를 고르면 이전 데이터를 **복사**하고 원본은 자동 삭제하지 않습니다.
- 새 프로그램 설치에 성공하면 예전 Local Game Shelf EXE와 이전 바로가기를 가능한 범위에서 정리합니다.
- 기존 백업 ZIP과 예전 자격 증명 저장소의 API 키는 호환성을 위해 계속 읽을 수 있습니다. 개인 PC에서 키를 삭제하면 이전 서비스 이름으로 저장된 키도 함께 삭제합니다. 환경 변수의 키는 사용자가 별도로 관리해야 합니다.

**업데이트 전 기존 설치 폴더의 `data/`를 따로 백업하세요.** 실제 Windows 설치/제거 및 EXE 동작은 이 Linux 제작 환경에서 검증하지 못했습니다.

## 새 사용자 및 공개 배포 개인정보

이 패키지에는 앱 코드, 기본 리소스, 테스트 및 빌드 스크립트만 포함됩니다. 실제 게임 파일, 기존 모음집, 게임 이미지 캐시, 사용자 `settings.json`, 개인 API 키는 포함하지 않습니다. API 키는 각 사용자가 본인의 Windows 자격 증명 저장소 또는 환경 변수에서 설정합니다.

새 설치자는 처음 실행할 때 자신의 게임 폴더를 직접 지정합니다. 앱 데이터는 기본적으로 선택한 프로그램 설치 폴더의 `data/`에 저장합니다. 관리자 권한이 필요한 `Program Files` 하위보다는 쓰기 권한이 있는 사용자 폴더를 선택하세요.

## 배포 전 확인 사항

- **명칭 중복 주의:** 2026년 11월 공개 검색 기준, `PlayDock`이라는 이름의 Windows 게임 라이브러리 프로그램이 `playdock.app`에서 이미 제공되고 있습니다. 이 소스는 요청한 이름을 기술적으로 적용한 시험 릴리스이며, 공개 배포 전에 상표/브랜드 혼동 가능성을 확인하세요. https://playdock.app/
- 기존 아이콘 디자인 자체는 교체하지 않았습니다. 아이콘 파일명만 `playdock.ico`로 통일했습니다.
- 코드 서명은 포함되어 있지 않습니다. Windows SmartScreen 경고가 나올 수 있습니다.
- 빌드 시 `tests/` 자동 테스트를 실행합니다. 완성된 Windows 설치 파일의 실행·제거 테스트는 별도로 수행해야 합니다.
- **PlayDock v0.7.7은 프로그램 이름 변경 릴리스**이며, 이미지 검색이나 게임 이름 변경 알고리즘의 추가 기능을 포함하지 않습니다.


## v0.8.2 UI·Controller·Service 소스 구조

기존 PySide6(Qt Widgets) 화면의 구성 코드를 `ui/`로 분리했습니다.

- 메인 창 UI 구성: `ui/launcher_layout.py`
- 이름 편집기 UI 구성: `ui/editor_layout.py`
- 공통 QSS 테마: `ui/styles.py`
- 이미지 검색, 모음집, 작품 정보 창과 선택 컴포넌트: `ui/artwork_dialog.py`, `ui/collection_board.py`, `ui/work_info_dialog.py`, `ui/selectors.py`

기존 `app.py`, `title_editor.py`에서 화면 생성 함수를 호출하므로 Windows EXE 빌드 방식은 동일합니다.
자세한 내용은 `UI_코드구조_설명.md`를 확인하세요.
