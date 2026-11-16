# PlayDock

ZIP·7z·RAR로 보관한 게임을 관리·설치·실행하는 Python/PySide6 데스크톱 앱입니다.

## 소스코드 구성

- `src/playdock/ui/` — 화면, 공통 대화상자, 스타일
- `src/playdock/controllers/` — 사용자 동작 및 화면과 기능 연결
- `src/playdock/services/` — 작업 스레드 및 서비스 로직
- `src/playdock/*.py` — 기존 코어·이미지·DLsite·DB 기능 모듈 (기능별 추가 정리 예정)
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
