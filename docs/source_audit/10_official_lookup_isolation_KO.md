# 3-D 정식 기능과 실험 코드 독립

기준: 535cdced1e890562545658d7c3ae4fecee67e47a. 3-B 및 3-C 각각 Windows 1100 passed, 1 skipped, EXE 빌드 성공. UI 선언 24개 동일.

정식 조회 엔진을 src/playdock/integrations/official_lookup/에 승격한다. 필수 파일 code_only.py, detector.py, no_api_html.py, steam_client.py, search_terms.py는 기준 실험 원본 blob을 그대로 복제하여 동작 차이가 없도록 고정한다. 실험용 원본은 연구 재현성과 독립 실행을 위해 유지한다. 복제된 실험 원본은 역사적 비교용이며 앞으로 정식 기능 수정은 integrations/official_lookup에서 진행한다. 중복 및 미사용 검색 함수 정리는 이후 최적화에서 검토한다.

본체 세 호출부(controllers/metadata.py, services/catalog_collection_service.py, workers/identity_artwork.py)의 import만 변경한다. DLsite 우선, Steam 폴백, 무품번 제외, API 키 불필요, 공식 URL 검증 등 기존 동작 유지. 4개 현행 기능 테스트는 정식 타입을 사용하도록 갱신. 기존 실험 테스트는 유지하며 품번/우선순위 테스트를 정식 엔진에도 추가한다. 실험 import 차단 상태에서 본체 import 및 합성 조회 확인. CI의 임시 작업공간에서만 실험 폴더를 이동하고 복원하며, 실험 없이 Windows EXE 빌드 검증한다. 사용자 데이터와 DB 스키마 변경 없음. main 미병합.

이전 검증: [3-B](https://github.com/sanato-nb/PlayDock/actions/runs/45345348205), [3-C](https://github.com/sanato-nb/PlayDock/actions/runs/45345592072).
