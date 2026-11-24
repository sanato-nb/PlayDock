# PlayDock 설정 → DB 상태 (통합 v3)

상단에는 **새로고침, 설정** 버튼만 두며, 설정 메뉴의 DB 상태 확인에서
설치된 PlayDock `data/playdock.db`를 읽기 전용으로 조회합니다.

- SQLite 스키마 버전 (v3)
- 작품 수 (`works`) 및 DLsite·Steam별 건수
- 사용자가 직접 설정한 게임-작품 연결 수 (`library_links`)
- 현재 라이브러리 게임 수
- SQLite 무결성 검사 결과

기존 `official_works.sqlite3`는 이전용 원본이며 별도의 활성 DB로 사용하지 않습니다.
표시 동작은 읽기 전용이고 게임·DB 데이터를 수정하지 않습니다.
