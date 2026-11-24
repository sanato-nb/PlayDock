# 7-C 최종 잔존 코드 감사

기준 af10566aeb5a066ac5ee9beb9565823b73895002, 검사 대상 7eeb6afe9bdc3fb7a91eaaab87b06de38b1b51d4. 원본과 현재 Git 트리 직접 비교 결과: 전체 추적 파일 332→430, Python 261→302, src/playdock Python 84→93, 해당 바이트 562478→577880, 루트 진입점 46286→44563 bytes. 독립 experiments 파일 66개 모두 동일 SHA. UI 보호 대상 38개 모두 동일 SHA. 구조 분리, 독립 공식 검색 엔진 이관, 검증·문서 추가 때문에 파일 수 증가; 파일 개수 감소가 목표가 아니다.

확인된 이전 경로 8개 없음: collection_board.py, dark_selector.py, work_db_dialog.py, online_art_dialog.py, ui/artwork_dialog.py, services/artwork_workers.py, services/save_backups.py, save_backups.py (src/playdock 기준). 이름이 같은 새 정식 UI 경로는 유지.

현재 기존 상세 이름 편집기의 텍스트 AI 기능, keyring 자격증명 접근, ddgs 검색 및 기존 설정 호환 필드는 남아 있다. 생성형 이미지 호출 및 AI 설정 메뉴, 게임 세이브 백업과 구형 미사용 UI를 복원하는 것은 금지한다. core.py/work_db.py는 실제 호환 import 경로이고, 독립 실험과 정식 검색 엔진의 소스 중복은 테스트 및 연구 분리 목적이다. 이러한 항목은 단순 미사용 import/중복 후보 수치만으로 자동 삭제하지 않는다. 자동 업데이트·플레이타임·통계 기능은 사용자 요구상 추가하지 않는다.

새 검증은 1단계와 동일 감사 알고리즘으로 두 커밋의 전체 SHA/AST, 미사용 import 및 정적 미도달 후보, 동일 함수 본문, 본체의 실험 의존성 및 폐기 모듈/심볼/생성 API 잔존을 비교한다. 기존 UI 38개와 실험 66개 SHA 검증, Windows 폐기 기능/호환성 집중 테스트 및 전체 회귀를 추가. 후보는 증거별로 보고하고 삭제 여부는 별도 확인한다. 이번 변경은 감사와 문서만이며 프로그램 동작/화면/데이터 무변경.

7-B run 45364463580 성공: 화면 8개+메뉴 6개, 14 PNG 픽셀 차이 0, 보호 소스 차이 0, 구조/좌표 차이 0, UI 회귀 36 passed. 실제 Windows 글꼴/네이티브 프레임 검수 별도. 7-A 1275 passed/1 skipped 및 6-E 교체·제거 데이터 호환 성공. 6-D 전체 실제 창 시작 시간 미확정. 새 잔존 검사와 회귀 결과 확인 전까지 7-C 완료 보류.
