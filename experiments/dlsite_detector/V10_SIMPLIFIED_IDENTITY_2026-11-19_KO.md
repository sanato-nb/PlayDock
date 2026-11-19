# PlayDock v0.10 — 게임 이름·품번만으로 정체 판독 (2026-11-19)

## 사용자 요구와 실제 범위
- 속도보다 정확도를 우선하고 판독 입력을 **게임 이름과 선택적 상품번호(RJ/BJ/VJ/EJ, 명시적 Steam App ID)**로 축소.
- 압축파일명·최상위 폴더명·복수 실행파일 중 근거가 있는 주 EXE명·README의 명시적 라벨만 수집.
- 암호 파일은 압축파일명만 사용. 게임 실행/전체 해제/EXE·INI·JSON·엔진 파일 내용 읽기 없음.
- 엔진·파일 크기·버전·한글화/번역·DLC는 정체 판단에서 **사용하지 않음**. 이후 다른 단계에서만 검사.
- 외부에는 *검색어*만 전달. 경로/원본 파일 본문/사용자 결과 JSON을 GitHub에 업로드하지 않음.

## 새 파일
- `experiments/dlsite_detector/simple_identity.py`: 이름·품번 근거 수집, 신뢰할 수 있는 유일 EXE 후보 추정, 보류 근거, 검색 요청 생성, 외부 공식 작품명·상품번호 교차 평가.
- `scripts/simple_identity_tester.py`: 독립 Tk GUI. 정밀검색 기본/빠른 검색 옵션, 진행바, 전체/보류 탭, 미확인 재검색, JSON `files` + `unresolved`.
- `tests/test_v10_minimal_identity_experiment.py`: 합성 압축으로 다중 EXE, 보조 EXE 제외, README, 코드 충돌, 품번 없는 게임, 암호화, 검색 장애, 오프라인, 파일 본문 미조회, 자체진단 검사.
- `scripts/Identity-Tester-README_KO.txt`: Windows 사용자 설명서.
- `.github/workflows/identity-tester-windows.yml`: v0.10 신 GUI PyInstaller EXE 빌드. 기존 v0.9 GUI는 회귀 보존.

## 판독 분류와 엄격한 경계
- `identified`: 공식 등록 작품의 이름과 압축 이름, 그리고 공식 상품번호 또는 **별도 로컬 이름 단서**의 일치. 이는 공식 *작품 식별*이며 게임 바이너리의 실제 진위 인증이 아니다.
- `likely`: 공식 검색 근거는 있으나 로컬 이름·품번 대조가 모자라거나 복수 EXE/읽기 제한이 있음.
- `multiple`: 여러 공식 제품 ID 또는 별개 제품 후보. 원작·패치 등을 자동 동일 제품으로 병합하지 않음.
- `unidentified`: 작품 미발견/검사 불가.
- `search_error`: 외부 검색 장애, 작품 부재와 별개.
- `identified` 외 모든 항목을 JSON의 `unresolved`와 '보류·미확인만' 탭으로 분리.
- 버전/한글판/번역 패치의 정체 적합성은 아직 검증하지 않음.
- 사용자 개인 파일은 실제 재검사하지 않았으므로 **v0.10 실측 정확도는 미측정**.

## 보존 및 빌드
- 브랜치: `experiment-dlsite-game-detector-20261117`, Draft PR #2, `main` 미병합.
- GitHub Actions EXE 빌드는 명시적 사용자 요청에 따라 1회 실행 후 `workflow_dispatch` 전용으로 복원.
- 배포 ZIP에 EXE 1개와 한국어 사용법 1개만 포함. 게임 목록·API 키 없음.

## 다음 개발
- 새 EXE로 이전과 동일한 129개 사용자 파일을 검사해 JSON 확보.
- v0.9의 원래 6단계 결과와 단순화된 v0.10을 *같은 정답표*로 비교.
- 누락·오탐·보류 판정을 수동 검수하며 실패 사례를 개인 자료 노출 없이 합성 테스트로 재현.
