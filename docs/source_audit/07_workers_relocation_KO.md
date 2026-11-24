# 3-A 작업 스레드 독립 계층 분리

기준: 6182f8c03e4a6d5923b77f6ded5d5c5d5cd90db8.
이동 커밋: 55f4fb7f91e0d13a59d817234c7474ce28af28a6.

| 기존 services 파일 | 새 workers 파일 |
|---|---|
| workers.py | game_tasks.py |
| catalog_collection_worker.py | catalog_collection.py |
| identity_artwork_worker.py | identity_artwork.py |
| title_workers.py | title.py |
| work_lookup_worker.py | work_lookup.py |

기존 blob을 그대로 이동하여 원본 함수·클래스·Signal·QThread 동작과 취소 로직은 바꾸지 않았다. 새 패키지 초기화 파일을 추가했다. 본체 8개 호출부는 import 경로만 변경했다. 회귀 테스트의 실제 worker import, monkeypatch 모듈 별칭, 소스 검사 경로와 Windows 워크플로 감시 경로를 갱신했다. services 내부에는 QThread 상속 구현을 두지 않는다. 이전 단계 검증은 해당 커밋에 고정한다.

검증: 이동 파일 SHA 동일, 다른 본체와 실험 파일 보존, 본체 호출부가 지정 import 변경만 포함하는지 비교, 저장소 Python/빌드의 이전 경로 검사, 전체 Windows 테스트 및 EXE 빌드. 최종 결과 확인 전 main 병합하지 않는다.

2-C의 초기 감사 실패는 실제 캐시 용량 필드 image_bytes에 대한 오탐이었다. 호출/정의/import만 검사하도록 수정했으며, 프로그램 데이터 및 캐시 필드는 보존했다. 재검증 실행: https://github.com/sanato-nb/PlayDock/actions/runs/45341397614
