# 1-B 실제 기능 사용 관계 감사 — 2026-11-24

기준: af10566aeb5a066ac5ee9beb9565823b73895002. 본체와 기존 테스트/실험 파일은 수정하지 않았다. 감사 도구 및 추가 감사 전용 테스트만 추가했다.

## 현재 본체에서 보이는 실제 메뉴 (원본 파일 직접 확인)

| 진입 | 연결된 처리 함수 | 근거 |
|---|---|---|
| 게임 정보 수집 | collect_library_information | ui/launcher_layout.py:45 |
| 새로고침 | reload | ui/launcher_layout.py:50 |
| 기능 / 공식 배너·아이콘 적용 | identify_selected_game | controllers/window_actions.py:57 |
| 기능 / 공식 게임명 설정 | open_official_name_settings | controllers/window_actions.py:63–65 |
| 설정 / 폴더 설정 | folder_wizard | controllers/window_actions.py:16–17 |
| 설정 / 데이터 관리 | data_manager_dialog | controllers/window_actions.py:18–19 |
| 설정 / 라이브러리 속성 | library_info_dialog | controllers/window_actions.py:20–21 |
| 설정 / DB 상태 확인 | show_database_status | controllers/window_actions.py:23–24 |
| 게임 관리 / 수동 이름 | rename_selected_game | controllers/window_actions.py:95 |
| 게임 관리 / 수동 배너·아이콘 | change_image("hero"/"icon") | controllers/window_actions.py:100–101 |
| 게임 관리 / 실행 옵션 | edit_launch_options | controllers/window_actions.py:103 |
| 게임 관리 / 공식 페이지 | open_saved_official_page | controllers/window_actions.py:106 |

경로는 src/playdock 기준. QAction 연결을 테스트에서 직접 클릭/trigger하여 처리 함수로 전달되는지 확인한다. 외부 사이트/자격증명/실제 게임에는 접근하지 않는다.

## 기존 기능과 호환 모듈의 구분

| 대상 | 현재 본체 메뉴 | 추가 증거 | 판단 |
|---|---|---|---|
| collection_board.py (루트 모듈) | 직접 연결 없음 | ui/collection_board.py 재수출, tests/test_ui_package_v081.py의 호환 검사 | 호환 모듈 정리 후보. 실제 CollectionBoard 구현은 유지 |
| dark_selector.py | 직접 연결 없음 | ui/selectors.py 재수출, 동일 호환 테스트 | 호환 모듈 정리 후보. 실제 selector 유지 |
| online_art_dialog.py | 이전 인터넷 검색 메뉴 제거 | ui/artwork_dialog.py 재수출, 동일 호환 테스트 | 이전 검색 UI 묶음 정리 후보 |
| ui/artwork_dialog.py | 이전 검색 메뉴 제거 | test_search_only_ui.py에서 파일 직접 읽기, test_ui_package_v081.py에서 존재 검증 | 검색 UI 및 관련 테스트 계약 함께 검토 |
| services/artwork_workers.py | 이전 UI에서만 정적 도달 | SearchJob/DownloadJob/IdentityJob, old artwork dialog 참조 | 이전 UI와 함께 검토 |
| work_db_dialog.py | 직접 연결 없음 | ui/work_info_dialog.py 재수출, 호환 테스트 | 호환 모듈 정리 후보. 작품정보 구현 유지 |
| AI SettingsDialog | 현재 설정 메뉴 없음 | app.py:278 settings_dialog, tests/test_search_only_ui.py가 설정 폼 구조 검사 | UI 제거 후보, 자격증명과 기존 설정값 보존 |
| 기존 TitleEditor | 현재 네 가지 게임 관리 메뉴는 직접 호출하지 않음 | title_editor.py 진입점; controllers/metadata.py:255 open_title_editor; tests/test_title_editor_inprocess.py가 직접 호출 | 이전 독립/내부 편집기 유지 여부 결정 전 보류 |
| AI 추천·번역 | 본체 상단/게임 관리 메뉴 없음 | ui/editor_layout.py의 start_lookup('gpt'/'translate'), services/title_workers.py에서 실제 제공업체 호출 | 편집기와 함께 검토. ai_providers 통째 삭제 금지 |
| online_artwork.py | 이전 검색 UI와 별개로 필수 함수 사용 | services/official_artwork_service.py:16 download_image, crop_png; services/artwork_service.py:14 save_selected_art | 유지 및 이미지 핵심과 검색 분리 |
| artwork.py | 수동 이미지 선택 및 로컬 이미지 | controllers/game_actions.py:317 save_image; library/metadata의 discover_local; title_workers의 AI 함수 | 필수 기능 유지, AI 분리 검토 |
| 정식 정보수집 | 현행 버튼 | catalog_collection_service 및 identity_artwork_worker가 experiments/.../code_only.py 사용 | 엔진 독립화 필요, 삭제 금지 |

## 빌드와 의존성
- scripts/Build-Windows-Release.ps1:68 ai_providers.py 존재 확인, 111–114 keyring/pyzipper/send2trash/ddgs 수집 및 rarfile/game_codes 포함.
- scripts/build_setup_windows.bat:36도 keyring/pyzipper/send2trash 및 game_codes 포함. 배포 방식별 차이 존재.
- requirements.txt: PySide6, py7zr, Pillow, keyring, pyzipper, send2trash, rarfile, ddgs.
- 현재 공식 이미지 적용은 online_artwork의 안전한 다운로드/검증/자르기 기능을 사용한다. 검색 UI가 없어졌다는 이유로 전체 파일 또는 Pillow를 제거할 수 없다. ddgs 및 keyring도 남은 검색·이름 편집·자격증명·실험 경로 확인 후 판단.
- 기존 TitleEditor 별도 EXE는 공개 배포에서 제외되어도 소스 진입점 및 직접 호출 회귀 테스트가 남아 있다.

## 자동화
[사용 관계 감사 Actions](https://github.com/sanato-nb/PlayDock/actions/runs/45338115448)
- scripts/audit_usage.py: 기준 Git 객체 SHA 재검증, 전체 텍스트 참조, 97개 import 후보 교차검색, UI 콜백, 동일 함수 그룹 상세.
- tests/audit/test_usage_routes.py: 실제 메인 UI 메뉴 신호 및 이전 이름 편집기 AI 버튼 신호 검증 (사업 로직은 spy로 대체).
- 기존 메뉴/공식 이미지/이름 편집/DB/수집 테스트를 함께 실행.
- 현재 원본 SHA 및 본체 변경 없음 검증과 정적 교차 검색 단계는 성공. 실제 Qt 검증의 최종 결과는 Actions 실행 상태에서 확인한다.

## 후속 기준
미사용 후보는 아직 삭제하지 않는다. 1-C에서는 참조의 의미(실제 코드, 주석, 부정 검사, 재수출, 테스트 전용 계약)를 분류하고 제거 범위를 확정한다. 기존 사용자 설정·DB·파일·모음집 보존, 독립 실험 유지, 현재 메뉴 동작 유지. main 미변경.

## 실측 결과 및 재검증

- 텍스트 파일 326개 원본 SHA 확인 및 참조 검색 성공, 오류 0개.
- 본체 미사용 import 후보 97건 교차검색, UI 콜백 연결 구문 232개.
- 5개 동일 AST 함수 후보: 실험의 SQLite connect 1그룹, desktop_directory 1그룹, AI JSON 파서 1그룹, 테스트 fixture/생성자 2그룹. 기능 동일성 및 호출 차이를 확인하기 전 통합 금지.
- 첫 실행: 26 passed, 1 failed. 실제 메인 메뉴 11개 호출 검증은 성공. 추가 이전 편집기 감사 테스트의 설치 폴더 미생성으로 실패하여 테스트 준비 코드만 수정 (1723b7d).
- [첫 실행 상세 산출물](https://github.com/sanato-nb/PlayDock/actions/runs/45338115448/artifacts/14894716814)
- [보완 후 재검증 실행](https://github.com/sanato-nb/PlayDock/actions/runs/45338260678)
- 최종 Qt 재검증 성공 여부가 확인되기 전 1-B 전체를 완료로 표시하지 않는다.
