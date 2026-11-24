# 7-E 최종 배포 후보 및 통합 준비

기준 ab3396ed49e85ed1dc3f11260d11508af1d1c84c. main 3f92ff58dad3ecff227b0b17f81d35b0cd425333. 비교 결과 기준 브랜치는 main보다 47 커밋 앞서며 뒤처진 커밋 0 (7-E 변경 전). main을 아직 변경하지 않는다.

## 7-D 실제 검증
[45368027082](https://github.com/sanato-nb/PlayDock/actions/runs/45368027082) 성공: 전체 1276 passed, 1 skipped, 10 기능군 누락 0, 정식 설치기/제거기 self-test, 실제 EXE 내부 검사, 격리 실행 및 정리 성공. 본체 67711209 bytes, 설치기 90138072 bytes, 제거기 11518098 bytes. UI 최신 코드 ce6eed0의 보호 38 SHA, 14 화면 픽셀 일치, 36 UI 테스트 성공. 7-D/7-E는 UI·기능 소스 미변경.

## 마지막 배포 후보 검증
통합 Windows CI에서 한 번 빌드한 실제 파일로 원본 대비 잔존 감사와 기존 데이터 호환 재검증(최적화 브랜치), 깨끗한 공개 ZIP 생성, 독립 파일 목록/데이터/표식/체크섬 검사, 실제 빌드와 ZIP/설치기 바이트 일치 확인. 성공 이후만 본체/설치기/전체 패키지 별도 아티팩트 생성. 테스트에 임의 개인 데이터 항목/변조 EXE 차단 검증 추가. 기존 README/안내/변경 기록 최신화. PDF는 과거 기록 유지하고 TXT가 최신임을 명시한다. main의 구형 중복 자동 빌드 트리거는 통합 CI로 이관하며 수동/독립 브랜치 검증 보존.

공개 GitHub Release 또는 버전 태그 생성하지 않는다. 기존 패키지 라벨 v0.8.3과 설치 내부 버전 0.8.0의 차이는 사용자 승인 후 버전 정책 별도 확정. 검증 아티팩트는 실행 커밋 및 public_bundle.json으로 식별한다. 정식 릴리스로 오인하지 않도록 개발 후보로 안내.

## 남은 검수 및 통합 조건
- 최종 후보 CI 및 독립 ZIP 검사 성공 확인.
- 실사용 Windows에서 한글 글꼴/네이티브 제목줄/고 DPI/실제 게임 및 온라인 조회 확인. CI 오프스크린 자동 비교만으로 보증하지 않는다.
- 실제 Windows 전체 시작 시간 측정은 CI에서 HWND 확인 실패로 미확정. 크기 비교 완료.
- ZipCrypto 1개 skip은 별도 테스트 환경 필요.
- 기존 설정/호환 경로/선택적 텍스트 AI 검색 보존. UI 기준 승인 없이 변경 금지.
- 초안 PR로 변경을 검토할 수 있게 준비하되 최종 검증 및 승인 전 main 병합·공개 출시 없음.

## 최종 자동 검증 완료 — 2026-11-24
검증 대상 커밋 `ad4e2d9815aa1bbbaa5989c94ed81a27a0fec1bf`. [Windows 통합 검증 45369495467](https://github.com/sanato-nb/PlayDock/actions/runs/45369495467) 성공. 전체 1280 passed, 실패 0, skip 0 (37.01초). 기능별 검증, 정식 EXE 3종 및 자체 검사, 동결 EXE 내부 구성·격리 실행, 잔존 감사, 사용자 데이터 호환, 개인정보 제외 공개 ZIP 및 독립 체크섬 검사 모두 성공. 이전 합성 데이터 10개 및 게임 파일 5개, 게임 3개/모음집 2개 보존. 배포 후보:
- [기존 설치 교체용 본체](https://github.com/sanato-nb/PlayDock/actions/runs/45369495467/artifacts/14907418915): PlayDock.exe 67708901 bytes, SHA256 d89b837d320071c3fc1f7d3ae2e2634c2df4e115e3f6b3134827becc5645cefd.
- [신규 설치기](https://github.com/sanato-nb/PlayDock/actions/runs/45369495467/artifacts/14907634324): 90135216 bytes, SHA256 4515a1030127a531c3a46bcfa02f05e2ff900326d1e0c0f82ba6e972814affdf.
- [전체 배포 ZIP](https://github.com/sanato-nb/PlayDock/actions/runs/45369495467/artifacts/14907204659): 168682051 bytes, SHA256 900c4ff2ad7105030f7aeaa4bac1b6b673676255917237c6006df53b2847d2b2. 허용된 9개 항목, data/ 빈 상태.
- [검증 증거](https://github.com/sanato-nb/PlayDock/actions/runs/45369495467/artifacts/14907809093).

최적화 구현 및 자동 검증 종료. 최종 검증 후 이 문서 및 체크리스트만 변경하며 제품 소스·테스트·빌드·UI는 검증된 커밋과 동일하다. PR #3 검토 상태 유지. 실제 Windows 사용자 화면/게임/외부 사이트 및 시작 시간 검수 미실시; 정식 버전 확정 및 main 병합/공개 출시 전 해당 사항 확인. 배포 후보는 기존 0.8.3 포장 라벨을 유지하며 정식 새 버전이 아니다.
