# 7-E 후속 — 마지막 ZipCrypto 회귀 검사 및 실제 Windows 검수

기준 d49f6023e3f12c30d8edcb62a420e4aa431545ba. 이전 통합 검증 45368027082: 1276 passed, 1 skipped. skip은 ZipCrypto 생성용 zip CLI 부재였다.

## 외부 도구 없는 실제 암호화 ZIP 검증
Info-ZIP 명령 `zip -q -X -j -P my-test-secret Secret.zip Game.exe`로 만든 실제 traditional ZipCrypto ZIP(148 bytes, synthetic Game.exe 내용 6 bytes MZtest)을 테스트 내 base64로 고정. SHA256 d06263980e6875153c0b8ca904dc8e84e280c88629c19676dfa3515c8c65a0d4. 실제 표준 zipfile에서 암호화 플래그, 저장 방식, 올바른 암호 읽기, 틀린 암호 오류를 독립 확인. 테스트는 원래의 누락/오류 암호 예외, 실패 시 설치 폴더 미생성, 정상 설치 및 원본 보존을 모두 유지한다. 앱 실행 코드, 압축 처리 안전 제한, UI, DB 및 사용자 데이터 구조 변경 없음. 추가 외부 의존성 없음. 새 통합 CI 결과 전에는 0 skip을 확정하지 않는다.

## 실제 Windows 최종 확인 체크리스트
별도 임시 게임 폴더와 앱 데이터 백업을 준비한다. 기존 사용자라면 프로그램 종료 후 EXE 교체만 수행하고 data/와 게임 폴더는 유지한다. 새 사용자 확인은 별도 Windows 계정/Sandbox에서 수행한다. 최종 성공한 커밋의 아티팩트만 사용한다.
- [ ] 실제 Windows 창: 100%/125% DPI, 한글 글꼴, 제목줄, 최소화/최대화/크기 조절.
- [ ] 라이브러리와 모음집, 검색/정렬, 배너/아이콘, 하단 여백 및 상단 메뉴가 기존 UI 기준과 동일.
- [ ] 게임 정보 수집 전 기능 버튼 비활성, 수집 후 조건별 활성. DLsite·Steam 실제 공식 조회와 제외 목록 확인.
- [ ] 게임 관리 4개 기능, 공식 이름/이미지 선택 적용, 파일 선택창 어두운 제목줄.
- [ ] 보유한 정상 ZIP/7z/RAR 샘플 설치/실행/제거, 암호 입력 오류 처리. 실행 파일 안전 확인.
- [ ] 기존 사용자 설정/DB/모음집/이름/이미지 보존, 원본 압축 파일 유지.
- [ ] 새 설치와 제거기 UI 확인. 앱 데이터·설치 게임은 삭제하지 않음.
- [ ] 기존과 후보 EXE의 실제 시작 시간 필요 시 동일 PC/게임 목록에서 준비 실행 후 교차 반복. scripts/benchmark_frozen_exe.py는 Python 3.12 Windows에서 --baseline / --optimized (각 EXE 3종 포함 폴더) --output 경로로 사용 가능; CI는 HWND 확인 실패로 실제 시작 시간 미확정.

자동 검증과 실제 사용자 Windows 확인을 구분한다. main 병합 및 정식 공개 버전 확정은 아직 수행하지 않는다.
