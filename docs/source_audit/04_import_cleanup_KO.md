# 2-A 미사용 import 정리

기준: a0e538e2b175b17030db86120878331166e6d4c5, 원본 정적 감사 af10566aeb5a066ac5ee9beb9565823b73895002.
- 97개 본체 후보 중 명백한 미사용 이름 19개 제거. 나머지 78개는 호환용 재수출/이전 API 및 보류 대상 이름으로 보존한다.
- core.py, cache_management.py, data_management.py, work_db.py, artwork.py의 자격증명 재수출, settings_service.py의 폴더/API 이름, ui/work_info_dialog.py의 WorkLookupThread 호환 import, services/install_service.py의 ArchivePasswordInvalid 및 services/library_service.py의 safe_folder_name은 유지한다.
- app.py와 title_editor.py는 표준 라이브러리 및 Qt 미사용 import를 추가 제거했다. 기존 명시적 호환 재수출과 다른 프로젝트 모듈 import는 후속 단계 전까지 유지한다.
- 기존 함수 본문·클래스·메뉴·설정·데이터·압축 처리·DB 구조 변경 없음. 기존 파일 삭제 없음.
- import 전용 AST 비교, 전체 추적 Python 파일의 외부 import 및 속성/문자열 참조 후보 재점검, Windows 전체 회귀 테스트를 실행한다. 검증 완료 전 main 병합하지 않는다.
- 미사용 import 제거 자체의 실행속도 향상은 아직 측정하지 않았다.
