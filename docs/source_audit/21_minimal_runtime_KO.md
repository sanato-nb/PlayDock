# 6-B 정식 최소 Qt 의존성 적용과 기존 이름 편집기 지연 로딩

기준 fdf7cbcd9ab8ee431fa1c453c93ff7eca7df5faf. 6-A run 45360145712에서 전체 의존성 감사 및 동일 버전 최소 Qt 설치, pip check, 전체 회귀 성공을 확인. 후보 EXE 빌드는 진행 중으로 최종 결과는 별도 확인한다.

requirements.txt: PySide6 전체 메타 배포판 대신 PySide6-Essentials (동일 지원 버전 범위). 불필요한 Addons/Pdf/WebEngine을 새 환경의 직접 설치 대상에서 제외. QtCore/QtGui/QtWidgets API는 변경하지 않는다. 기존 venv를 강제로 수정하거나 라이브러리를 삭제하지 않는다.

controllers/metadata.py: TitleEditor import를 실제 open_title_editor 호출 시점으로 이동. 정상 본체 import 경로에서 기존 상세 편집기의 UI/controller 모듈을 미리 로드하지 않는다. 현재 공식 이름 설정 및 수동 이름 변경, 기존 TitleEditor의 실제 기능 및 저장 형식 유지. PyInstaller가 함수 내부 import도 수집하므로 아직 구형 편집기 자체를 EXE에서 제외했다는 의미는 아니다.

keyring, ddgs는 기존 상세 편집기의 텍스트 AI/웹 검색 및 온라인 이미지 검색 구현에 남아 있어 유지. AI 설정 UI와 외부 프롬프트 방식에는 변경 없음. 불필요한 기능 삭제 여부와 배포 의존성 제외는 호출 경로의 별도 확인이 필요하다. 사용자 설정, DB, 압축 및 설치 데이터 변경 없음.

추가 검증: 새 프로세스에서 app import 후 title_editor/controller/editor_layout 미로딩, 명시적 import 정상, 정식 최소 requirements, 기존 메뉴와 상세 이름 관리자 회귀, 전체 Windows 테스트 및 정식 설치/제거 EXE self-test. 기존 6-A 비교 workflow는 역사적 기준 커밋으로 수동 실행 가능하도록 고정.
