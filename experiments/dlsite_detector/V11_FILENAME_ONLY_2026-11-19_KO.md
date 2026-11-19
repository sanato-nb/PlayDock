# PlayDock v0.11.3 파일명 전용 최소 정체 판독기 — 인수인계

## v0.11.3 — 무관한 Bing RSS 결과로 검색 종료하던 문제 개선
- v0.11.2 129개 실사용 JSON에서 품번 없는 39개는 모두 Bing RSS 검색만 실행. 6월의 너와 나 → 숫자 6, BunnyHero → 중국 블랙박스, BUZAMA 2 → 오사카성, SummertimeSaga → 유튜브 고객센터 등 명백히 무관한 검색 결과가 있으면 `search_one_title`에서 즉시 `return`해 DDGS는 0회 호출됨.
- `filename_web_search.py`: 전체 게임 이름 비교(띄어쓰기·구분자 표준화), GAME 문맥 및 실제 배포 페이지 경로 검사. Bing 결과가 무관하면 원문 건수와 제외 예시를 기록하고 DDGS를 한 번 더 요청. 공식 게임 배포 페이지인 경우에는 즉시 종료, 일반 기사만 있을 때는 공식 출처를 더 검색. 결과는 품질순 합치고 URL 중복 제거.
- `filename_only.py`: 6글자 미만 제목을 무조건 버리던 웹 단서 필터를 3글자부터 경계 기반 비교로 개선. REC·PASEC 같은 짧고 겹치기 쉬운 이름은 공식 판매 페이지나 게임 문맥을 추가로 요구하고 작품 정체로 자동 확정하지 않음.
- `scripts/filename_identity_tester.py`: JSON 파일 기본명 v0.11.3, 상세 창에 총/관련/제외 검색 결과 수 및 거부 예시 표출.
- 기본 웹 검색 프로세스 종료 시간은 8.5초에서 13초로 변경. 신뢰도 확인용 추가 DDGS 조회로 실제 전체 시간은 증가 가능. 품번 있는 파일은 이전 직접 조회 경로 유지.
- 이번 v0.11.3은 게임 파일 내용은 읽지 않으며, 129개 실제 재검사 결과 전까지 성공률 향상 수치를 주장하지 않는다. Python 회귀 690개 통과.



## v0.11.2: 129개 실제 사용자 결과에서 '검색했는데 미발견' 진단
- v0.11.1 검사 129건 중 `official_match` 9건, `catalog_found` 72건, `likely` 6건, `multiple` 1건, `unidentified` 41건. 90개 파일명에 DLsite/Steam ID가 있으며 39개는 ID 없음.
- 무품번 39개가 모두 `unidentified`였으나 통신 오류는 없고 파일당 0.25~0.36초만 소요. JSON이 원본 검색 목록을 저장하지 않으므로 원인은 **검색 공급자 0건 반환 또는 후보 판단에서 전부 제외** 중 하나로 구분되지 않았음.
- 직접 수동 웹 검색에서는 `6월의 너와 나`, `BunnyHero`, `BUZAMA 2`의 관련 자료가 확인됨. 다만 이 결과는 웹 검색 일반 서비스의 것이며 Windows 프로그램의 Bing RSS/DDGS 결과를 직접 증명하지 않음.
- `filename_web_search.py`에서 Bing RSS·DDGS 검색별 `state`, `result_count`, `seconds` 추적(동일 기존 조회에 추가 통신 불필요).
- `filename_only.py`에서 `web_raw_results`, `web_evidence`, `search_providers` 기록. 공식 페이지뿐 아니라 제목·게임 문맥이 관련된 웹 검색 페이지를 `web_candidate`로 보관, 게임 콘텐츠 자동 확정하지 않음.
- `scripts/filename_identity_tester.py` 상세 화면에 결과 제목/URL 및 검색 공급자 시간/건수 노출, JSON 집계 추가. 파일명 이외의 아카이브 내부는 열지 않음.
- `tests/test_v11_filename_only_experiment.py` 검색 웹 단서/무관 페이지/0건 응답/공급자 통계를 확인하는 합성 회귀 추가.
- 사용자의 개인 JSON과 압축파일은 공개 저장소에 넣지 않음. v0.11.2 실제 129개 파일의 재측정 이전에는 실사용 정확도 향상을 주장하지 않음.



## 2026-11-19 v0.11.1: 129개 실측 JSON을 근거로 수정
- 업로드 `PlayDock_Filename_Identity_v0.11.json`: 129개 중 `official_match` 9, `likely` 78, `search_error` 38, `multiple` 1, `unidentified` 3.
- 품번 없는 파일 39개 중 `LookupBusy` 32, `LookupTimedOut` 5, `RuntimeError` 1, 조회 후 후보 미발견 1. 8초 제한을 넘긴 DDGS 백엔드가 실행 중인 상태로 전역 잠금을 계속 보유해 나머지 검색을 막았다.
- `filename_web_search.py`: Bing RSS 형식 검증 → DDGS 대체 시도. 기본 게임명 검색을 **자식 프로세스**로 분리, 약 8.5초 강제 종료하여 다음 조회를 오염시키지 않음. 부정확한 RSS/차단 HTML은 검색 결과 없음으로 처리하지 않음.
- `filename_only.py`: 기존 `_TITLE_GATE` 대신 격리 워커를 사용. 제품 ID가 공식 조회되었으나 파일명에 게임 이름이 없거나 다국어 제목 차이로 비교가 불가하면 `catalog_found` (품번 공식 상품 발견·이름 미검증)으로 따로 보고. **실제 게임 콘텐츠 식별 완료로 표시하지 않음.**
- `filename_identity_tester.py`: PyInstaller EXE에서 별도 프로세스가 실행 가능하도록 워커/자가 진단 옵션 추가. GUI/JSON에서 `catalog_found` 집계.
- 파일명 외의 압축 내부는 열지 않음. 이전 사용자 개인 검사 JSON, 사용자 고유 게임 목록, API 키는 공개 저장소에 포함하지 않음.
- Python 합성 회귀 679개 통과 (새 빌드 완료 이후 최종 검증 상태 별도 기록).
- 실사용 네트워크 검색 성공률·전체 소요시간의 개선 여부는 사용자가 새 검사 JSON을 업로드해야 비교할 수 있음.



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
