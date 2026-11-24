# 1-C 본체 소스 정리 대상 분류 — 2026-11-24

기준: af10566aeb5a066ac5ee9beb9565823b73895002
1-B 재검증: [27 passed](https://github.com/sanato-nb/PlayDock/actions/runs/45338260678), [참조 증거](https://github.com/sanato-nb/PlayDock/actions/runs/45338260678/artifacts/14895335712).
범위: src/playdock의 추적 Python 파일 84개 전체. 각 파일에 하나의 우선 작업 분류를 지정한다. 정적 조사 및 직접 확인한 코드/테스트/빌드 근거에 기반한 정리 계획이며, 삭제 승인 또는 성능 개선의 증명은 아니다. 보류는 유지 원칙으로 취급한다.

## 분류 집계
| 분류 | 파일 수 |
|---|---:|
| 유지 | 32 |
| 보류 | 10 |
| 분리·통합 | 13 |
| 이동 | 18 |
| 삭제 후보 | 6 |
| 최적화 | 5 |
| 합계 | 84 |

## 파일별 판정
| 경로 (src/playdock/) | 분류 | 역할 및 근거 | 후속 처리 |
|---|---|---|---|
| `__init__.py` | 유지 | 패키지 초기화 | 현 위치 유지 |
| `ai_providers.py` | 보류 | AI 제공업체·자격증명 및 이전 이름 편집기 연결 | 기존 편집기 정책 결정 후 분리; 설정값·키 삭제 금지 |
| `artwork.py` | 분리·통합 | 수동 이미지 저장·로컬 이미지 탐색과 AI 기능 혼재 | 이미지 서비스와 이전 AI 기능 분리; save_image/discover_local 유지 |
| `bulk_title_edit.py` | 이동 | 일괄 이름 변경 및 복원·백업 | services/title_edit_service.py 또는 기존 bulk_title_service 통합 검토 |
| `cache_management.py` | 보류 | 캐시 호환 재수출 | 호환 테스트·호출 변경 전 유지 |
| `collection_board.py` | 삭제 후보 | 현재 UI 구현의 이전 import 경로 | ui/collection_board.py 유지; 호환 계약 변경과 테스트 검증 후 제거 |
| `collection_board_model.py` | 이동 | 모음집 카드 데이터 계산 | models/collection_board.py |
| `controllers/__init__.py` | 유지 | 패키지 초기화 | 유지 |
| `controllers/catalog_collection.py` | 유지 | 수집 버튼·진행·완료 연결 | 유지; 워커 import 갱신만 |
| `controllers/data_manager.py` | 유지 | 데이터 관리 요청 연결 | 유지 |
| `controllers/game_actions.py` | 분리·통합 | 설치·실행·세이브·이미지 UI 동작 | 세이브 및 실행/이미지 처리 경계 검토; 안전 승인 유지 |
| `controllers/library.py` | 최적화 | 목록·선택·모음집·화면 갱신 | 합성 목록에서 검색/정렬/선택/DB 접근 측정; 동작 유지 |
| `controllers/metadata.py` | 분리·통합 | 작품정보·이름·공식 이미지·이전 편집기 혼재 | 현재 이름/공식 이미지/작품 조회의 책임 분리; 이전 진입점은 보류 |
| `controllers/title_editor.py` | 보류 | 이전 이름 편집기 직접 실행 및 AI 연결 | 27개 검증에서 버튼 연결 확인; 별도 제거 정책 없으면 유지 |
| `controllers/window_actions.py` | 최적화 | 상단 메뉴 상태 및 선택 동기화 | function_availability의 반복 DB 조회 측정; 상태 판정 동일 |
| `core.py` | 보류 | 게임/서비스 호환 import | 호출부 이전 및 테스트 계약 확인 전 유지 |
| `dark_selector.py` | 삭제 후보 | 선택 UI 호환 모듈 | ui/selectors.py 유지; 호환 검사 변경 후 제거 검토 |
| `data_management.py` | 보류 | 데이터 관리 이전 import | 백업·복원 호환 계약 확인 전 유지 |
| `database/__init__.py` | 유지 | 패키지 초기화 | 유지 |
| `database/official_catalog.py` | 분리·통합 | DB 위치·이전 경로·공식 식별 검증 | 공식 코드 검증과 저장 경로 경계 정리; 기존 DB 위치 유지 |
| `database/work_repository.py` | 최적화 | 스키마·마이그레이션·저장·조회 | 연결 수/조회시간 측정; 스키마 및 데이터 마이그레이션 유지 |
| `game_codes.py` | 이동 | 품번 정규화 | models 또는 공통 코드 모듈; 빌드 hidden-import 및 실험 참조 갱신 |
| `game_collections.py` | 이동 | 모음집 저장 및 조회 | storage/collections.py; 기존 JSON 스키마 유지 |
| `game_icons.py` | 이동 | 게임 아이콘 처리 | ui/widgets 또는 이미지 서비스로 책임 기준 재배치 |
| `game_identity.py` | 보류 | 이전 식별 및 AI/검색 연계 | 이전 검색 UI와 실험·테스트 참조 구분 후 처리 |
| `install_management.py` | 분리·통합 | Windows 프로그램 설치·레지스트리·제거 | 설치 계층 이동 및 desktop_directory 통합; 기존 삭제 방어 유지 |
| `integrations/__init__.py` | 유지 | 패키지 초기화 | 유지 |
| `integrations/dlsite_client.py` | 유지 | 공식 DLsite 요청·응답 검증 | 유지; 공통 정식 조회 엔진과 경계 확정 |
| `korean_title_search.py` | 보류 | 이전 이름 편집기의 한국어 검색 | 편집기 및 테스트 계약 유지 |
| `launch_approval.py` | 이동 | 실행 승인·변경 판정 | services/launch_approval.py; 승인 동작 유지 |
| `launch_options.py` | 이동 | 실행 인수 검증 | services/launch_options.py; 명령어 검증 유지 |
| `library_tree.py` | 이동 | 라이브러리 그룹 구성 | models/library_tree.py |
| `local_storage.py` | 이동 | 프로그램 데이터 위치·기존 데이터 이전 | storage/local.py; 마이그레이션 경로 그대로 |
| `localized_titles.py` | 이동 | 언어별 제목 처리·조회 | services/localized_titles.py 또는 integration 경계; 기존 언어 데이터 유지 |
| `models/__init__.py` | 유지 | 패키지 초기화 | 유지 |
| `models/game.py` | 유지 | Game 모델·ID·안전한 이름 | 유지 |
| `native_caption.py` | 유지 | Windows 및 설치기 제목 표시줄 | 최신 검증된 동작 유지 |
| `online_art_dialog.py` | 삭제 후보 | 이전 인터넷 이미지 검색 UI 호환 모듈 | 이전 검색 UI 세 파일 묶음으로 검토; 외부 import 계약 검증 |
| `online_artwork.py` | 분리·통합 | 안전한 다운로드·검증·자르기와 웹 검색 혼재 | 이미지 핵심 기능 유지; 검색부 별도 분리 후 사용 여부 검증 |
| `product_titles.py` | 분리·통합 | 품번·표시명 처리 및 공식 제목 조회 | 순수 제목 처리와 외부 요청 분리; DB의 clean_title 유지 |
| `save_backups.py` | 이동 | 세이브 백업·복원 | services/save_backup_service.py; 경로/ZIP 안전 유지 |
| `services/__init__.py` | 유지 | 패키지 초기화 | 유지 |
| `services/archive_service.py` | 유지 | 압축 처리 및 안전 검사 | 유지; 성능은 별도 벤치마크 |
| `services/artwork_service.py` | 유지 | 이미지 저장·백업 | 유지; 이미지 공통부 import 변경만 |
| `services/artwork_workers.py` | 삭제 후보 | 이전 인터넷 이미지 검색 UI 전용 스레드 | ui/artwork_dialog.py와 함께 검토; 기존 공식 worker 유지 |
| `services/bulk_title_service.py` | 분리·통합 | 일괄 제목 변경 동작 및 검증 | bulk_title_edit 순수 함수와 책임 통합 검토 |
| `services/cache_service.py` | 유지 | 이미지 캐시 관리 | 유지 |
| `services/catalog_collection_service.py` | 분리·통합 | 품번 사전 필터·DB 수집·AI 인계·실험 의존 | 정식 공식 조회 엔진 독립; 프롬프트 및 검증 데이터 유지 |
| `services/catalog_collection_worker.py` | 이동 | 수집 Qt 작업 스레드 | workers/catalog_collection.py |
| `services/collection_service.py` | 유지 | 모음집 변경 처리 | 유지 |
| `services/data_service.py` | 유지 | 데이터 백업/복원 및 무결성 | 유지; 백업 포맷 보존 |
| `services/database_status_service.py` | 유지 | 읽기 전용 DB 상태 확인 | 유지 |
| `services/identity_artwork_worker.py` | 이동 | 공식 이미지 작업 스레드 | workers/identity_artwork.py; 실험 의존은 별도 독립화 |
| `services/install_service.py` | 유지 | 게임 설치 및 제거 | 경로 안전 및 휴지통 처리 유지 |
| `services/launch_service.py` | 유지 | 실행 파일 탐색 및 선택 | 유지 |
| `services/library_service.py` | 최적화 | 스캔·메타데이터·설정 읽기 | 스캔 및 JSON 읽기 측정; 캐시 무효화 검증 후 최적화 |
| `services/official_artwork_service.py` | 유지 | 공식 이미지 후보·다운로드·검증 | 유지; 안전 URL 및 사용자 선택 유지 |
| `services/official_work_service.py` | 최적화 | 확인된 작품 연결 및 화면 정보 | 반복 조회·배치 조회 측정; 확인 연결 정책 유지 |
| `services/settings_service.py` | 분리·통합 | 폴더 설정과 AI 제공업체 저장 혼재 | 폴더 설정 유지; 이전 AI 설정 분리 |
| `services/title_workers.py` | 이동 | 단일/일괄 제목 조회 Qt 스레드 | workers/title.py; BulkTitleWorker db_only 유지; 이전 AI 모드 보류 |
| `services/work_lookup_worker.py` | 이동 | 작품 조회 Qt 스레드 | workers/work_lookup.py; 기존 경로 확인 |
| `services/workers.py` | 이동 | 설치·제거·세이브 Qt 스레드 | workers/game_tasks.py |
| `setup_paths.py` | 이동 | 초기 폴더 제안 및 저장 | storage/setup_paths.py; 설치 마법사 빌드 참조 유지 |
| `simple_title_edit.py` | 이동 | 수동 표시 이름 저장/복원 | services/simple_title_service.py; 원본명/히스토리 보존 |
| `title_translation.py` | 보류 | 이전 AI 텍스트 번역 | 이전 이름 편집기 정책 결정 전 보존 |
| `ui/__init__.py` | 유지 | 패키지 초기화 | 유지 |
| `ui/artwork_dialog.py` | 삭제 후보 | 현재 메뉴에서 제거된 인터넷 이미지 검색 창 | 관련 호환 모듈/스레드와 함께 검토; 현재 공식 이미지 창 유지 |
| `ui/collection_board.py` | 유지 | 내 모음집 실제 UI | 유지 |
| `ui/dialogs/__init__.py` | 유지 | 패키지 초기화 | 유지 |
| `ui/dialogs/catalog_collection.py` | 유지 | 정보 수집 진행 및 TXT 내보내기 | 유지 |
| `ui/dialogs/common.py` | 분리·통합 | 공통 창·파일 선택·네이티브 캡션 혼재 | file_dialog.py와 공통 창 분리; 검수된 캡션 동작 유지 |
| `ui/dialogs/database_status.py` | 유지 | DB 상태 창 | 유지 |
| `ui/dialogs/identity_artwork.py` | 유지 | 공식 이미지 체크박스 미리보기 | 유지 |
| `ui/dialogs/library.py` | 분리·통합 | 폴더·모음집·캐시·데이터·이전 AI 설정 창 | 기능별 창 분리; 이전 AI 설정 제거는 별도 계약 확인 |
| `ui/dialogs/title.py` | 분리·통합 | 제목 미리보기·선택·저장 UI 혼재 | 미리보기/선택 UI 유지; 서비스 책임 정리 |
| `ui/editor_layout.py` | 보류 | 이전 이름 편집기 UI | 직접 실행 경로 및 AI 버튼 유지 여부 결정 전 보존 |
| `ui/launcher_layout.py` | 유지 | 검수된 메인 UI 배치 | 디자인·버튼 연결 유지 |
| `ui/selectors.py` | 유지 | 공통 선택 메뉴 구현 | 유지 |
| `ui/styles.py` | 유지 | QSS 스타일 | 디자인 유지; 불필요한 스타일은 사용 추적 후 정리 |
| `ui/widgets/__init__.py` | 유지 | 패키지 초기화 | 유지 |
| `ui/widgets/launcher.py` | 유지 | 메인 UI 공통 위젯 | 유지 |
| `ui/work_info_dialog.py` | 유지 | 작품정보 미리보기 및 호환 재수출 | 현재 코드 참조 유지 |
| `work_db.py` | 보류 | 이전 DB API 호환 재수출 | DB 호출부 전환 후 호환 검사 |
| `work_db_dialog.py` | 삭제 후보 | 이전 DB 창 import 호환 모듈 | ui/work_info_dialog.py 유지; 호환 계약 검토 |

## 진입점 및 지원 영역
app.py는 유지하며 미사용 import를 검토한다. setup_wizard.py/uninstall_wizard.py는 유지하고 설치 공통 함수 중복만 검토한다. title_editor.py/title_editor_entry.py는 직접 실행 및 테스트 계약 때문에 보류한다. refactor_test_support.py와 기존 테스트·실험·빌드 도구는 보존하고 변경 시 실제 참조를 업데이트한다. 이 표의 84개에는 포함하지 않는다.

## 구현 순서 및 검증
1. 2-A: 명확한 불필요 import부터 정리 (97건 후보는 재수출·테스트/빌드 참조·동적 사용을 확인하고 개별 판정). 기존 메인 메뉴 및 이름 편집기 계약 유지.
2. 2-B: 이전 인터넷 검색 UI 3개 파일(online_art_dialog.py, ui/artwork_dialog.py, services/artwork_workers.py), 호환 재수출 3개 파일을 그룹별로 검토. 테스트 계약 변경 사유를 기록. online_artwork.py의 download_image/crop_png/save_selected_art는 삭제 금지.
3. 2-C: AI 이미지 생성 및 보이지 않는 AI 설정 정리 후보 검토. 이전 이름 편집기, AI 텍스트 기능, keyring 등은 현재 유지/보류. 기존 사용자 자격증명·설정값 삭제 금지.
4. 3단계: worker 5개 이동, 계층 밖 파일 이동·역할 분리, 정식 공식 조회 모듈과 실험 경계 독립. 실험 원본 및 독립 실행 유지. 순환 import 및 PyInstaller 경로 검증.
5. 4–6단계: 중복 함수 및 반복 DB 조회/JSON/이미지 로딩 최적화, 합성 데이터 성능 측정, 의존성/EXE 크기 비교.
6. 7단계: 기존 Windows 1101 passed/1 skipped 기준 및 추가 감사 테스트, 전체 빌드와 실사용 UI 검수. 사용자 데이터, 압축파일, 설정/모음집/DB 스키마 보호.

## 완료 기준
- 기준 Git 트리의 84개 파일에 대해 경로 중복·누락 0, 각 행의 blob SHA 일치.
- 1-A 정적 감사 및 1-B 27개 Qt 회귀 확인.
- 1-C 계획 문서 및 JSON 저장. 실행 성능 측정은 아직 하지 않음.
- 운영 파일 변경·삭제 없음. 이후 구현 단계에서만 소스 변경.
