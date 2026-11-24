# 3-B 계층 밖 기능 파일 재배치

기준: 1c3fe1567eefadabb83039cf3491e075a3ed8e2a. 3-A 전체 Windows 회귀 1100 passed, 1 skipped 및 EXE 빌드 성공.

13개 최상위 모듈을 아래 위치로 옮겼다. 기존 이름의 중복 구현이나 호환 모듈을 추가하지 않는다.

| 기존 | 신규 |
|---|---|
| local_storage.py | storage/local.py |
| setup_paths.py | storage/setup_paths.py |
| game_collections.py | storage/collections.py |
| collection_board_model.py | models/collection_board.py |
| library_tree.py | models/library_tree.py |
| game_codes.py | models/game_codes.py |
| game_icons.py | ui/widgets/game_icons.py |
| launch_approval.py | services/launch_approval.py |
| launch_options.py | services/launch_options.py |
| save_backups.py | services/save_backups.py |
| simple_title_edit.py | services/simple_title_edit.py |
| bulk_title_edit.py | services/bulk_title_edit.py |
| localized_titles.py | services/localized_titles.py |

본체 및 진입점의 import, 테스트 경로, Windows 빌드의 필수 파일 및 hidden-import를 변경한다. 데이터 위치 계산, 설정 형식, DB, 모음집, 이름 히스토리, 실행 승인, 백업 안전 처리, 원본 압축파일은 변경하지 않는다. 사용자 데이터에는 접근하지 않는다. 독립 실험과 기존 호환 모듈(core.py 등)은 보존한다. 모듈 내부 import 경로 이외의 AST 동일성, 이전 경로 잔존 및 전체 Windows 테스트·EXE 빌드 검증 후 완료 판정한다.
