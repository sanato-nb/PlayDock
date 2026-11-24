# 6-C Windows EXE 빌드 구성 최적화

기준 9171287118c948fc84b90e4e5b4e8d2987e4eab4. 6-B 정상 종료: 1275 passed, 1 skipped, 본체 67,732,138 bytes, 설치기 90,157,523 bytes, 제거기 11,517,237 bytes (45360569948). UI 보존 검증 45361084316: 기준/현재 각각 화면 8개 및 메뉴 6개 캡처, UI_SOURCE_CHANGED_REVIEW [], UI_CONTRACT_MATCH, UI 회귀 36 passed.

- send2trash 전체 서브모듈 수집에서 Windows 하위 모듈 수집과 배포판 메타데이터 복사로 변경. macOS/GIO/기타 플랫폼 모듈 제외. 기존 빌드 경고(Windows에서 send2trash.mac import 실패)를 예방. Windows 실행 경로 유지. keyring, ddgs, pyzipper 등의 기존 의존성/동적 수집 유지.
- build_setup_windows.bat를 정식 Build-Windows-Release.ps1 호출로 통합. build_exe_windows.bat의 위임 방식은 기존 유지. 00_BUILD_WINDOWS_EXE.bat 안내의 별도 이름 관리자 EXE 오기 수정. 실제 EXE 3종 및 이름/설치기 payload 유지.
- pip check 추가. 기존 의존성 및 데이터 저장 방식 불변.
- 빌드 후 실제 CArchive/PYZ의 Qt DLL 및 Windows 플랫폼 플러그인, 필수 모듈과 비Windows 휴지통 모듈 제외 확인. 별도 임시 설치 표식/합성 설정을 가진 본체 EXE 실행 및 DB 초기화 확인. 이는 실제 모든 GUI 동작을 보장하는 검증은 아니며 최종 설치/제거 및 성능 비교는 별도.
- 이전 BAT 정적 검사를 단일 정식 빌드 경로에 맞게 갱신. UI 보호 대상 38개 파일 모두 변경하지 않는다. 본체 실행 소스/설치기 및 제거기 UI/사용자 데이터 변경 없음.
- 실측 크기와 실행 시간의 최종 동일환경 비교는 6-D. 현재 단계의 결과는 CI 성공 후 확정.
