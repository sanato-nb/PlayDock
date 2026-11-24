# 2-B 이전 이미지 검색 UI 및 호환 모듈 정리

기준: 3814e2360f2638f5a56b318f444f50fb47a6dc52 (2-A 전체 Windows 검증 1103 passed, 1 skipped).
삭제 커밋: e39430e1340bda4b1a8b70dcf691ef93533c735d.

## 삭제 범위

- src/playdock/online_art_dialog.py
- src/playdock/ui/artwork_dialog.py
- src/playdock/services/artwork_workers.py
- src/playdock/collection_board.py
- src/playdock/dark_selector.py
- src/playdock/work_db_dialog.py

이전 검색 UI는 현재 메인 메뉴에 연결되어 있지 않으며, 세 호환 모듈은 현재 정식 UI 구현을 단순 재수출했다. 1-B 참조 증거와 실제 소스 테스트를 대조하여 삭제했다. Git 기록은 유지한다.

## 보존

- ui/collection_board.py, ui/selectors.py, ui/work_info_dialog.py 및 공식 작품 이미지 UI/worker/service.
- online_artwork.py 전체: 다운로드, 검증, 자르기, 저장 및 이전 검색 알고리즘은 이번 단계에서 변경하지 않음.
- artwork.py, game_identity.py, AI 설정/이름 편집기, 사용자 자격증명과 데이터, 모든 독립 실험 및 기존 빌드 의존성.
- 실제 원본 기능 소스는 6개 삭제 외 변경하지 않는다.

## 테스트 계약 변경

test_ui_package_v081은 현재 정식 경로를 직접 import하고 제거 경로의 부재를 검증한다. test_dark_dropdown은 현행 제목 선택 메뉴 및 실제 DarkMenuSelect를 검사한다. test_search_only_ui의 사용하지 않는 파일 읽기를 제거한다. test_ui_business_boundaries_v086은 현재 공식 이미지 UI/Controller/Service의 책임 경계를 검증한다. test_chapter_title_search_v069, test_crop_drag_and_product_codes, test_game_identity_pipeline, test_identity_accuracy_v067의 폐기 UI 전용 검사는 현재 공식 이미지 선택 계약으로 교체한다. 기존 검색 및 이미지 자르기 알고리즘 테스트는 유지한다. test_worker_settings_separation_v085은 현재 공식 이미지 작업자와 DB 작업자를 검증한다. 테스트 파일 9개 변경, 테스트 개수 감소를 목적으로 삭제하지 않았다.

## 검증

scripts/audit_legacy_ui_cleanup.py는 기준 Git 트리 대비 삭제 집합 정확성, 나머지 본체 SHA 동일, 실험 파일 보존, 제거 모듈 직접 import 유무를 검증한다. Windows 전체 테스트 실행 전 결과를 확인한다. 2-A 검증 워크플로는 해당 스냅샷을 수동 재현하도록 고정했다. 검증 성공 전 main에는 병합하지 않는다.

## 최종 검증 완료

[Windows 실행 45339885719](https://github.com/sanato-nb/PlayDock/actions/runs/45339885719): 1103 passed, 1 skipped. 6개 파일·605줄 제거, 나머지 본체/진입점 84개 SHA 보존, 제거 모듈 직접 import 0. [산출물](https://github.com/sanato-nb/PlayDock/actions/runs/45339885719/artifacts/14894664528). 2-B 완료.
