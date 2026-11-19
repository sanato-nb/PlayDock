# v0.10 간소화 코드 위치

- `experiments/dlsite_detector/simple_identity.py` — 압축 이름·주요 EXE·README에서 게임 이름과 상품번호만 수집하고 외부 정체 후보 판독
- `scripts/simple_identity_tester.py` — 별도 Windows GUI, 미확인 탭·미확인 재검사·JSON 저장
- `tests/test_v10_minimal_identity_experiment.py` — 합성 ZIP을 사용한 안전·정확도 테스트
- `.github/workflows/identity-tester-windows.yml` — v0.10 독립 EXE 수동 빌드
- `experiments/dlsite_detector/V10_SIMPLIFIED_IDENTITY_2026-11-19_KO.md` — v0.10 구현·검증·주의사항
- `scripts/game_identity_tester.py` — 이전 v0.9 GUI (배포 대상 아님, 기존 회귀 보존)

---

# PlayDock 소스·파일·폴더별 역할 (실험 브랜치 v0.10)

> **시작점:** [인수인계](HANDOFF_2026-11-19_KO.md) · [새 채팅 프롬프트](NEXT_CHAT_PROMPT_KO.md) · [회귀 체크리스트](REGRESSION_CHECKLIST_KO.md).
>
> 아래는 핵심 작업 범위. GitHub 저장소 전체 224개 경로를 무조건 나열하기보다 **새 채팅에서 실제 수정할 기능과 파일을 바로 찾을 수 있도록** 구분했다. 옛 파일을 삭제하거나 이동하지 않고 유지한다.

## 최상위 폴더

```text
PlayDock/
├── README.md                              — 프로젝트 소개와 작업·문서 시작점
├── app.py                                 — 정식 PlayDock 실행 진입점
├── title_editor.py                        — 게임 표시명 편집기 실행 진입점
├── setup_wizard.py                        — 설치 마법사 실행 진입점
├── uninstall_wizard.py                    — 제거 마법사 실행 진입점
├── src/playdock/                          — 정식 PlayDock의 UI·Controller·서비스·DB 코드
│   ├── ui/                                — PySide6 화면 위젯·레이아웃·대화상자·스타일
│   ├── controllers/                       — UI 이벤트와 기능 서비스 연결
│   ├── services/                          — 설치·제거·조회·작업 스레드 및 주요 기능
│   ├── models/                            — 게임 도메인 데이터·식별 모델
│   ├── database/                          — 사용자 SQLite 데이터 보관·조회
│   └── integrations/                      — 외부 플랫폼 연동
├── experiments/                           — 정식 앱에 연결하지 않은 독립 기능 실험
│   └── dlsite_detector/                   — 압축파일 게임 정체 판독기 로직·실험 문서
├── scripts/                               — 실행·빌드·배포 명령 및 독립 검증 GUI
├── tests/                                 — pytest 회귀 테스트·합성 ZIP 픽스처 생성
├── docs/                                  — 정식 PlayDock 문서·구조·공개 배포 안내
└── .github/workflows/                    — CI 테스트 및 필요 시 수동 Windows 빌드
```

## 게임 정체 판독기 주요 파일별 역할

```text
experiments/dlsite_detector/
├── __init__.py                — 독립 실험 Python 패키지 초기화
├── archive_encryption.py      — ZIP/7z/RAR 암호화 여부 확인
├── archive_inspector.py       — 압축 내부 항목·크기·EXE·엔진·작품번호·언어 단서 수집
├── internal_metadata.py       — 기본 README 제한 필드만 읽기; 레거시 정밀 설정 파서는 명시적 선택 시만 사용
├── metadata_fields.py        — 엔진별 gameTitle/product_name 등 허용 필드 판별
├── search_terms.py           — 압축파일 이름에서 검색용 제목 정제
├── identity_hints.py         — 작품번호·Steam ID·버전·배포/번역 단서 추출
├── search_plan.py            — 파일명·내부 목록·README 통합 검색 계획; 압축파일명 제목 검색 보장
├── search_session.py         — GUI 배치 검색 캐시·에러/쿨다운 제한·검색 재시도 대기열 및 통계
├── detector.py               — DLsite 등록번호·타입 조회
├── steam_client.py           — Steam 개별 앱 정보 조회
├── pipeline.py               — 일반 웹 검색·검색 결과 근거 및 후보 판정
├── enhanced_search.py        — DLsite·Steam 통합, 웹 코드-공식 제목 교차 확인으로 무관한 작품 ID 오인 방지
├── web_alias_discovery.py    — 다국어 이름·영문 병기 웹 단서 추출
├── storefront_candidate.py   — itch.io/Steam 진짜 작품 홈 판별; 댓글·devlog 오인 차단
├── catalog_aliases.py        — 공식 다국어 별칭과 검증된 DLsite↔Steam 교차 근거를 통한 보수적 상품 병합
├── archive_identity.py       — 암호·내부 구조·README 수집 후 통합 검색; 시간 계측·검색 실패 재검사
├── evidence_normalizer.py    — 파일명·목록·메타·공식 웹 근거를 출처별 정규화
├── identity_matcher.py       — 작품 ID/공식 제목/내부 근거 비교
├── identity_verifier.py      — 6단계 보수 판정과 카탈로그·로컬 상태 구분
├── verification_report.py    — 근거·제한·판정 코드 JSON 보고서 데이터 모델
├── identify_cli.py           — 단일 압축파일 통합 판독 명령행 진입점
├── archive_cli.py            — 웹 미사용 압축 목록 확인 명령행 진입점
├── cli.py                    — 초기 DLsite 등록 조회 명령행 진입점
├── pipeline_cli.py           — 독립 실험 DB·이름 변경/수동판정 실행 명령행 진입점
├── filename_batch.py         — 게임 압축파일 이름 목록 일괄 실험
├── review_store.py           — 독립 실험 SQLite 수동 검토·이름 변경 이력 관리
├── artwork_staging.py        — 아이콘·이미지 단계적 변경·복원 실험
├── README_KO.md              — v0.1~v0.5 상세 변경 이력(이전 규칙 일부 포함)
├── V06_IMPLEMENTATION_2026-11-19_KO.md — v0.6 실제 구현·테스트·남은 한계
├── V07_IMPLEMENTATION_2026-11-19_KO.md — v0.7 파일명·내부 구조·README 기반 실제 개발 기록
├── V08_ACCURACY_2026-11-19_KO.md — v0.8 오인 차단·후보별 공식 ID 근거 분리 및 검증
├── V09_ACCURACY_2026-11-19_KO.md — v0.9 다중 EXE 역할 필터·상품 관계·웹 제목 판정 강화
├── HANDOFF_2026-11-19_KO.md  — 현재 상태·실측 검증·다음 작업·제약사항
├── FILE_MAP_KO.md            — 현재 파일·폴더 및 호출 경로 설명
├── REGRESSION_CHECKLIST_KO.md — 새 버전 기능·안전성 검증 기준
└── NEXT_CHAT_PROMPT_KO.md    — 새 채팅에 그대로 입력할 실제 개발 요청
```

## GUI·테스트·워크플로

```text
scripts/
├── game_identity_tester.py            — 독립 Tkinter GUI(진행률·검색 실패 재검사·단계별 시간·JSON/CSV 내보내기)
└── Identity-Tester-README_KO.txt       — 독립 Windows 테스트 EXE 사용 방법

tests/
├── test_v05_search_and_catalog_experiment.py       — v0.5~v0.6 검색·별칭·쿨다운·이중 판정
├── test_v07_filename_structure_readme_experiment.py — v0.7 README 읽기 제한·파일명 검색 보장·원본 불변성·자체 테스트
├── test_fast_combined_scan_v04_experiment.py       — 속도/중복 조회 제한과 내부 단서 통합
├── test_internal_first_search_v03_experiment.py    — 검색 전 이름+내부 근거 수집 및 암호 정책
├── test_archive_identity_pipeline_experiment.py   — 압축 식별 파이프라인·근거 순서
├── test_internal_metadata_experiment.py            — 내부 설정필드 파싱·제한/예외
├── test_metadata_evidence_stage5_experiment.py     — 5단계 설정 근거/판정 유효성
├── test_identity_verification_stage6_experiment.py — 6단계 최종 일치/충돌/미확인 회귀
├── test_gui_progress_and_alias_recovery_experiment.py — GUI 진행률 및 별칭 후보 복구
├── test_password_archives.py                      — 암호화 아카이브 안전 정책
└── test_search_quality_experiment.py              — 검색 질과 잘못된 후보 회귀

.github/workflows/
├── python-tests.yml                   — 변경사항/PR의 전체 Python pytest CI
├── identity-tester-windows.yml        — 독립 판독기 Windows EXE 수동 빌드·자체 테스트
└── build-windows-exe.yml              — 정식 PlayDock 공개 배포 수동 빌드(판독기와 별도)
```

테스트 목록은 대표 항목이며 전체 프로젝트 `tests/`에는 본체 UI/DB/기능의 다른 많은 테스트가 있다. 정확한 최신 목록은 GitHub 브랜치 `git tree`를 다시 확인한다.

## 주요 호출 구조

```text
scripts/game_identity_tester.py          — UI: 사용자가 파일·모드·진행률 선택
         ↓
experiments/dlsite_detector/archive_identity.py  — 서비스: 파일명+내부 근거 동시 활용
    ├─ archive_encryption.py             — 암호 상태 확인
    ├─ archive_inspector.py              — 파일 목록·EXE·엔진 단서
    ├─ internal_metadata.py              — 제한된 메타데이터 내용
    ├─ search_plan.py                    — 파일명+내부 근거로 검색 계획 완성
    └─ search_session.py                 — 배치 캐시/오류 제한
         ↓
enhanced_search.py / pipeline.py / detector.py / steam_client.py — 웹/플랫폼 조회
         ↓
identity_verifier.py + identity_matcher.py — 별칭/공식 ID/내부 근거 대조
         ↓
verification_report.py                   — 읽기 전용 이중 판정·근거 JSON
         ↓
scripts/game_identity_tester.py          — UI에 현재 단계·판정·실측 시간 표시
```

## 구조 유지 원칙

- **UI는 함수 호출과 표시만** 담당. 압축 판독/검색/제목 비교/최종 판정은 `experiments/dlsite_detector/`에 둔다.
- 정식 PlayDock `src/playdock/ui/` ↔ `controllers/` ↔ `services/` 분리 체계를 임의로 뒤섞지 않는다.
- 독립 실험은 아직 정식 PlayDock 사용자 DB를 변경하지 않고, 불변 `read_only=true` 보고서를 출력한다.
- 기존 CLI와 호환 테스트를 유지하면서 새 인터페이스가 필요한 경우 추가하고 옛 사용자를 깨뜨리지 않는다.
