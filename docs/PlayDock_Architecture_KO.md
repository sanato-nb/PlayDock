# PlayDock 최신 소스 구조 및 유지보수 안내

기준 코드 ce6eed03a37e7eb620eb0e41fb043aa1c9cdbcf8 (Work 추가 최적화 포함). Python 3.12 / PySide6-Essentials / SQLite / Windows. 본체 파일 93개. 아래 구조는 기준 Git 트리와 일치한다. 구조 문서는 버전 번호를 추정하지 않으며, 공식 배포 버전 확정은 별도 작업이다.

## 최상위

```text
PlayDock/
├── app.py                 # 메인 창 실행
├── title_editor.py        # 기존 상세 이름 편집 창 (본체 내 호출 가능)
├── title_editor_entry.py  # 기존 이름 편집 진입점 호환
├── setup_wizard.py        # 설치기
├── uninstall_wizard.py    # 제거기
├── requirements.txt       # 런타임 의존성
├── assets/                # 앱 아이콘
├── src/playdock/          # 본체 기능 및 UI
├── tests/                 # 기능·회귀·최적화 검증
├── experiments/           # 독립 연구 도구 (본체 의존 0)
├── scripts/               # 실행·빌드·검증·독립 도구
├── docs/                  # 사용 및 개발 기록
└── .github/workflows/     # 자동/수동 검증과 배포
```

## 본체 파일별 역할

```text
src/playdock/
├── __init__.py  # 패키지 초기화
├── ai_providers.py  # 기존 선택적 텍스트 AI·자격증명 호환
├── artwork.py  # 로컬 이미지 탐색·저장 및 이전 텍스트 추천 호환
├── cache_management.py  # 캐시 관리 기존 import 호환
├── controllers/  # 화면 동작과 업무 기능 연결
│   ├── __init__.py  # 패키지 초기화
│   ├── catalog_collection.py  # 게임 정보 수집 연결
│   ├── data_manager.py  # 데이터 관리 연결
│   ├── game_actions.py  # 게임 설치·실행·제거 연결
│   ├── library.py  # 목록·검색·정렬·모음집 연결
│   ├── metadata.py  # 수동/공식 이름·이미지·공식 페이지 연결
│   ├── title_editor.py  # 기존 상세 이름 편집 동작
│   └── window_actions.py  # 상단 기능·설정·정렬 메뉴
├── core.py  # 기존 core import 재노출
├── data_management.py  # 데이터 백업·복원 기존 import 호환
├── database/  # SQLite 작품 데이터
│   ├── __init__.py  # 패키지 초기화
│   ├── official_catalog.py  # 공식 카탈로그 가져오기 및 검증
│   └── work_repository.py  # 작품/게임 연결 저장·조회·일괄 조회
├── game_identity.py  # 기존 게임 식별 지원
├── install_management.py  # 설치 위치·제거·Windows 등록
├── integrations/  # 외부 정보 조회
│   ├── __init__.py  # 패키지 초기화
│   ├── dlsite_client.py  # DLsite 작품 조회 및 응답 정리
│   └── official_lookup/  # 본체 독립 공식 검색 엔진
│       ├── __init__.py  # 패키지 초기화
│       ├── code_only.py  # 품번 기반 DLsite 우선·Steam 후순위
│       ├── detector.py  # 공식 작품 검증 및 기존 판독 지원
│       ├── no_api_html.py  # 공개 HTML 조회 지원
│       ├── search_terms.py  # 검색 제목 정리
│       └── steam_client.py  # Steam 공개 작품 조회
├── korean_title_search.py  # 기존 한국어 제목 검색
├── models/  # 데이터 모델·순수 목록 처리
│   ├── __init__.py  # 패키지 초기화
│   ├── collection_board.py  # 모음집 구성 인덱스
│   ├── game_codes.py  # 품번 해석 및 표시
│   ├── game.py  # 게임 모델·ID
│   └── library_tree.py  # 검색·정렬·그룹 구성
├── native_caption.py  # Windows 창 캡션 스타일
├── online_artwork.py  # 기존 이미지 후보·다운로드·크롭
├── product_titles.py  # 공식 품번과 제목 조회 지원
├── services/  # 실제 기능 처리
│   ├── __init__.py  # 패키지 초기화
│   ├── archive_service.py  # 압축 검증·해제·암호 처리
│   ├── artwork_service.py  # 이미지 저장·적용
│   ├── bulk_title_edit.py  # 일괄 제목 변경 규칙
│   ├── bulk_title_service.py  # 일괄 제목 적용 처리
│   ├── cache_service.py  # 캐시 검사 및 정리
│   ├── catalog_collection_service.py  # 공식 정보 수집·제외 프롬프트
│   ├── collection_service.py  # 모음집 관리 기능
│   ├── data_service.py  # 앱 데이터 백업·복원
│   ├── database_status_service.py  # DB 상태 집계
│   ├── install_service.py  # 게임 설치·안전한 제거
│   ├── launch_approval.py  # 실행 승인 확인
│   ├── launch_options.py  # 실행 인수 검증
│   ├── launch_service.py  # EXE 후보 및 실행 대상
│   ├── library_service.py  # 게임 스캔·메타데이터·표시 이름
│   ├── localized_titles.py  # 언어별 제목 선택
│   ├── official_artwork_service.py  # 검증된 공식 이미지 처리
│   ├── official_work_service.py  # 공식 작품 식별 및 메타 연결
│   ├── settings_service.py  # 설정 및 기존 자격증명 호환
│   └── simple_title_edit.py  # 수동 제목 변경 및 복원
├── storage/  # 사용자 데이터 경로 및 파일 저장
│   ├── __init__.py  # 패키지 초기화
│   ├── collections.py  # 모음집 JSON 저장
│   ├── local.py  # 설치 표식·데이터 위치·이전
│   └── setup_paths.py  # 초기 폴더 설정
├── title_translation.py  # 기존 텍스트 번역 지원
├── ui/  # 화면과 스타일
│   ├── __init__.py  # 패키지 초기화
│   ├── collection_board.py  # 모음집 카드 화면
│   ├── dialogs/  # 대화상자
│   │   ├── __init__.py  # 패키지 초기화
│   │   ├── cache_manager.py  # 캐시 관리 창
│   │   ├── caption.py  # 대화상자 제목줄
│   │   ├── catalog_collection.py  # 수집 진행 및 제외 목록
│   │   ├── collection_settings.py  # 모음집 설정
│   │   ├── common.py  # 공통 입력·확인 창
│   │   ├── data_manager.py  # 앱 데이터 관리
│   │   ├── database_status.py  # DB 상태
│   │   ├── file_dialog.py  # 어두운 파일 선택 창
│   │   ├── folder_settings.py  # 폴더 설정
│   │   ├── identity_artwork.py  # 공식 이미지 선택
│   │   ├── library.py  # 라이브러리 속성
│   │   ├── title_preview.py  # 제목 미리보기
│   │   └── title.py  # 공식 제목 설정
│   ├── editor_layout.py  # 기존 상세 이름 편집기 UI
│   ├── launcher_layout.py  # 메인 화면 배치
│   ├── selectors.py  # 공통 선택 위젯
│   ├── styles.py  # QSS 테마
│   ├── widgets/  # 재사용 위젯
│   │   ├── __init__.py  # 패키지 초기화
│   │   ├── artwork_cache.py  # Qt 이미지 디코딩 캐시
│   │   ├── game_icons.py  # 아이콘 표시
│   │   └── launcher.py  # 메인 화면 위젯
│   └── work_info_dialog.py  # 작품 확인 창
├── work_db.py  # 기존 공식 DB import 호환
└── workers/  # Qt 백그라운드 작업
    ├── __init__.py  # 패키지 초기화
    ├── catalog_collection.py  # 공식정보 수집 스레드
    ├── game_tasks.py  # 설치·제거 스레드
    ├── identity_artwork.py  # 공식 이미지 조회 스레드
    ├── title.py  # 제목 작업 스레드
    └── work_lookup.py  # 작품 조회 스레드
```

## 기능 수정 시 찾아갈 위치

| 기능 | 우선 확인할 파일 (src/playdock 기준) |
|---|---|
| UI 배치/디자인 | ui/launcher_layout.py, ui/styles.py (사용자 승인 없이 변경 금지) |
| 상단/상세 메뉴 | controllers/window_actions.py, controllers/metadata.py |
| 목록 및 새로고침 | controllers/library.py, services/library_service.py, models/library_tree.py |
| 공식 정보 수집 | controllers/catalog_collection.py, workers/catalog_collection.py, services/catalog_collection_service.py, integrations/official_lookup/code_only.py |
| 작품 DB | database/work_repository.py, services/official_work_service.py |
| 이름 변경 | services/simple_title_edit.py, services/bulk_title_service.py, workers/title.py |
| 배너·아이콘 | services/official_artwork_service.py, artwork.py, ui/widgets/artwork_cache.py |
| 모음집 | storage/collections.py, models/collection_board.py, controllers/library.py |
| 압축·설치·실행 | services/archive_service.py, services/install_service.py, services/launch_service.py, services/launch_options.py |
| 앱 데이터 | storage/local.py, storage/setup_paths.py, services/data_service.py |
| 파일 선택 창 | ui/dialogs/file_dialog.py, ui/dialogs/caption.py |
| 배포 | scripts/Build-Windows-Release.ps1, setup_wizard.py, uninstall_wizard.py |

UI → Controller → Service/Worker → Model/Database/Storage/Integration이 목표 경계다. 실제 일부 기존 UI와 호환 모듈은 직접 서비스 호출을 유지한다. 완벽한 단방향 계층이라고 단정하지 않는다. 기존 core/work_db 및 cache_management/data_management 재노출 경로는 기존 호출을 유지하기 위한 것이다. 절대 import 호환 검색 경로 유지.

## 데이터 보존

설치 표식이 있는 본체 옆 data/에 settings.json, collections.json, manual_games.json, product_titles.json(사용 시), playdock.db, cache/게임ID/meta.json·hero.png·icon.png, backups/, logs/를 유지한다. 앱 데이터 백업은 게임 세이브 백업과 다르다. 사용자 지정 경로, 공식 DB 링크, 수동 제목과 복원 이력, 모음집, 실행 옵션, 이미지 원본을 유지한다. 원본 압축 및 설치 게임 폴더는 본체 데이터와 별개다. 현재 DB 스키마 3을 임의 변경하지 않는다.

## 개발 및 배포

Windows에서 `python -m pip install -r requirements.txt pytest`, `python -m pytest -q`, `python app.py`. 기존 import 경로를 위해 진입점과 테스트 설정을 유지한다. 정식 빌드: `scripts/00_BUILD_WINDOWS_EXE.bat` 또는 `./scripts/Build-Windows-Release.ps1 -NoLaunch -NoWinget`. 결과는 PlayDock.exe, PlayDock_Setup.exe, PlayDock_Uninstall.exe와 체크섬/ZIP. 설치된 앱에는 Python 불필요. 개인 데이터/키/절대 경로 포함 금지.

Windows 일반 검증: source-final-feature-review.yml (전체 pytest 1회, JUnit 기능별 요약, 동일 venv 정식 빌드, EXE 내부 검사와 격리 실행). UI 비교: source-ui-reference.yml. 원본 대비 잔존 감사: source-final-residual.yml. 이전 데이터 호환: source-upgrade-compatibility.yml. 공개 배포: build-windows-exe.yml (수동). Linux 회귀: python-tests.yml. 이전 세부 벤치마크는 수동 실행으로 보존. 검증 이력과 독립 실험은 삭제하지 않는다.

## 수정 원칙

UI 기준 84bbde0 및 38개 보호 SHA 유지. 자동 비교 14 화면 일치, 실제 Windows 글꼴·프레임은 별도 확인. 기능을 변경할 때 해당 기능 테스트와 전체 회귀를 통과해야 한다. 새로운 기능이나 자동 업데이트, 게임 세이브 백업, 플레이타임, 통계, 생성형 이미지 도입 금지. 기존 선택적 텍스트 AI/검색 및 설정 호환은 현재 남아 있어 사용자 승인 없이 삭제하지 않는다. 원본 데이터·DB 마이그레이션은 별도 검토. main은 검증 및 통합 결정 전 변경하지 않는다.
