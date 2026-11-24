# 4-C 공통 함수 통합

기준 664983d4809e5d0958ead8d535a3825ad00ec99a. 4-B run 45356458478: 집중 56 passed, 제목 metadata 3→1 및 sidebar title 5→1 로그 확인. 전체 1210 passed, 1 skipped 출력 후 프로세스 종료 코드 1로 작업 실패. 원인은 확정되지 않았으므로 4-C에서 재검증하며 성공으로 처리하지 않는다.

동일 구현 세 종류를 한곳으로 통합:
- 설치기 desktop_directory는 install_management.desktop_directory를 import. Windows 알려진 폴더와 fallback 유지.
- artwork._decode_json은 ai_providers._extract_json의 별칭. 기존 JSON 파싱 및 예외 동작 동일.
- 정식 Steam 명시 식별 패턴은 models/game_codes.py에서 정의. official_work_service 및 integrations/official_lookup/code_only가 동일 객체를 사용. 파일명 추출과 명시적 수동 입력 등 기존 호출자별 규칙은 변경하지 않는다.

기존 import 이름 유지, 실험용 원본 유지, DB와 데이터 형식 및 UI 변경 없음. 서로 유사하지만 의미가 다른 DLsite 품번 패턴, 캡션 필터 등은 무리하게 통합하지 않는다. 공통 함수 동일 객체·입출력 검증과 4-B 재검증, Windows 전체 테스트 및 EXE 빌드 수행. AI 텍스트 기능 범위 확대 없음.
