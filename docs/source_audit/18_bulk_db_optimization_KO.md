# 5-D 작품정보 DB 일괄 조회 최적화

기준 d951c7a25f2eee91ec313c651b6ec54a9c1cbe81. 5-C 동일 커밋 전체 회귀 1267 passed, 1 skipped 정상 종료 (run 45358935266). 별도 이미지 집중 검사 성공, EXE 검증 진행 중 (run 45358935325).

공식 게임명 일괄 적용의 기존 사전검사: 게임별 get_link과 get_official_work, 작업자에서 다시 WorkDatabase 초기화와 공식 작품 조회. 새 get_linked_official_works는 400개 ID씩 LEFT JOIN, 연결 1회, 정상 1000게임 3 SELECT. 비표준 이전 링크 정규화와 검증된 URL 필터 유지. get_official_works는 정규화된 (store,code) 중복을 제거하고 400개씩 요청 CTE JOIN. 작업자 db_only 모드도 한 번에 일괄 조회. 공식 이름 적용 UI는 이미 가져온 검증된 작품 레코드를 작업자에 전달, 같은 미리보기 내 DB 재조회 없음. 변경 사항은 다음 미리보기에서 다시 읽는다. 별도 단일 제목 및 네트워크 허용 모드는 기존 방식 유지. 사전검사·worker 결과의 제목/언어 fallback·검증 URL·미확인 제외 규칙 유지. 스키마 및 메타 저장 형식 변경 없음.

검증: 정상/비표준/잘못된/없는 링크, DLsite/Steam 혼합, 중복 작품 키, SQL 파라미터 400단위 분할, 1000게임 사전검사 연결 2000→1 및 SELECT 2000→3, DB/네트워크 재접근 금지된 작업자, 다음 요청 변경 반영, 전체 회귀. 연결 횟수는 repository.connect 측정 기준으로 객체 초기화/스키마 점검 연결 제외. 전체 프로그램 속도 수치는 아님.
