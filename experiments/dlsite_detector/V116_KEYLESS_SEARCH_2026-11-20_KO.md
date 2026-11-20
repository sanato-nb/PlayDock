# PlayDock 파일명 전용 판독기 v0.11.6 — API 키 없는 검색 개선 (2026-11-20)

## 범위
- 실험 브랜치 `experiment-dlsite-game-detector-20261117` / Draft PR #2 전용. `main`과 PlayDock 정식 UI 및 DB 변경 없음.
- 원본 ZIP/7z/RAR 미개봉. 파일명의 게임명·품번·챕터·별도 콘텐츠 유형 표시만 처리.
- 사용자 고유 129개 파일 목록·검색 JSON·API 키는 커밋하지 않음.

## 키 없는 검색 경로
1. 파일명에 DLsite 품번 또는 Steam ID가 있으면 해당 공식 조회만 실행.
2. 품번이 없으면 독립 워커에서 DDGS `duckduckgo` 백엔드 1회.
3. 품질이 낮은 게임 기사/오류/0건만 있을 때 Bing RSS 1회 보조. 정확한 스토어 게임 페이지가 있으면 검색 종료.
4. 모은 제목/URL의 작품명·페이지 slug·챕터를 검증하며 URL 추적 파라미터만 무시하되 제품 식별 쿼리는 유지해 중복 제거. Steam URL에 제목 slug가 없어도 검색 제목이 완전히 같으면 공식 Steam API 재검증 단계로 전달. DLsite 공식 작품 URL은 관련 기사를 대신해 조기 종료 가능.
5. 검색에서 발견한 공식 DLsite URL 품번 및 제3자 검색 제목/URL에 나온 품번을 제한적으로 공식 카탈로그와 재대조. 제3자 품번은 `search_official_recheck`로 보존하며 **공식 파일명 일치로 자동 확정하지 않음**.
6. Steam 후보는 기존과 같이 Steam 공식 상품명·유형 검증. DLC/모드/패치/서버팩/합본 등 파일명 힌트가 있으면 본편으로 확정하지 않음.

## 기술 및 운영 한계
- DDGS는 무료 오픈소스 라이브러리이며 공식 무제한 API가 아니다. 서비스별 이용 조건, 차단, 비정상 응답, 버전별 지원 백엔드 변경 가능. Google 웹페이지 직접 스크래핑을 별도로 구현하지 않는다.
- Bing RSS 공개 엔드포인트는 검색 결과 API 계약·호출 보장이 없다. HTML 차단 응답은 정상적인 '0건'으로 처리하지 않는다.
- 공개 SearXNG 인스턴스는 JSON/RSS 응답이 막힌 곳이 많고 제3자 가용성·개인정보 통제도 불확실하므로 기본 제공자에 넣지 않는다. 개인 관리 인스턴스라면 향후 선택형 설정이 가능하다.
- 키가 필요한 Serper 선택형 경로는 이전 기능을 보존하지만 기본 경로가 아니며, 키는 JSON/커밋에 포함되지 않는다.
- 한 워커의 제한시간은 13초이며 검색 실패와 '확인 가능한 후보 없음'은 별도 기록한다.
- 공식 작품 카탈로그에 이름이 있다는 것과 파일 내용의 실제 정체는 구분한다.
- 129개 사용자 데이터에 대한 v0.11.6 온라인 정확도/속도는 실제 재검사 전까지 미측정.

## 변경 경로
- `experiments/dlsite_detector/pipeline.py` — DDGS 기본 게임명 조회의 DuckDuckGo 한정
- `experiments/dlsite_detector/filename_web_search.py` — 보조 검색 시점, 챕터 단서, URL 중복·JSON 공급자 로그
- `experiments/dlsite_detector/filename_only.py` — 후보 품번 공식 재조회, 배포 형태 구분, 기록 구조
- `scripts/filename_identity_tester.py` — 독립 UI의 버전·진단·JSON 표시
- `scripts/Filename-Tester-README_KO.txt` — 독립 실행파일 사용법 및 제한 설명
- `tests/test_v11_filename_only_experiment.py` — 합성 제목과 모의 웹 응답 회귀
- `experiments/dlsite_detector/FILE_MAP_KO.md` — 파일 역할 최신화
- `experiments/dlsite_detector/HANDOFF_2026-11-19_KO.md` — 최신 버전 명시

## 테스트 및 빌드 확인
- 전체 Python 회귀 최종: **727 passed**, 2026-11-20 GitHub Actions [성공 #44677221287](https://github.com/sanato-nb/PlayDock/actions/runs/44677221287). Python 3.12, Ubuntu 러너 기준.
- 첫 CI(#44676673765)는 챕터별 itch.io URL 일치 테스트 1건 실패(1 failed/722 passed). `filename_page_rank.py`의 정확한 챕터 슬러그 허용 로직 수정 후 최종 CI 모두 성공.
- Windows 독립 EXE v0.11.6: **미생성/미검증**. 이전 v0.11.5 빌드 결과를 새 버전의 성공으로 표기하지 않음.
- EXE Actions는 `workflow_dispatch` 수동 전용을 유지함.
- **수동 EXE 실행 제약:** `.github/workflows/identity-tester-windows.yml`은 현재 실험 브랜치에만 있고 `main`에는 존재하지 않는다. GitHub `workflow_dispatch`는 워크플로 정의가 기본 브랜치에 있어야 수동 실행할 수 있다. 사용자 지시대로 `main`에는 파일을 추가하지 않고, 일회성 push 트리거로 자동 빌드하지 않았다. 따라서 이번 v0.11.6 Windows EXE는 아직 생성되지 않았다. Windows 빌드 성공 보고 금지.
