# PlayDock — DLsite 이름↔품번 검색기 독립 2종 (2026-11-21)

## 작업 결과
- 독립 Windows 실행 파일:
  - `PlayDock-Name-to-Code.exe` — 작품명/압축파일 이름 → RJ/VJ/BJ/EJ 품번 후보
  - `PlayDock-Code-to-Name.exe` — RJ/VJ/BJ/EJ 품번 → DLsite 공식 작품명
- 두 프로그램은 `scripts/lookup_window.py` UI만 공통으로 사용하고, 검색 엔진은 `experiments/dlsite_detector/reverse_lookup.py`로 분리함.
- 압축파일 선택 처리 `experiments/dlsite_detector/archive_input.py` 신설. GUI 다중 파일 선택 / 폴더 직접 선택 / 직접 입력 병용 / 1,000개 일괄 지원.
- PlayDock 메인 GUI, 라이브러리 DB, 원본 자료에 영향 없음.
- 사용자 제공 129개 결과나 파일명 목록, API 키는 저장소에 업로드하지 않음.

## ZIP·7z·RAR 파일 선택 기능 추가 (2026-11-21)

- 두 실행파일 UI에 `압축파일 선택 (여러 개 가능)`, `폴더 내 압축파일 선택`, `선택 목록에서 제거`, `입력 모두 지우기` 버튼 추가.
- 파일 선택 다이얼로그는 ZIP/7z/RAR만 표시하며 다중 선택 지원. 폴더 선택은 바로 아래의 대상 확장자만 나열하고 재귀 탐색하지 않음.
- 사용자 **파일 내용과 아카이브 내부 파일/메타데이터는 열지 않음**. 로컬 경로는 basename으로만 추출하고 외부 검색에 전달하지 않음.
- 이름→품번: 선택한 압축파일명 정제 후 검색. 품번→이름: 이름에 포함된 유일한 RJ/VJ/BJ/EJ를 추출; 코드가 없거나 복수이면 경고 후 해당 파일 조회를 건너뜀.
- 입력한 텍스트와 선택한 압축파일을 함께 일괄 처리하며, 검색 결과 JSON/CSV에 원래 파일명과 `input_origin`을 기록.
- 네트워크 차단 시 `브라우저에서 직접 찾기`는 텍스트가 없어도 선택된 파일명으로 작동.
- **19건 추가된 압축파일 선택 테스트**로 129개 파일명 일괄 처리, 가짜 아카이브 미개봉, 파일 선택창, 코드 추출 오류 등을 검증.
- 최종 검증: [Actions #44855887839](https://github.com/sanato-nb/PlayDock/actions/runs/44855887839) / 커밋 `3e045bd7bc3a67d605841ff75b5d9d314b981d9e`.
- Windows Python 회귀 **51 passed**, 두 Windows GUI EXE PyInstaller 패키징 및 EXE `--self-test` 모두 성공.
- 새 배포: [Artifact #14687397927](https://github.com/sanato-nb/PlayDock/actions/runs/44855887839/artifacts/14687397927), 2026-12-21 만료 예정.
- ZIP SHA256: `60f967cd18ede36ae5f4cec0509a2802d8f9aff03fa88d91d469f01bb573083b`.
- EXE SHA256: `PlayDock-Name-to-Code.exe` — `f9bf1ec48490ec99472fd142d13e4e8d131c2510a238b2c98b334668a8b4a2d4`; `PlayDock-Code-to-Name.exe` — `cdc98427780560b9e9fe6c372db234ad7a0971b801f57404e8bb0ae54559e065`.
- Windows 실접속은 DLsite 일반 HTML 오류, Google/Bing에서 공식 링크 추출 0건으로 이전과 유사. **실제 검색 성공률 향상은 입증하지 않음.**

## 이름 → 품번
1. `cleaned_search_title`로 파일명/검색어 정리. 개인 디렉터리 경로를 외부로 보내지 않음.
2. DLsite 일반 HTML 검색 페이지의 작품별 공식 URL/품번만 수집 (maniax/home 우선, 비어 있으면 soft/girls).
3. 링크가 없으면 Bing/Google/DuckDuckGo/Mojeek 일반 HTML을 제한적으로 시도.
4. 공식 제품 HTML에서 같은 품번을 다시 찾고 제목과 대조.
5. 제목 정확히 일치한 공식 페이지, 품번만 공식 확인된 페이지, HTML 검색 링크만 얻은 후보를 분리.
6. 자동 조회 장애 시 `브라우저에서 직접 찾기`로 일반 Google 검색을 연다.

## 품번 → 이름
1. 형식 `RJ|VJ|BJ|EJ` + 숫자 6~8자리만 허용.
2. 기존 `fetch_dlsite_html`의 공식 제품 HTML로 품번과 상품명을 확인.
3. 계정·API 키·JSON API 호출 없음. 제품 조회 실패는 '미등록'으로 판단하지 않음.
4. 자동 조회 실패 시 `브라우저에서 직접 찾기`를 통해 공식 DLsite 페이지를 연다.

## 최초 양방향판 회귀 및 Windows 빌드 (압축파일 선택 전 기록)
- 최종 빌드: [GitHub Actions #44772075099](https://github.com/sanato-nb/PlayDock/actions/runs/44772075099), 커밋 `b12fdc4657acdbbeb0f18f7d4aa63d77185a7a7c`.
- Windows Python 테스트: **32 passed** (신규 양방향 합성 테스트 18건 + v0.11.7 HTML 테스트 14건).
- PyInstaller Windows 단독 EXE 2개 생성 성공, 각각 인터넷 없는 `--self-test` 성공.
- 아티팩트: [#14648231736](https://github.com/sanato-nb/PlayDock/actions/runs/44772075099/artifacts/14648231736) (2026-12-20 만료 예정).
- ZIP SHA-256: `97c412eabb316821f155cc0f2e79d6f0544000e6d1a82382cb48f068e277ec2a`.
- ZIP 구성: EXE 두 개와 한국어 사용법 TXT 한 개만 포함.

## HTML 실접속 (Windows CI에서 실행한 제한적 진단)
- DLsite 일반 제목 검색: `PublicHtmlUnavailable / HTTPError` — 자동 접근 실패. **작품 부재 증거가 아님**.
- Bing HTML: 요청은 정상 응답, 공개 검색어 `RPG`의 공식 작품 링크 후보 추출 **0건**.
- Google HTML: 요청은 정상 응답, 공개 검색어 `RPG`의 공식 작품 링크 후보 추출 **0건**.
- 이 진단은 사이트 접근/추출 가능성만 보는 것이며, 사용자의 실제 작품명·품번에 대한 정답률 검증이 **아니다**.
- DLsite 페이지·검색 엔진은 국가, IP, 연령 확인, 사이트 자동 접근 정책, JavaScript 렌더링 여부에 따라 다르게 동작할 수 있음.
- HTML 자동 조회 실패 시 브라우저 직접 검색 버튼 제공. CAPTCHA·연령게이트 등 접근 통제 우회 없음.

## 후속 검증
- 사용자 PC에서 두 EXE를 각각 실행하고, 검색 결과를 JSON/CSV로 제출하면 실제 오류율·적중률을 분리해서 측정할 수 있다.
- 실험 브랜치 `experiment-bidirectional-lookup-20261121`. main 병합·본체 통합 없음.

## 2026-11-21 사용자 검증 JSON 2종 분석 및 이름 검색 수정

사용자가 제출한 검색 결과는 로컬 개인 데이터이며 **저장소에 업로드하지 않았다**. 아래에는 익명 집계만 기록한다.

- 공통 입력: 압축파일 129건.
- 파일명에 DLsite RJ/VJ/BJ/EJ 코드가 있는 파일: 89건, 없는 파일: 40건.
- 기존 이름→품번: `confirmed=0`, `candidates=7`, `no_candidate=99`, `invalid=23`.
  - 품번이 있는 89건 중 `no_candidate=62`, `invalid=23`, `candidates=4`.
  - 품번이 없는 40건 중 `no_candidate=37`, `candidates=3`.
  - 제목이 짧은 일반 단어·제작사명이 무관한 DLsite 작품 후보로 표시되는 사례 확인.
  - 파일명에 적힌 코드와 다른 공식 코드가 후보로 표시된 사례도 확인.
- 기존 품번→이름: `confirmed=87`, `invalid=40`, `unavailable=2`.
  - 코드가 있는 파일 기준 공식 HTML 이름 조회 성공 **87/89 = 97.8%**.
  - `invalid=40`은 파일명에 DLsite 품번 자체가 없어 검색 조건을 충족하지 않은 것. 상품 미등록 판단이 아님.
- 공식 DLsite 작품 제목 **확정**은 게임 파일 내용·번역명·버전 일치를 의미하지 않는다.

### 수정 내용
- `lookup_title`에서 파일명 품번을 제목 제거 전에 추출, 정확히 같은 코드의 공식 HTML 조회를 직접 수행.
- HTML에서 품번·제목 확인 시 `filename_code_verified`, HTML 조회 불가 시 `filename_code_only`. 둘 다 다른 코드로 임의 대체하지 않음.
- 여러 다른 품번이 포함된 파일명은 한 작품으로 자동 결정하지 않음.
- 품번 없는 제목 검색은 관련 없는 작품명(짧은 공통어, 제작사 등)을 결과에서 제외.
- 공식 DLsite 검색 서버가 모두 실패한 경우 단순 '후보 없음'과 구분해 `unavailable` 처리.
- UI 상태명과 공식 조회 성공 집계를 새로운 품번 검증 상태에 맞춤.

### 테스트와 배포
- [GitHub Actions #44857372278](https://github.com/sanato-nb/PlayDock/actions/runs/44857372278)
- **Windows 회귀 테스트 61개 통과**, EXE 2개 빌드 및 자체 진단 성공.
- 최종 배포 ZIP SHA256: `d8b48efc324047d998cb5b14927e43bfd4619192035c550b3e75b6be128c7c56`.
- Windows ZIP Artifact [#14688003195](https://github.com/sanato-nb/PlayDock/actions/runs/44857372278/artifacts/14688003195).
- **개선 후 129건 실측 재검증은 아직 수행되지 않았다.** 87/89는 이전 품번→이름 프로그램의 실측이며 새 이름→품번 성능으로 인용하지 않는다.
- 제목만 있는 40건은 일반 검색 웹페이지 제한 때문에 여전히 성공률이 낮을 수 있으며, 사이트 접근 차단을 우회하지 않는다.
