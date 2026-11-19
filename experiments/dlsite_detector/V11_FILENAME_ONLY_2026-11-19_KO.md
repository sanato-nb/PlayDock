# PlayDock v0.11 파일명 전용 최소 정체 판독기 — 인수인계

## 사용자 의도
사용자가 반복 지적한 검색 타임아웃·정확도 저하를 분리 진단하기 위해
이전 v0.10.2의 폴더/EXE/README 검사, 다단계 검색 체인을 *완전히 제외*한 별도 프로그램.

## 실제 구현
- `experiments/dlsite_detector/filename_only.py`: 파일명 문자열만 받음. `extract_filename_clues`는 이름·RJ/BJ/VJ/EJ/Steam ID 추출; `identify_filename`는 공식 코드 직접 조회 또는 웹 제목 검색 한 번.
- `scripts/filename_identity_tester.py`: 새 Tkinter GUI. 파일명 직접 붙여넣기, 실제 파일 선택, 전체/보류 결과, JSON 저장, 오류·시간 기록, 무인터넷 EXE 자체 테스트.
- `tests/test_v11_filename_only_experiment.py`: 합성 이름만 사용하는 회귀 검사. 내부 ZIP/7z/RAR 열기 없음.
- `scripts/Filename-Tester-README_KO.txt`: 새로운 EXE 설명서.
- `.github/workflows/identity-tester-windows.yml`: 독립 Windows 검증판 EXE 빌드 대상으로 `filename_identity_tester.py` 지정.
- 이전 `simple_identity.py`, `simple_identity_tester.py`, v0.10 사용자 설명서는 과거 회귀 검증용으로만 보존. 기존 게임 데이터/사용자 계정/PlayDock DB에는 손대지 않음.

## 판정과 한계
- 외부 상품 ID가 파일명 속 ID와 동일한지 비교. 이름·게임 유형도 일치하면 `official_match`로 출력.
- 품번 없는 파일은 일반 웹 검색이 필요하며 외부 검색 장애에 따라 미확인일 수 있음.
- `official_match`는 카탈로그 상품명과 *파일명*의 일치일 뿐 **압축파일의 실제 콘텐츠가 게임이라는 검증은 아니다**.
- 외부 DDGS, DLsite 공개 JSON, Steam API는 네트워크 사정으로 실패할 수 있음. 백엔드 멈춤 시 별도 스레드가 일시 남을 수 있어 동일 서비스 중복 호출 차단.
- JSON에는 `scope: archive_filename_only` 또는 각 파일의 `archive_contents_inspected: false` 기록.
- 게임 버전·한국어 지원·번역 패치·엔진 분석은 후속 단계로 보류. 번역 패치 *공식 상품*만 파일명 게임 본편과 동일한 것으로 확정하지 않음.
- 사용자 실파일 대규모 재검증 없이 정확도 상승률을 주장하지 않음.

## 빌드 정책
- 실험 브랜치 `experiment-dlsite-game-detector-20261117`, Draft PR #2, main 병합 금지.
- Windows 빌드는 사용자의 요청에 따른 1회 실행 후 수동 전용으로 복원.
- 사용자 검사 JSON은 비공개 로컬 파일로 유지, GitHub 커밋 금지.

## 다음 검증 제안
- 실제 게임 ZIP을 전송할 필요 없이 기존 11개 파일의 **파일명 문자열**을 새 GUI에 붙여넣어 검색.
- JSON에서 정확히 어떤 이름/번호로 검색했는지, 공식 응답·오류·시간을 살펴본다.
- 무품번 게임은 웹 출처가 검색되지 않았는지/네트워크 타임아웃인지 별도 계측한다.
