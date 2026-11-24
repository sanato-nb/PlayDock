# 3-C UI 대화상자 분리

기준: 0b65c68c678d85c418d0d77895676101cc874709.
기존 common/library/title 모듈의 24개 최상위 함수·클래스를 10개 역할별 모듈로 분리한다. common은 입력/확인, file_dialog는 파일 선택, caption은 캡션 필터, folder_settings는 폴더, collection_settings는 모음집, cache_manager는 캐시, data_manager는 데이터 관리, library는 속성, title_preview는 미리보기 및 후보 선택, title은 일괄 이름 설정이다. UI 동작·디자인·기존 커스텀 파일 선택 제목 표시줄 구현을 보존한다. 기존 Controller/진입점 import 및 테스트 소스 조회 경로를 갱신한다. 서비스·DB·스토리지·작업 스레드·실험 코드는 그대로 둔다. 기존 import 중 일부는 보수적으로 유지한다. UI 내 기능 로직 추가 분리는 별도 검토한다.

검증: 24개 선언 AST 동일, 이전 import 검사, 전체 Windows 회귀 및 EXE 빌드. 검증 성공 전 main 병합하지 않는다. 3-B 첫 감사 실패는 이전 워크플로 hidden-import 경로 1건이며 0b65c68c678d85c418d0d77895676101cc874709에서 수정했다.
