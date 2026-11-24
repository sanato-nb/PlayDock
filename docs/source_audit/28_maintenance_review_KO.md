# 7-D 유지보수 구조 및 자동 검증 정리

기준 ce6eed03a37e7eb620eb0e41fb043aa1c9cdbcf8 (Work 새로고침 최적화). 해당 커밋 Windows 1276 passed / 1 skipped, UI 38 SHA 및 14 PNG 일치, 정식 EXE 빌드 성공(45366469355, 45366469020). 7-C 45365167121 정적+Windows 성공: 폐기 참조 0, 본체 실험 의존 0, 미도달 본체 모듈 0, 본체 내부 동일 함수 그룹 0. 전체 동일 본문 후보 65개는 독립 엔진/실험·테스트 중복 포함이며 실제 본체 내부 중복과 구분.

## import 후보 검토

7-C artifact 14905124703의 final_residual.json 직접 분류: 총 289 (src 211 + 진입점 78). UI 보호 파일 210건, core/work_db 공개 재노출 40건, settings_service 4건, cache_management 8건, data_management 21건, artwork의 get_secret/set_secret 2건. 나머지 4건: detector.unicodedata, no_api_html.CATEGORIES, install_service.ArchivePasswordInvalid, library_service.safe_folder_name. 75건은 호환/설정 관련 후보이며 개별 실제 사용 여부의 확정은 아님. UI 보호 210건은 자동 삭제 금지. 나머지 4건도 테스트/외부 호출과 실험 동등성 검토 전 보존. 이 단계에서는 소스 기능 변경 없음.

## CI 중복 정리

최신 Work 커밋으로 자동 실행된 5개 워크플로 중 4개가 전체 pytest를 반복하고 2개가 정식 EXE 빌드를 반복했다. 자동 실행을 일반 Windows 회귀+빌드+실행 검증 1개로 통합한다. 이전 6개 집중 워크플로는 수동 실행만 유지하며 테스트 파일, 기록 및 기존 실행 이력 삭제 없음. UI 검증, 별도 성능 및 데이터 호환, 독립 실험과 공개 배포는 유지한다. 새 통합 검증은 full suite 결과 JUnit을 기능군에 분류하고 기존 정식 빌드와 실제 EXE 내부/실행 검사 수행. 과거 실행이 성공했다고 새 통합 CI 성공을 가정하지 않는다.

최신 파일 지도: ../PlayDock_Architecture_KO.md. 원본 UI 38개 파일 및 실험 66개 무변경. main 통합 없음. 다음 7-E에서 통합 CI 및 최종 배포 검증을 확인하고 남은 실사용 화면/실행 시간 검증 한계 기록. 실제 사용자 Windows 검수와 별도 배포 승인 전 완료 확정 금지.
