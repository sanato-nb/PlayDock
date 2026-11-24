# PlayDock

ZIP·7z·RAR로 보관한 게임을 관리·설치·실행하는 Windows용 Python 3.12/PySide6/SQLite 데스크톱 앱입니다.

## 현재 개발 상태 — 2026-11-24

- 게임 정보 수집: 압축파일명에 있는 DLsite 품번 또는 Steam App ID를 공식 사이트와 대조해 SQLite 작품정보 및 게임 연결을 저장합니다.
- 품번 없는 압축게임: 공식 조회에서 사전 제외하고, 수집 종료 후 AI 조사 프롬프트를 복사하거나 TXT로 저장할 수 있습니다.
- 공식 배너·아이콘 적용: 선택 게임에 검증된 공식 이미지 후보가 있는 경우만 활성화합니다. 체크하지 않은 이미지는 변경하지 않습니다.
- 공식 게임명 설정: 저장된 DB 기반으로 여러 게임의 표시 이름을 미리보고 선택 적용합니다.
- 게임 관리: 수동 이름 변경, 수동 배너·아이콘 설정, 실행 옵션, 공식 작품 페이지 열기.
- 설정: 폴더 설정, 데이터 관리, 라이브러리 속성, DB 상태 확인. AI 설정 메뉴는 제거했으며 기존 저장값은 보존합니다.
- 상단 화면 선택과 기능 버튼 활성화, 공통 파일 선택 창 디자인을 개선했습니다.
- 원본 압축파일, 게임 목록, 모음집, 설정과 이미지 캐시를 임의로 삭제하거나 변경하지 않습니다.

## 다운로드 및 검증

[Windows Actions 실행 목록](https://github.com/sanato-nb/PlayDock/actions/workflows/playdock-inprocess-title-windows.yml)에서 **현재 커밋에 해당하는 성공한 실행**을 선택합니다.

| 아티팩트 | 용도 |
|---|---|
| PlayDock-Update-EXE-Windows | 기존 설치의 PlayDock.exe 교체 |
| PlayDock-Installer-Only-Windows | 새 설치 |
| PlayDock-Full-Package-Windows | 전체 배포 패키지 |

기존 사용자 데이터는 유지하고 프로그램을 종료한 뒤 EXE만 교체합니다. 실제 Windows 화면에서 제목 표시줄·아이콘·창 크기 조절 등 시각 검수는 별도로 진행합니다.

- [메뉴 구성 및 데이터 보존](docs/PlayDock_Menu_Cleanup_20261124_KO.md)
- [UI 개선 내용](docs/PlayDock_UI_Polish_20261124_KO.md)
- [게임 정보 수집 흐름](docs/PlayDock_Collected_Game_Flow_KO.md)
- [다운로드 안내](docs/PlayDock_Windows_Download_Guide_KO.md)
- [변경 기록](CHANGELOG_KO.md)

## 독립 실험 기록

기존 게임 정체 판독기 실험은 `experiments/dlsite_detector/`에 보존합니다. 본체의 현재 공식 수집 방식과 과거 검색 실험 방식은 구분합니다.

- [2026-11-19 실험 인수인계 (과거 기록)](experiments/dlsite_detector/HANDOFF_2026-11-19_KO.md)
- [실험 파일 구조](experiments/dlsite_detector/FILE_MAP_KO.md)
- [실험 회귀 테스트 기준](experiments/dlsite_detector/REGRESSION_CHECKLIST_KO.md)
- [v0.1~v0.5 실험 개발 기록](experiments/dlsite_detector/README_KO.md)

## 개발 및 커밋 규칙

- 최신 통합 소스는 `main`을 기준으로 확인합니다. 기능 개발은 별도 브랜치에서 진행하고 검증 후 통합합니다.
- 커밋 제목은 변경한 내용을 한국어로 간단히 작성합니다. 불필요한 분류 접두사, 프로젝트명, 버전 반복은 생략합니다.
- 세부 구현 내용과 검증 결과는 커밋 본문에 남깁니다.
- 과거 커밋 및 독립 실험은 기존 작업 브랜치와 백업 브랜치에 보존합니다.
- 사용자 데이터·압축파일·개인 경로·자격증명은 커밋하지 않습니다.

## 소스코드 구성

- `src/playdock/ui/` — 화면, 공통 대화상자, 스타일
- `src/playdock/controllers/` — 사용자 동작 및 화면과 기능 연결
- `src/playdock/services/` — 압축 해제·설치·실행 파일 탐색·라이브러리 관리·작업 스레드
- `src/playdock/models/` — 게임 데이터 모델과 식별자
- `src/playdock/database/` — SQLite 작품 저장·조회
- `src/playdock/integrations/` — DLsite 외부 조회
- `src/playdock/core.py`, `src/playdock/work_db.py` — 이전 import 경로를 유지하는 호환 모듈
- `src/playdock/*.py` — 아직 분리되지 않은 이미지·이름 등 기능 모듈
- `app.py`, `title_editor.py`, `setup_wizard.py`, `uninstall_wizard.py` — 각 EXE 진입점
- `scripts/` — Windows 실행·빌드·공개 배포 스크립트
- `tests/` — 자동 테스트
- `docs/` — 한국어 문서 및 사용자 설명서

**중요:** 기존 `core`·`ui` 등 절대 임포트 호환성을 유지하기 위해 진입점과 테스트에서 `src/playdock`을 Python 검색 경로에 추가합니다. 다음 단계에서는 상대 임포트와 정식 패키징으로 이행할 수 있습니다.

## 개발 환경

```bash
python -m pip install -r requirements.txt pytest
python -m pytest -q tests
python app.py
```

Windows 빌드는 `scripts\00_BUILD_WINDOWS_EXE.bat`, 기존 EXE 재포장은 `scripts\01_REPACKAGE_EXISTING_EXES.bat`으로 실행할 수 있습니다. GitHub Actions에서는 main 및 지정 개발 브랜치에서 변경 시 Windows 테스트와 EXE 빌드를 실행할 수 있으며, 수동 실행도 지원합니다. 빌드 성공 여부는 해당 실행 결과에서 확인합니다.

개인 게임 목록, 압축파일, API 키, 이미지 캐시, 사용자 DB는 저장소에 업로드하지 않습니다.

자세한 파일별 역할은 [`docs/소스코드_구조_v0.8.4.md`](docs/소스코드_구조_v0.8.4.md)를 참고하세요.
