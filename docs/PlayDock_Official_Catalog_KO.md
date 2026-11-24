# PlayDock 공식 작품정보 — v3 통합 방식

이 문서는 과거 별도의 정체 판독기 DB를 다루던 안내를 대체합니다.
정체 판독기와 PlayDock는 **설치 폴더의 `data/playdock.db` 한 개**를 사용합니다.
공식 확인된 DLsite/Steam 품번, 공식 작품명, 종류·분류, 공식 URL, 확인 시각은
메인 `works` 테이블에 저장됩니다. `official_works`라는 활성 테이블은 더 이상 사용하지 않습니다.

설치 위치를 스캐너가 모르면 콘솔에서 PlayDock 설치 폴더를 지정합니다.
설치 표식을 검증하기 전에는 DB를 새로 만들지 않고, 기존 TXT만 생성합니다.
기존 `official_works.sqlite3`는 과거 데이터 이전용 원본으로 보존하며
PlayDock가 처음 시작될 때 한 번만 읽어옵니다.

상세한 10개 works 필드 및 3개 library_links 필드는
`docs/PlayDock_Unified_DB_v3_KO.md`를 참고하세요.
