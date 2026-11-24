# PlayDock

ZIP·7z·RAR로 보관한 게임을 관리·설치·실행하는 Python/PySide6 데스크톱 앱입니다.

## 현재 진행 중인 독립 실험 — 게임 정체 판독기 v0.5

> 이 실험은 **정식 PlayDock 본체에 아직 연결되지 않았습니다.** 기존 데이터·라이브러리는 변경하지 않습니다. GitHub의 [Draft PR #2](https://github.com/sanato-nb/PlayDock/pull/2)에서만 개발하며 `main`은 미병합 상태입니다.

- [**2026-11-19 인수인계 (최신 상태·실측 수치·다음 작업)**](experiments/dlsite_detector/HANDOFF_2026-11-19_KO.md) — 새 채팅에서 먼저 읽을 기준 문서
- [**새 채팅 시작 프롬프트**](experiments/dlsite_detector/NEXT_CHAT_PROMPT_KO.md) — 그대로 복사해 v0.6 실제 개발을 요청하는 문서
- [파일·폴더별 역할 및 호출 구조](experiments/dlsite_detector/FILE_MAP_KO.md) — 실험 소스·UI·테스트·CI 파일 각각의 역할
- [회귀 테스트 체크리스트](experiments/dlsite_detector/REGRESSION_CHECKLIST_KO.md) — 검색 누락·암호·별칭·속도 계측 검증 기준
- [기존 v0.1~v0.5 개발 기록](experiments/dlsite_detector/README_KO.md) — 구버전 실행 순서가 포함된 역사 기록

**현재 판독 방식:** 압축파일 이름과 압축 내부 근거를 모두 모으고 → 후보를 합쳐 인터넷 검색 → 공식 작품 확인과 로컬 압축파일 내용 대조를 분리. 암호화 파일은 내부를 보지 않습니다.

**실사용 비교:** v0.5에서 129개 검사, 공통 128개 기준 v0.4보다 파일별 소요시간 합이 70.61% 감소했지만 일부 웹 검색 생략이 포함됩니다. 작품 식별 정확도는 독립 정답표 없이 확정하지 않았습니다. 실제 사용자 129개 JSON은 개인 경로·게임명이 포함되어 GitHub에 업로드하지 않았습니다.



## 소스코드 구성

- `src/playdock/ui/` — 화면, 공통 대화상자, 스타일
- `src/playdock/controllers/` — 사용자 동작 및 화면과 기능 연결
- `src/playdock/services/` — 압축 해제·설치·실행 파일 탐색·라이브러리 관리·작업 스레드
- `src/playdock/models/` — 게임 데이터 모델과 식별자
- `src/playdock/database/` — SQLite 작품 저장·조회
- `src/playdock/integrations/` — DLsite 외부 조회
- `src/playdock/core.py`, `src/playdock/work_db.py` — 이전 import 경로를 유지하는 호환 모듈
- `src/playdock/*.py` — 아직 분리되지 않은 이미지·이름 등 기능 모듈
- `app.py`, `title_editor.py`, `setup_wizard.py`, `uninstall_wizard.py` — 각 EXE 진입점
- `scripts/` — Windows 실행·빌드·공개 배포 스크립트
- `tests/` — 자동 테스트
- `docs/` — 한국어 문서 및 사용자 설명서

**중요:** 기존 `core`·`ui` 등 절대 임포트 호환성을 유지하기 위해 진입점과 테스트에서 `src/playdock`을 Python 검색 경로에 추가합니다. 다음 단계에서는 상대 임포트와 정식 패키징으로 이행할 수 있습니다.

## 개발 환경

```bash
python -m pip install -r requirements.txt pytest
python -m pytest -q tests
python app.py
```

Windows 빌드는 `scripts\00_BUILD_WINDOWS_EXE.bat`, 기존 EXE 재포장은 `scripts\01_REPACKAGE_EXISTING_EXES.bat`으로 실행할 수 있습니다. GitHub Actions EXE 빌드는 수동 실행만 허용합니다. Windows 빌드의 실제 성공 여부는 별도 환경에서 검증해야 합니다.

개인 게임 목록, 압축파일, API 키, 이미지 캐시, 사용자 DB는 저장소에 업로드하지 않습니다.

자세한 파일별 역할은 [`docs/소스코드_구조_v0.8.4.md`](docs/소스코드_구조_v0.8.4.md)를 참고하세요.
