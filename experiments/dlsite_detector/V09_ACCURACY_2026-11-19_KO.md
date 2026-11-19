# PlayDock v0.9 — 독립 게임 정체 판독기 정확도 개선 보고 (2026-11-19)

## 목적과 실제 입력
- v0.8 독립 판독기 129개 압축파일 검사 JSON의 **오판 가능 근거**를 확인하여 개선.
- 사용자는 처리시간보다 잘못된 게임/상품 선택의 방지를 우선.
- 공개 저장소에는 사용자 JSON·게임 이름 목록·내부 상대 경로·API 키를 넣지 않고 **합성 게임 명칭/모의 인터넷 결과만** 테스트함.
- 실제 129개에 대해 v0.9 실행을 다시 수행하지 않았으므로 정답률/오탐률 향상치는 아직 측정할 수 없음.

## 개발한 기능
1. `archive_inspector.py` — 모든 EXE를 제목 후보로 보지 않고 전체 목록 수집 후 EXE 경로·Unity 동일 이름 `*_Data` 연결·Unreal Shipping 이름을 판별함. `pythonw`, `createdump`, `zsync`, `CrashReportClient`, `OpenSaveFolder`, `Uninstaller` 등 런타임/보조 도구의 검색을 줄이고, BepInEx/MonoBleedingEdge/Engine/bonus/CG 폴더 이름을 작품 후보에서 제외함. EXE 바이너리 내용은 읽지 않음.
2. `pipeline.py` — 일반 웹 검색 결과에서 연결된 긴 다중 사이트 제목은 정확한 제목 일치/게임 콘텍스트로 사용하지 않음. 원본 웹 증거(제목/URL)는 JSON에서 확인 가능하게 보존함.
3. `identity_matcher.py` — 같은 제목 정규화 결과가 나오더라도 정확한 대표 제목이 다른 후보의 공식 작품번호를 잘못 복사하지 않게 후보별로 구분함.
4. `identity_verifier.py`, `verification_report.py` — 공식 작품번호가 여러 개이고 그중 하나는 명시적 번역 패치, 다른 하나는 동일한 원제 기반의 게임 상품인 경우 `related_products_review`와 `candidate_relationships`에 **미확인 관련 상품 가설**을 남김. ID는 별도로 유지하며 `matched`나 `automatic_binding_allowed`를 올리지 않음. 무관한 별개 공식 ID는 계속 `conflicting_official_ids`로 분류함.
5. `metadata_fields.py` — README 라벨 `品番: RJ...` 형식을 지원, README 내용 2개 제한 유지.
6. `scripts/game_identity_tester.py` — `0.9-test` 버전 및 `[서로 다른 외부 상품의 관계 (미확인)]` 표시. 여전히 PlayDock 전체 프로그램과 완전히 분리된 검증기.

## 테스트
- 합성 ZIP·모의 웹 조회 기반 `tests/test_v09_accuracy_experiment.py`의 9개 테스트 추가.
- 전체 회귀 테스트 621개 통과: https://github.com/sanato-nb/PlayDock/actions/runs/44453760922
- Windows 수동 빌드 워크플로: `.github/workflows/identity-tester-windows.yml`.
- 원본 ZIP/7z/RAR 수정, 게임 실행, 사용자의 PlayDock DB 변경, 인증 키 배포 없음.

## 다음 검증
- 같은 사용자의 129개 검사 파일을 v0.9 EXE로 다시 실행하고 *파일별* v0.8/v0.9 결과를 비교.
- **오판 확인:** 작품 번호가 서로 다른 공식 상품, 한·영·일 별칭 관계, 별도 판매 패치와 원작, 여러 게임 실행파일이 공존할 때 판정의 안정성.
- 공식 링크·원작/패치 관계 증명이 없는 항목을 자동 확정하지 말 것.
