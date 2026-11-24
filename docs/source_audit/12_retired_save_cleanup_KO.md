# 2-D 잔존 게임 세이브 백업 기능 제거

사용자 요구에 따라 메뉴에서 제거되었으나 남아 있던 게임 자체 세이브 백업·복원 기능을 실제 소스에서도 제거한다. 기준 055b845028b0fd476b77d2d7d97101bf4a7af904의 직전 b4ee4d4, 수정 커밋 055b845028b0fd476b77d2d7d97101bf4a7af904.

- services/save_backups.py 삭제
- workers/game_tasks.py의 SaveBackupThread 및 import 삭제
- controllers/game_actions.py의 backup_saves, restore_saves, start_save_worker, save_worker_finished 및 import 삭제
- app.py의 관련 import와 save_worker 상태 삭제
- 폐기된 기능 전용 테스트 5개 제거, 기능 존재를 기대하던 구조 테스트는 현행 기능 검증으로 조정
- 게임 제거 시 세이브도 휴지통으로 이동할 수 있다는 안전 경고는 유지
- 설정, DB, 모음집, 캐시, 기존 백업 ZIP 및 실제 게임 세이브는 삭제하지 않음. 데이터 백업/복원 서비스 변경 없음.
- 테스트에서 남은 본체 심볼 전수 검사와 기존 세이브/백업 보존 확인.

4-A 첫 검증에서는 SQLite 연결 및 SELECT 횟수 각각 2→1 확인, 9 passed, 1 failed. 실패 원인은 새 테스트의 링크 키가 Game.id(해시) 대신 임의 문자열 g였음. 실제 game.id로 수정했다. 프로그램의 DB 처리 로직을 변경하지 않았다. 전체 Windows 검증 전 완료 판정하지 않는다.
