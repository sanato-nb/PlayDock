# PlayDock 게임 정체 판독기 — 새 채팅 인수인계 (2026-11-20)

> **v0.11.6 추가(2026-11-20):** 전체 Python 회귀 **723개 통과** ([Actions #44676783968](https://github.com/sanato-nb/PlayDock/actions/runs/44676783968)); v0.11.6 Windows EXE는 수동 빌드 전까지 미검증. 기준 HEAD와 테스트 결과는 [v0.11.6 개발 기록](V116_KEYLESS_SEARCH_2026-11-20_KO.md) 참조. 기본 DDGS의 DuckDuckGo 한정, 약한 기사 결과에서 Bing RSS 추가 확인, 챕터 비교와 URL 중복 제거, 웹 품번 공식 재조회, 별도 DLC/패치/모드팩 본편 오인 방지를 추가. 129개 실사용 재검사와 Windows 새 EXE 검증은 별개로 확인해야 한다. 아래 v0.5 내용은 역사 기록이며 최신 설계 기준이 아니다.

> **v0.11.5 최신:** v0.11.4 실사용 129개 검사에서 무품번 39개 중 DDGS 실패 16개 확인. Google 검색 결과 제공 서비스 Serper.dev를 사용자 API 키 선택 입력형으로 연결. 키 입력 시 Serper → DDGS → Bing RSS, 키 미입력 시 기존 검색. 키는 실행 중 자식 환경변수로만 전달하고 EXE/임시 JSON/명령행/결과/공개 코드에 넣지 않음. `serper_client.py`, `filename_web_search.py`, `filename_only.py`, `filename_identity_tester.py`, tests 및 `V11_FILENAME_ONLY_2026-11-19_KO.md` 참조. 실제 검색 품질은 새 Windows EXE 사용자 재검사 전까지 미측정.

> **v0.11.4 최신:** 사용자 129개 v0.11.3 JSON에서 웹 후보 17개 중 개발자 홈·다른 챕터·다른 작품명 일부 일치 오탐과 검색 장애 18건을 확인. `filename_page_rank.py` 신규 구현으로 게임 작품 URL slug·챕터·제목 전체 대조, `filename_web_search.py` DDGS 우선 + Bing RSS 보조, `filename_only.py` 공식 Steam ID/제목 재검증 및 불일치 결과 제외, `filename_identity_tester.py` 공급자 오류·제외 근거 상세/JSON 기록. 파일명 이외의 압축 내용은 여전히 읽지 않음. 상세 `V11_FILENAME_ONLY_2026-11-19_KO.md` 및 tests 참조. 실사용 정확도는 재검사 전 미측정.


> **v0.11.3:** 129개 사용자의 v0.11.2 결과에서 품번 없는 39개의 Bing RSS 결과가 전부 무관함에도 RSS 결과 '6건 존재'만으로 DDGS 검색이 0회라는 원인 확인. `filename_web_search.py`에서 이름 전체+게임 문맥+판매 페이지 품질 확인 후 관련 없으면 DDGS 재검색, 제공자별 유효/제외 건수 기록. `filename_only.py`의 REC/PASEC 6글자 제한을 완화하되 미검증 후보로만 둠. 신규 테스트 6개, 총 690개 통과. 새 파일명 판독기는 압축파일 내부를 절대 열지 않음.


> **v0.11.2:** 이전 v0.11.1 129개 사용자 검사에서 품번 없는 39개가 모두 미확인인 문제를 분석. 이 파일명 전용 새 버전은 검색 원본 URL/제목과 Bing RSS/DDGS별 응답 건수·시간을 JSON에 포함하고, 게임명 관련 웹 문서도 확정 아닌 `web_candidate`로 분류함. 정확도 개선 수치는 재검사 필요. 세부 `V11_FILENAME_ONLY_2026-11-19_KO.md` 참조.


> **v0.11.1:** 사용자의 129개 파일명 검사에서 품번 없는 39개 중 32개가 `LookupBusy`로 실검색도 못한 원인 규명. `filename_web_search.py`에서 제한시간 이후 **검색 자식 프로세스를 종료**해 연쇄 실패 차단, RSS→DDGS 대체 지원. 품번만 등록된 파일은 `catalog_found` 분류 추가. 새 EXE 진입점 여전히 `scripts/filename_identity_tester.py`, 저장소 실험 브랜치 Draft PR #2 유지. 사용자 파일명 JSON은 공개 저장소 업로드 금지.


> **v0.11 파일명 전용 독립 검증판:** 이번에는 실제 압축파일 내부를 열지 않으며 EXE·README·폴더를 검사하지 않습니다. `experiments/dlsite_detector/filename_only.py`와 `scripts/filename_identity_tester.py` 신규 작성. 파일명에서 게임명과 공식 번호만 뽑아 직접 조회하거나 단일 웹 제목 검색합니다. 파일명을 붙여넣기만 해도 판독 가능합니다. 상세 `V11_FILENAME_ONLY_2026-11-19_KO.md` 읽기. 이전 0.10.2 GUI는 회귀 보존합니다. 원본 게임 파일/개인 JSON 공개 금지.


> **v0.10.2 정확도/시간 수정:** 사용자 개인 v0.10.1 JSON 11개 분석에서 총 340.75초, 코드 5회 공식 조회 성공·8회 웹 검색 네트워크 오류·8회 쿨다운 생략을 확인. `simple_identity.py`가 공식 상품번호 먼저 조회 후 공식 제목을 로컬 이름과 대조해 쓸모없는 제목 웹 검색을 생략하며, 품번 없는 경우에만 짧은 웹 조회를 사용하도록 변경. `scripts/simple_identity_tester.py`의 분류기는 공식 ID와 일반 제목에서 서로 다른 경로를 사용. 이름·품번 외 입력은 사용하지 않으며 별도 미확인 탭/JSON 보존. `V10_SIMPLIFIED_IDENTITY_2026-11-19_KO.md`에 기록. v0.10.2 사용자의 실제 정확도는 미측정.


> **v0.10.1 첫 화면 규칙:** v0.10 검사 JSON에서 공통 하위 폴더명이 너무 많이 검색되는 오염을 확인하고 `simple_identity.py`의 폴더 후보를 **압축파일 최상위 1단계(`parts[0]`)만** 사용하도록 제한했다. `audio`/`css`/`data`/`img`/`js` 등 루트 공통 리소스 폴더도 검색에서 제외한다. EXE·README는 별도 기존 안전 규칙을 유지. 테스트 645개 통과. 새 Windows EXE의 버전 표시는 `0.10.1-test`. 자세한 기록은 `V10_SIMPLIFIED_IDENTITY_2026-11-19_KO.md` 참조.


> **v0.10 간소화 독립 판독기 (2026-11-19):** 이번 실험의 **실행 EXE 진입점은 `scripts/simple_identity_tester.py`**이며, 엔진은 `experiments/dlsite_detector/simple_identity.py`입니다. 기존 v0.9 `scripts/game_identity_tester.py`와 복잡한 6단계 엔진은 회귀 호환용으로만 남겼습니다. 새 실행판은 압축파일명·최상위 폴더·복수 EXE 역할 확인·README의 명시적인 **게임 이름/작품번호만** 수집하고, 검색 실패/복수 후보/유력 후보는 별도 미확인 탭 및 JSON `unresolved`에 보관합니다. 버전/한국어/엔진/DLC 검사는 후속 단계로 제외했습니다. [v0.10 상세](V10_SIMPLIFIED_IDENTITY_2026-11-19_KO.md).


> **현재 소스 v0.9-test — 정확도 중심 재감사 (2026-11-19):** v0.8의 129개 실제 검사 JSON에서 찾은 후보 오염을 중심으로 다중 EXE 역할 필터(보조 도구/엔진 런타임 제거, Unreal Shipping 구분), 공통·보너스 폴더 검색 억제, 이어 붙은 웹 결과 제목의 오인 방지, 후보별 공식 ID 정확한 분리, **별도 등록된 본편과 번역 패치의 '연관 가능성' 표시**를 추가했습니다. 본편·번역 패치 상품은 절대 자동 병합하지 않으며 내부 본문 읽기 정책도 유지합니다. README 일본어 '品番'을 지원합니다. [v0.9 개발 기록](V09_ACCURACY_2026-11-19_KO.md)을 우선 읽으세요. CI 전체 테스트 **621개 통과**: https://github.com/sanato-nb/PlayDock/actions/runs/44453760922. v0.9의 실제 129개 정확도는 아직 측정하지 않았습니다.


> **현재 소스 v0.8-test — 정확도 우선 개정 (2026-11-19):** 기존 v0.7 파일·폴더 목록 중심 + README 제한 읽기를 유지합니다. 인터넷 검색에서 댓글·개발일지를 단독 작품 페이지로 승격하지 않으며, 제3자 웹 품번은 **검색 제목과 공식 작품명 사이의 연결 근거**가 없으면 공식 후보로 승격하지 않습니다. 서로 다른 DLsite/Steam 후보의 공식 ID는 개별 후보에만 표시합니다. 압축파일명/내부 EXE·폴더와 외부 제목 사이의 정확한 일치 여부는 별도 참고 근거로만 표시하며 **최종 일치 확정이나 자동 연결에는 사용하지 않습니다.** [v0.8 구현 기록](V08_ACCURACY_2026-11-19_KO.md)을 먼저 확인하세요. 실제 129개 개인 게임에 대한 v0.8 재측정은 아직 수행되지 않았습니다.


> **현재 소스 v0.7-test (2026-11-19):** 기본 분석은 압축파일명 + 내부 파일·폴더 목록/구조를 수집하고 **README의 제한된 식별 필드(최대 2개 파일)만 내용 읽기**합니다. INI·JSON·app.info·Steam ID 설정파일 등은 파일명/경로만 확인합니다. 검색 계획은 압축파일명 제목을 반드시 포함하며, 목록/README 수집 이후 인터넷 조회하고 공식 후보와 교차검증합니다. [v0.7 실제 구현 문서](V07_IMPLEMENTATION_2026-11-19_KO.md)를 먼저 확인하세요. v0.5 실측 129개 데이터는 이전 기록이고 **v0.7 실측 결과가 아닙니다.**

> **v0.6 개발 기록 (2026-11-19):** 이 문서의 0.5 수치와 미해결 목록은 **개발 이전 기준 기록**입니다. 신규 개발 커밋 및 최신 현재 구현은 [v0.6 실제 구현 기록](V06_IMPLEMENTATION_2026-11-19_KO.md)과 [파일별 역할](FILE_MAP_KO.md)을 먼저 확인하세요. P0 웹 품번 복구·오류 분리·재검사·단계별 시간 측정 및 검증된 DLsite↔Steam 병합을 실험 브랜치에 반영했습니다. 사용자 개인 129개 파일에 대한 v0.6 재측정은 수행하지 않았습니다. Draft PR #2 유지, main 미병합.

> **현재 기준 문서 / 단일 진입점.** 작업 연속성은 이 문서를 우선하며, 이전 `README_KO.md`의 1~17절은 역사적 기록이다. 이 문서는 새 채팅이 프로젝트 상황을 먼저 검증한 뒤 *실제 개발*에 착수하도록 작성했다.
>
> **개인정보:** 실제 129개 압축파일의 이름·압축 내부 경로·웹 결과를 담은 원본 JSON/CSV와 상세 감사 보고서는 **공개 GitHub에 올리지 않는다**. 다음 채팅에는 사용자가 필요한 JSON을 다시 첨부해야 한다. 이 문서에 개인 게임 목록/파일명을 나열하지 않는다.

## 1. 프로젝트와 현재 상태

- 저장소: https://github.com/sanato-nb/PlayDock
- 작업 브랜치: `experiment-dlsite-game-detector-20261117`
- Draft PR: https://github.com/sanato-nb/PlayDock/pull/2 — 아직 `main`에 병합하지 않음.
- 현재 검증판: **0.5-test**, 독립 Windows GUI (`scripts/game_identity_tester.py`).
- PlayDock 본체 `src/playdock/`에 실험 판독기를 연결하지 않았음.
- 마지막 기능 기준 커밋(문서 인수인계 전): `42617f69e22036901ada7ca03513a2f35affcbac`.
- 마지막 기능 기준 CI: Python 전체 회귀 테스트 **592개 통과** https://github.com/sanato-nb/PlayDock/actions/runs/44327029338 ; Windows 빌드/EXE `--self-test` 성공 https://github.com/sanato-nb/PlayDock/actions/runs/44327012216 .
- README·문서·워크플로를 이 인수인계에서 정리하더라도, `main` 병합·사용자 DB 변경은 금지.

## 2. 사용자 요구 및 불변 규칙

1. **핵심 순서:** `압축파일 이름 + 압축파일 내부 근거를 둘 다 수집 → 후보 정규화·우선순위·중복 제거 → 함께 인터넷 검색 → 6단계 교차검증`. **파일명만 먼저 검색하거나 내부만 우선하는 식으로 왜곡 금지.**
2. ZIP/7z/RAR 원본 **읽기 전용**. 게임 EXE/패치/스크립트 실행 금지, 원본 이름·내용 변경/일괄 해제 금지.
3. 암호화 또는 암호 상태 불명 파일은 내부를 읽지 않고 파일명만 검색. 암호 없는 파일만 내부 목록·크기가 제한된 메타데이터를 읽음.
4. 검색에 파일 전체 경로·내부 파일 전체 목록·설정 원문을 전송하지 않음; 후보 제목/작품 ID만 전송. 게임 바이너리 및 개인 API 키/캐시를 GitHub에 업로드하지 않음.
5. '공식 게임 카탈로그에 존재'와 '내 압축파일이 해당 게임'은 다른 질문. 근거 부족 시 미확인 처리. 특히 DLC·패치·번역판·합본 및 상이한 공식 ID를 함부로 통합/자동 등록 금지.
6. 사용자 데이터/설정/기존 게임 라이브러리·모음집·이미지 캐시 보존. `src/playdock/`의 UI와 Controller/Service 기능 분리는 유지. 현재는 독립 실험 유지.
7. 커밋 제목/설명은 **한국어**. 변경 파일·폴더 트리를 보여줄 때 경로마다 **역할을 한글로 설명**. 중복 문서는 인덱스/표시로 정리하되 과거 기록을 무단 삭제하지 않음.
8. 자동 Windows EXE 빌드는 원치 않음: 필요할 때 수동 `workflow_dispatch`로 생성. **테스트 CI와 EXE 빌드는 구별**.

## 3. 구현 파이프라인 v0.5

**비암호화:** 이름 파싱(1) → 암호 판독(3) → ZIP/7z/RAR 목록(4) → 작은 엔진 설정/README 메타데이터(5) → 이름·내부 근거 통합 검색(2) → 별도 6단계 검증.

**암호화/불명:** 이름(1) → 암호 판독(3) → 파일명만 인터넷 검색(2); 내부 미조회.

- `archive_encryption.py`: 암호 상태 확인.
- `archive_inspector.py`: 목록, 파일 수·크기, EXE, Unity/Godot/Ren'Py/RPG Maker/Unreal 등 단서, 작품 코드, 번역 경로.
- `internal_metadata.py` + `metadata_fields.py`: 안전한 제한 안에서 Unity `app.info`, RPG Maker `System.json`, NW.js `package.json` 등 명시적 필드 수집. 솔리드 7z는 `index_only`가 될 수 있음.
- `search_plan.py`: 파일명·내부 목록·설정 단서를 **함께** 모아 점수 순 정렬. 빠른 모드 파일당 최대 3개, 정밀 모드 6개 후보 검색어.
- `pipeline.py`, `enhanced_search.py`, `steam_client.py`, `detector.py`: 외부 작품 조회 및 후보 보존.
- `search_session.py`: GUI 배치 실행 동안만 캐시. 연속 검색 오류 2회 시 제목 검색을 20초간 생략, **공식 작품 ID 조회는 계속**. 이 정책은 속도를 개선하지만 탐지 누락을 낳을 수 있음.
- `catalog_aliases.py`/`identity_matcher.py`: 명시적 공식 ID/확인된 별칭을 기반으로 통합; 서로 다른 플랫폼의 같은 작품을 아직 완벽히 연결하지 못함.
- `identity_verifier.py`/`verification_report.py`: `catalog_status`와 `local_identity_status` 분리, `verdict`는 별도 보수 판정. 모든 자동 연결 `false`.
- `scripts/game_identity_tester.py`: Tkinter GUI만 담당하고 독립 분석 함수 호출, 상단 전체/단계 진행바, JSON/CSV 출력, 파일별 `analysis_seconds`; **암호·목록·메타·네트워크 각각의 시간은 아직 별도 계측하지 않음**.

## 4. 실사용 검증 수치 (원본 JSON을 다시 대조한 값)

| 항목 | v0.4 | v0.5 |
|---|---:|---:|
| 검사 항목 | 128개 | 129개 (v0.4와 일치 128개) |
| 파일별 처리시간 합 | 1068.725초 | 전체 318.092초 / 동일 128개 314.084초 |
| 동일 128개 처리시간 감소 | — | **70.61%** |
| 외부 후보 제목이 존재하는 파일 | 82개(원본 재집계) | 83개(전체·동일 128개 모두) |
| 최종 `likely_candidate` | 2개 | 전체 4개 / 동일 128개 4개 |
| 최종 `matched` | 0개 | 0개 |
| 최종 `needs_review` | 115개 | 전체 110개 |
| 최종 `unclassifiable` | 11개 | 전체 15개 |

v0.5 마지막 배치 검색 세션: `requests=162`, `cache_hits=5`, `avoided_requests=20`, `network_errors=39`. 검색 생략이 한 번 이상 발생한 파일 **13개**, 오류 기록 파일 **36개**.

v0.5 카탈로그 상태(129개): `official_game_found=79`, `web_candidate=2`, `multiple_candidates=1`, `lookup_error=30`, `not_found=17`.

**엄격한 해석:** 70.61%는 원자료의 파일별 기록 시간 합계 비교이고 Windows 벽시계·단계별 실시간 재현 실험이 아님. 캐시·네트워크 상태·검색 생략도 달라짐. 외부 후보 83/129는 **후보 발견률(64.3%)이지 정확도/재현율 아님**. 사용자가 가진 압축파일 바이트/공식 진위의 독립 전수 검증은 수행되지 않음.

## 5. 반드시 수정할 미해결 결함

### P0 — *웹 응답에 작품 코드가 있는데 결과 후보는 비어 있음*
- 검색 결과 제목/URL의 RJ 등의 코드가 눈에 띄어도 2단계가 이를 검증 대기 후보로 보존하지 않고 `not_found`로 반환하는 경우가 반복됨.
- 안전한 해결: 제목·URL에서 식별자를 제한적으로 파싱 → 원본 카탈로그 공식 ID 조회 → 확인되면 카탈로그 후보, 원본 확인 실패 시 '제3자 카탈로그/웹 단서'로 보류. 제3자 글을 공식 확정으로 승격 금지.
- 회귀 실험: *가상* 한글 제목 + 제3자 작품번호 링크, *가상* 시리즈 2/3 등. 번호는 테스트 전용 가짜 값 사용.

### P0 — 검색 오류로 생략된 항목 관리
- `SearchSession` 쿨다운으로 제목 검색 20회 생략/13개 파일 영향. 지금도 게임 미존재와 검색 실패가 섞여 보일 수 있음.
- `lookup_error`/`skipped_due_to_cooldown`/`not_found` 구분, 재검색 대기열 또는 개별 수동 재검사. 오류 복구 후 남은 파일부터 재시도; 불필요한 조회 폭증 금지.

### P1 — 다국어/플랫폼 후보 병합
- DLsite 공식 ID와 Steam 작품 ID가 동일 게임의 서로 다른 상품명을 가리켜도 복수 후보가 남는 사례.
- **공식적으로 검증 가능한 교차 플랫폼 링크/원제/명시적 병기**가 있을 때만 병합. 단어 유사/기계 번역만으로 동일 게임 확정 금지.
- 내부 `elenastory`와 카탈로그 `Elena's Story` 같은 문장부호/공백 변형을 표시명 비교에서 고려하되, 근거 등급·출처를 보존.

### P1 — 내부 목록 근거의 신호/노이즈 구분
- `player`, `BepInEx` 등 일반 파일명, Unity 라이브러리 다수가 압축 근거 목록을 길게 함. 검색 후보 필터와 사용자 UI용 요약은 분리.
- `RJ` 코드/실행파일/명시적 엔진 제목과 장르 불명 DLL 경로를 혼동하지 않기. 원본 경로는 삭제하지 않고 제한된 요약만 보고서에 제공.

### P1 — 패치/DLC/번역판/합본 관계
- 번역 패치 등록 ID가 원작과 다름; DLC/합본에 본편 ID가 포함되기도 함. 카탈로그 `catalog_release_type`와 로컬 패키지 유형을 구분하여 자동 링크 방지.

### P1 — 단계별 성능 계측
- `archive_name_parse_ms`, `encryption_probe_ms`, `index_scan_ms`, `metadata_read_ms`, `search_ms`, `verification_ms`를 별도 JSON에 기록; 벽시계 포함.
- 이후 진짜 병목 확인 전에는 압축 내부 목록을 과도하게 생략하거나 게임 바이트를 무제한 읽지 않음.

## 6. v0.6 실제 작업·승인 기준

1. 시작 직후 GitHub 브랜치/PR/현재 README/소스/pytest 상태를 재확인; 이미 구현된 기능은 중복 추가하지 않음.
2. **P0 두 가지**(외부 식별자 단서 보존, 쿨다운 재검사/오류 구분)부터 구현.
3. 순서 불변·암호 보호·본편/패치 구분·잘못된 공식 ID 교차 병합 금지·입력 파일 불변을 검증하는 합성 ZIP/모의 검색 회귀 테스트 추가.
4. 단계별 `time.perf_counter` 측정 구현. UI/분석 함수 분리 유지, 상위 단계/전체 파일 진행률 표시는 계속 제공.
5. 사용자가 실제 JSON을 다음 채팅에 업로드하면 **동일 이름 기준**으로 v0.5 결과와 나란히 비교하고 오탐·누락·시간을 평가. 공개 저장소에는 비식별 집계와 합성 테스트만 반영.
6. 전체 pytest, 가능하면 Windows EXE `--self-test`. EXE 빌드는 **수동 실행**. 실패 시 성공이라고 말하지 않음.
7. GitHub 실험 브랜치에 한글 커밋, PR #2 Draft 유지. `main`과 공개 배포 프로그램은 건드리지 않음.

**별도 자료:** [파일별 역할 안내](FILE_MAP_KO.md), [새 채팅 프롬프트](NEXT_CHAT_PROMPT_KO.md), [검증 체크리스트](REGRESSION_CHECKLIST_KO.md), [실험 전력 상세](README_KO.md).

## 7. 실행·재현과 소통

```bash
python -m pip install -r requirements.txt pytest
python -m pytest -q
python -m pytest -q tests/test_v05_search_and_catalog_experiment.py
python -m experiments.dlsite_detector.identify_cli "<실제 경로>" --online --verify --json
```

Windows 검증판은 GitHub Actions `identity-tester-windows.yml`의 **수동 실행**으로 만들고 성공한 Run의 Artifacts를 받는다. 이 EXE는 PlayDock 본체가 아닌 **독립 검증용**.

**새 채팅에서 첫 수행 동작:** 이 파일 전체 읽기 → 현재 브랜치 GitHub 소스 확인 → P0 버그 재현 → 실제 코드/테스트 수정 → 한글 커밋 → 테스트 결과/남은 이슈 보고. 계획서만 다시 쓰지 말 것.
