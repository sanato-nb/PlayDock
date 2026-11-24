# 1단계 정적 감사 실측 결과 — 2026-11-24

기준 소스: af10566aeb5a066ac5ee9beb9565823b73895002
원본 트리: b5868ab60bf859a9bd807fd6f8ee5f917c18bc8f
감사 도구 커밋: 1d0ff2c7d138cc8ab754e292680dc05712233379

- [성공한 감사 Actions](https://github.com/sanato-nb/PlayDock/actions/runs/45337242068)
- [전체 인벤토리 JSON 및 파일별 분류 보고서](https://github.com/sanato-nb/PlayDock/actions/runs/45337242068/artifacts/14893074992)
- 기준 Windows 검증: 1101 passed, 1 skipped, EXE 73.1 MB ([실행 결과](https://github.com/sanato-nb/PlayDock/actions/runs/45334982495)).

## 실측
- 추적 파일 332개.
- Python 261개 모두 원본 Git 객체 SHA 확인 및 AST 파싱 성공 (오류 0).
- 본체 84개, 12,332줄.
- 본체 미사용 import 후보 97건.
- 본체 직접 실험 의존 3개 연결, 진입점에서 정적 도달한 실험 모듈 5개.
- 전체 저장소 동일 AST 함수 본문 후보 그룹 5개. 중복 삭제 확정 아님.

| 계층 | 파일 | 줄 | 바이트 |
|---|---:|---:|---:|
| controllers | 8 | 1945 | 89215 |
| core-root | 31 | 3086 | 140445 |
| database | 3 | 657 | 30090 |
| experiments | 52 | 10582 | 493736 |
| integrations | 2 | 168 | 7126 |
| models | 2 | 45 | 1459 |
| root | 6 | 1135 | 47653 |
| scripts | 19 | 4856 | 230468 |
| services | 21 | 2381 | 106917 |
| tests | 100 | 16486 | 688081 |
| ui | 17 | 4050 | 187226 |

## 실제 확인된 실험 의존
- controllers/metadata.py → experiments/dlsite_detector/code_only.py
- services/catalog_collection_service.py → experiments/dlsite_detector/code_only.py
- services/identity_artwork_worker.py → experiments/dlsite_detector/code_only.py

정식 엔진을 integrations 또는 services로 이동할 때 기존 실험 도구 및 빌드 참조를 함께 검증한다.

## 진입점 정적 미도달 후보 (삭제 확정 아님)
| 본체 파일 (src/playdock/) | 정적 역참조 | 후속 작업 |
|---|---|---|
| collection_board.py | 없음 | 호환용 import 경로 및 소스 검사 테스트 확인 |
| dark_selector.py | 없음 | 호환용 import 경로 확인 |
| online_art_dialog.py | 없음 | 이전 이미지 검색 UI 호출 및 빌드 참조 확인 |
| services/artwork_workers.py | ui/artwork_dialog.py | 이전 UI와 함께 실제 도달성 검토 |
| ui/artwork_dialog.py | online_art_dialog.py | 이전 검색 UI 및 관련 테스트 확인 |
| work_db_dialog.py | 없음 | 기존 작품 DB 대화상자 import 호환 확인 |

## 진행 판정
- 1-A 전체 목록, SHA, AST 및 정적 의존 관계: 완료.
- 1-B 실제 메뉴와 동적 호출, 빌드/문자열 참조, 테스트 전용 API 교차 검증: 미완료.
- 1-C 파일·함수별 최종 유지/이동/통합/삭제 후보 분류: 미완료.
- 실행 성능, 메모리 및 EXE 최적화 효과: 미측정.

정적 import 그래프는 실제 사용 여부의 증명이 아니다. 97개 import, 6개 미도달 파일, 5개 동일 본문 그룹을 자동 삭제하지 않는다. 운영 소스, 데이터, DB, 게임 압축파일 및 main 변경 없음.
