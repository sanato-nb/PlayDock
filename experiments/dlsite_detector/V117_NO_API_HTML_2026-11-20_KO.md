# PlayDock 단독 판독기 v0.11.7 — API 호출 없는 공개 HTML 검색 실험 (2026-11-20)

## 목적
사용자가 외부 API 및 API 키 없이 게임 파일명만으로 게임 정체를 검색하기를 원함. 기존 v0.11.6 무료 검색의 실측 실패를 확인하여 검색·공식 상품 대조 경로를 분리했다.

## 두 개의 실제 검사 결과 (사용자가 제공한 사적 JSON, 원본은 커밋하지 않음)
| 지표 | v0.11.6 Serper 사용 | 동일 코드/키 없는 v0.11.61 |
|---|---:|---:|
| 파일명 총수 | 129 | 129 |
| 검색 장애 | 8 | 38 |
| 웹 이름 후보 | 26 | 1 |
| 공식 이름 일치 | 12 | 9 |
| 코드로 공식 상품 등록 확인 | 68 | 68 |
| 유력 후보 | 12 | 10 |
| 복수 후보 | 1 | 1 |
| 미확인 | 2 | 2 |

두 결과에서 작품번호·Steam ID 없이 제목 웹 검색이 필요한 파일은 39개였다. API 키 없이 진행한 기록의 DDGS 공급자 호출 39건 모두 오류, Bing RSS 38건 무관 결과, 1건 관련 결과였다. **이 통계는 v0.11.6 기존 방식에 대한 진단이지 v0.11.7 정확도 향상 증거가 아니다.**

## v0.11.7 독립 GUI의 실행 방식
- `scripts/filename_identity_tester.py`에서 API 키/Serper 입력란을 제거하고 `identify_filename(..., no_api=True)`로 실행.
- 신규 `experiments/dlsite_detector/no_api_html.py`: DuckDuckGo 비-JS 검색 HTML, itch.io 검색 HTML, Mojeek 일반 검색 HTML, Steam 검색 HTML의 결과 앵커를 제한적으로 수집. DLsite 상품 HTML 및 Steam `/app/ID/` HTML에서 직접 제품명 추출.
- `experiments/dlsite_detector/filename_web_search.py`: 격리된 프로세스에서 `no_api` 플래그에 따라 HTML 공급자만 선택. 이전 Serper 환경변수는 검색 자식 프로세스에서 삭제. 기존 워커 제한시간, 공급자 오류·시간 로그 유지.
- `experiments/dlsite_detector/filename_only.py`: 직접 품번, 검색에서 발견한 품번, Steam ID 모두 `no_api` 모드에서는 일반 상품 HTML을 사용. 기존 API 기반 분류는 레거시 개발·테스트에 남지만 이번 GUI 경로에서는 호출하지 않는다.
- **기본 결과는 보수적**: 공개 HTML로 번호·작품명은 확인 가능하나 게임 유형을 검증 못 하면 `catalog_found`로 남기며 `official_match`를 자동 부여하지 않는다.
- JSON 저장 이름은 `PlayDock_Filename_Identity_v0.11.7_no_api.json`. 압축파일 자체/개인 자료 미검사.

## 안전 및 기술상 한계
- 계정/토큰/유료 API 없음. 브라우저 HTML 조회는 사이트 정책·차단·캡차·연령 게이트·언어 설정에 영향을 받음. 무단 차단 우회/캡차 회피는 구현하지 않음.
- HTML 파서는 검색 결과와 URL을 보수적으로 검증하나, 공개 검색 사이트가 자동화 요청에 정상 응답한다고 보장할 수 없음. 실제 Windows 검색 성공률·정답률은 아직 사용자 실측 전에는 **미측정**.
- PDF/아카이브/게임 EXE 내부 데이터는 미분석. 실제 게임 버전·배포 정체를 확인하지 않음.
- 공개 GitHub에는 개인 129개 전체 파일명, 개인 JSON, API 키를 업로드하지 않음.
- 연구는 `experiment-dlsite-game-detector-20261117` 실험 브랜치 / Draft PR #2 한정. `main` 병합 금지.

## 회귀 검사
- 전체 Ubuntu Python 3.12: **739 passed**, [CI #44739859816](https://github.com/sanato-nb/PlayDock/actions/runs/44739859816). 과거 727건 + HTML 모의 응답 12건.
- Windows EXE 실행 결과·다운로드 아티팩트는 별도 빌드 완료 후 기록.
