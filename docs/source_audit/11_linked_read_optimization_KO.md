# 4-A 공식 작품정보 반복 조회 최적화

기준: c8fd2bf0998a3b3b8859267cc07b7677a25218f8. 3-D 검증 성공: 전체 1147 passed, 1 skipped; 실험 폴더 없는 독립 검증 29 passed 및 EXE 빌드 성공. https://github.com/sanato-nb/PlayDock/actions/runs/45348797902

기존 collected_game_record는 library_links 조회 후 works를 별도 SQLite 연결에서 읽었다. get_linked_official_work는 정상 링크의 두 SELECT를 LEFT JOIN 한 SELECT로 통합한다. 과거 비표준 링크는 동일 연결에서 기존 정규화 규칙으로 폴백한다. 공식 URL 검증과 수동 품번 삭제 우선 규칙 유지. 결과 딕셔너리 구조 유지. DB 스키마, 데이터 파일, 인덱스, 기존 get_link/get_official_work는 변경하지 않는다. 장기 캐시를 추가하지 않는다.

공식 이미지 적용 시 같은 record를 재사용하고, 상세 화면의 확인된 작품정보와 품번도 동일 호출 안에서 재사용한다. UI 문구 및 디자인 변경 없음. 정상적으로 연결된 단일 레코드의 기존 2회 연결/2회 SELECT 대비 1회 연결/1회 SELECT를 trace_callback으로 검증한다. 체감 속도 또는 전체 화면의 50% 개선을 주장하지 않는다. 미연결, Steam, 비표준 링크, 잘못된 URL, 수동 해제 및 DB 수정 즉시 반영을 테스트한다. 다음 작업은 목록 전체의 반복 메타데이터/DB 처리 및 합성 벤치마크다.
