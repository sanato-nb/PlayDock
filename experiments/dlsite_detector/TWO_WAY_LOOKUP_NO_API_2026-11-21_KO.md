# PlayDock — DLsite 이름↔품번 검색기 독립 2종 (2026-11-21)

## 작업 결과
- 독립 Windows 실행 파일:
  - `PlayDock-Name-to-Code.exe` — 작품명/압축파일 이름 → RJ/VJ/BJ/EJ 품번 후보
  - `PlayDock-Code-to-Name.exe` — RJ/VJ/BJ/EJ 품번 → DLsite 공식 작품명
- 두 프로그램은 `scripts/lookup_window.py` UI만 공통으로 사용하고, 검색 엔진은 `experiments/dlsite_detector/reverse_lookup.py`로 분리함.
- PlayDock 메인 GUI, 라이브러리 DB, 원본 자료에 영향 없음.
- 사용자 제공 129개 결과나 파일명 목록, API 키는 저장소에 업로드하지 않음.

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

## 실제 회귀 및 Windows 빌드
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
