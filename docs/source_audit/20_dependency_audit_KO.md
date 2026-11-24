# 6-A 외부 라이브러리 사용 및 최소 Qt 설치 후보 감사

기준 24c3728f1abc95fe0c50a47cf53efbb1e9b50409. 5-E 종합 비교 run 45359885842 실행 중. 본체 요구사항은 변경하지 않는다.

직접 의존성 8개:
- PySide6: GUI. QtCore/QtGui/QtWidgets 등 실제 모듈 전수 검사.
- Pillow: 이미지 변환 및 크롭.
- py7zr: 7z, pyzipper: AES ZIP, rarfile: RAR.
- send2trash: 안전한 게임 제거.
- keyring: 잔존 선택적 텍스트 AI의 OS 자격 증명 및 이전 호환.
- ddgs: 잔존 검색/이름 편집 및 온라인 이미지 검색 경로. 현재 공식 품번 수집은 이 패키지에 의존하지 않음.

정적 import가 없다고 바로 삭제하지 않는다. 지연 import와 테스트·실험·패키징 의존성을 분리 기록. 본체 전체 import 경로 및 동적 import 후보, 실제 설치 배포판별 RECORD 파일 바이트를 JSON으로 기록한다.

PySide6 전체 배포판 대신 같은 버전 PySide6-Essentials를 사용 가능한지 별도 깨끗한 venv로 확인. 전체 환경 freeze에서 PySide6 메타 패키지/Addons/Pdf/WebEngine만 제외하며 나머지 버전 유지. pip check, Qt 모듈 import, 전체 Windows 회귀, 기존 빌드 플래그로 후보 EXE 빌드. 결과를 보고 6-B/C에서 정식 requirements와 빌드 경로 변경을 검토. 현재 사용자의 설치본이나 데이터는 변경하지 않는다. RECORD 파일 크기와 EXE 압축 크기는 별개이며 설치 환경 크기 감소가 EXE 크기 감소를 보장하지 않는다.
