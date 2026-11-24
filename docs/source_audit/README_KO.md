# PlayDock 소스코드 정리 — 1단계 감사 시작

## 기준
- 기준 커밋: `af10566aeb5a066ac5ee9beb9565823b73895002`
- 원본 트리: `b5868ab60bf859a9bd807fd6f8ee5f917c18bc8f`
- [Windows 검증](https://github.com/sanato-nb/PlayDock/actions/runs/45334982495): 1101 passed, 1 skipped. EXE 73.1 MB. 시각 검수는 별도.
- 추적 Python 261개 (src 84개). 테스트·실험·스크립트도 삭제 후보 분석 대상이지만 독립 실행 기능은 보존.
- 본체와 기존 사용자 데이터의 변경은 하지 않는다.

## 직접 확인한 우선 검토 대상
| 위치 | 근거 | 분류 |
|---|---|---|
| app.py | MainWindow가 5개 Controller mixin과 QMainWindow를 조합, 기존 core/artwork 등의 import 존재 | 유지 / 미사용 import 후보 확인 |
| controllers/metadata.py | experiments.dlsite_detector.code_only.Work 직접 import, 이름/작품정보/이미지 기능 혼재 | 분리 검토 |
| services/catalog_collection_service.py | experiments.dlsite_detector.code_only 직접 import | 공식 조회 엔진의 정식 계층 이전 후보 |
| core.py, work_db.py | 기존 호출 유지용 재수출 | 유지 / 호환 제거는 후속 조사 |
| artwork.py | save_image/discover_local와 기존 AI 함수가 한 파일에 존재 | 필수 이미지 기능 유지 / AI 별도 조사 |
| ui/dialogs/common.py | 공통 입력 창, 파일 선택 창, Windows 캡션 처리 혼재 | 파일 선택 창 분리 후보 (기능 동일 유지) |
| ui/dialogs/library.py | 초기 설정·모음집·캐시·데이터 관리·라이브러리 정보·이전 AI 설정 창 | 책임 분리 검토 |
| ui/dialogs/title.py | 이름 설정 UI와 미리보기·저장 처리 | UI-서비스 경계 검토 |
| services/*worker*.py | 기능 서비스와 Qt 작업 스레드 혼재 | workers 이동 후보 |

## 재현 방법
`python scripts/audit_source.py --ref af10566aeb5a066ac5ee9beb9565823b73895002 --out audit_output`

Git 객체에서 원본 SHA를 확인하고 모든 추적 Python 파일을 AST로 분석한다. 결과는 Actions의 PlayDock-Source-Audit에 저장된다. 정적 import 그래프, 파일별 줄 수, 역참조, 사용하지 않을 가능성이 있는 import, 동일 함수 본문 후보, 실험 의존 경계를 기록한다. 정적 미도달은 미사용 확정이 아니며 Qt 연결, 외부 호출, 빌드 스크립트, 동적 import, 재수출을 함께 검증해야 한다. 자동 삭제는 하지 않는다.

## 단계
1. 소스 인벤토리와 정적 의존관계 (도구 작성 및 실행)
2. 실제 메뉴/작업 진입점 호출, 테스트 및 빌드 참조와 후보 교차 검증
3. 파일 및 함수별 유지 / 이동 / 통합 / 삭제 후보 / 최적화 분류 확정
4. 합성 데이터로 실행시간 및 메모리 기준 측정
5. 감사 결과 검토 후 코드 변경 시작

사용자 데이터 및 원본 압축파일은 접근하거나 수정하지 않는다.
