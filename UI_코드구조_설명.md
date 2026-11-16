# PlayDock v0.8.2 — 소스코드 구조

UI 언어: **Python / PySide6 Qt Widgets**, 스타일: **QSS**, DB: **SQLite**.

## 의존 방향

1. `app.py`, `title_editor.py`가 메인 창 객체를 생성하고 UI 레이아웃 함수를 호출한다.
2. `ui/`는 위젯, 화면, 대화상자, 클릭 신호와 콜백 연결을 담당한다.
3. `controllers/`는 콜백을 받아 게임 선택/설치/이름 변경 등 흐름을 조정한다.
4. `services/`는 실제 오래 걸리는 작업을 QThread에서 실행한다.
5. `core.py`, `work_db.py` 등 기존 독립 함수가 압축파일·DB·이름 정보를 처리한다.

기존 공개 API(예: `app.MainWindow`, `title_editor.TitleEditor`, `app.InstallThread`)는
가능한 경우 import 재노출을 유지했다. **UI 모듈에 Controller를 import하는 역방향 연결은 추가하지 않았다.**

## 파일 트리

```text
PlayDock/
├── app.py                          # 메인 실행 및 MainWindow 초기화
├── title_editor.py                 # 독립 이름 편집기 실행/초기화
├── ui/
│   ├── launcher_layout.py          # 메인 라이브러리 화면 배치
│   ├── editor_layout.py            # 이름 편집 화면 배치
│   ├── widgets/launcher.py         # 필터 버튼, 팝업 메뉴, 배너 그리기
│   ├── dialogs/common.py           # 공통 다크 대화상자/메시지/입력
│   ├── dialogs/library.py          # AI 설정, 첫 실행, 데이터, 캐시, 모음집
│   ├── dialogs/title.py            # 제목 후보/일괄 수정 대화상자
│   ├── artwork_dialog.py           # 인터넷 이미지 선택/크롭
│   ├── work_info_dialog.py         # DLsite 작품 정보 창
│   ├── collection_board.py         # 모음집 표시
│   ├── selectors.py                # 다크 메뉴 선택 컴포넌트
│   └── styles.py                   # 공통 QSS
├── controllers/
│   ├── library.py                  # 목록/모음집/게임 상세/검색
│   ├── game_actions.py             # 설치/제거/실행/세이브/EXE 선택
│   ├── metadata.py                 # DLsite·이미지 조회/제목 편집기 호출
│   ├── window_actions.py           # 상단 메뉴/정렬 등 이벤트
│   └── title_editor.py            # 제목 편집·일괄 변경·언어 관리
├── services/
│   ├── workers.py                  # 설치/제거/세이브 백업 QThread
│   └── title_workers.py           # 제목/다국어/일괄 조회 QThread
├── core.py                         # 압축 파일/설치/실행 등의 도메인 함수
├── work_db.py                      # 작품 SQLite DB
├── tests/                          # 기능 테스트 및 구조 검증
└── .github/workflows/             # Windows 빌드/배포
```

## 실제 코드 호출 예시

```text
ui/launcher_layout.py
  [게임 설치] 클릭 시 self.install_game 호출
         ↓
controllers/game_actions.py
  GameActionControllerMixin.install_game
  게임/비밀번호/진행률 작업 준비, 작업 스레드 실행
         ↓
services/workers.py
  InstallThread.run
         ↓
core.py
  install(game, progress, password)
         ↓
QThread Signal → Controller에서 UI를 갱신
```

## 보장 범위와 한계

- 원본 압축파일·게임 저장 경로·개인 API 키·작품 데이터의 이동/초기화는 하지 않는다.
- 이전 JSON 및 SQLite 데이터의 형식을 이 작업에서 변경하지 않는다.
- 기존 기능 테스트는 실행하지만 PySide6가 설치되지 않은 Linux 환경에서는 GUI 실물 클릭/화면 테스트가 불가능하다.
- Controller 메서드는 기존 Qt MainWindow의 메서드를 믹스인으로 분리한 점진적 리팩터링이다.
  향후 의존성 주입으로 독립 Controller 객체를 구성할 수 있으나 이번에는 호환성 우선.
- 대화상자의 입력 검증 등 일부 화면에 밀접한 로직은 `ui/dialogs`에 남겨두었다.

## GitHub

- 저장소: `https://github.com/sanato-nb/PlayDock`
- 모든 커밋 제목 및 본문은 한국어로 작성한다.
- `data/`, API 키, 게임 압축파일과 개인 설정을 절대 커밋하지 않는다.
- `UPLOAD_TO_GITHUB.ps1`는 로컬 사용자 데이터가 아닌 이 소스 폴더만 새 클론에 복사해 커밋한다.
