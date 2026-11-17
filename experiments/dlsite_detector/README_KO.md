# PlayDock · DLsite→인터넷 검색 및 변경 이력 독립 실험

> **PlayDock 본체에 아직 이식하지 않은 독립 기능**입니다. `src/playdock/`의 UI·DB·이미지 저장 동작은 변경하지 않았습니다. 개인 게임 목록을 자동 스캔하지 않습니다.

## 1. 검색 판정 규칙

| 단계 | 결과 | 처리 |
|---|---|---|
| DLsite 1차 | ✅ `confirmed_game` | 게임 작품번호·종류 확인 → **즉시 통과** |
| DLsite 1차 | 🔵 `registered_non_game` | **비게임으로 추정** → 별도 목록 보관, 수동 변경 허용 |
| DLsite 1차 | 🟡 `registered_type_unknown` | 일반 인터넷 검색으로 진행 |
| DLsite 1차 | 🟠 `needs_review` | 일반 인터넷 검색으로 진행 |
| DLsite 1차 | ⚪ `unverified` | 일반 인터넷 검색으로 진행 |
| DLsite 통신 오류 | `lookup_unavailable` | 일반 인터넷 검색으로 진행 |
| 일반 인터넷 2차 | `internet_candidate` | 독립 사이트 2곳 이상에 같은 이름의 게임 검색 결과가 있을 때 **확정하지 않고 검토 후보로 보관** |
| 일반 인터넷 2차 | 🔴 `lookup_unavailable` | 여전히 정체를 못 찾으면 **조회 불가 목록에 별도 보관** |
| 입력 오류 | `input_error` | 검색 없이 수정 요청 |

이름만 같은 다른 게임을 선택하지 않기 위해 **연관성 높은 게임 사이트의 검색 결과가 하나라도 있어야 하며**, 검색 결과가 두 개라도 동일한 사이트는 독립 근거로 세지 않습니다. 일반 검색의 자동 판별은 어디까지나 검색 결과 수준의 **추정**이므로 실제 페이지·게임 상세 내용을 검증하는 다음 단계가 필요합니다. 조회 실패는 'DLsite에 없는 게임'이라는 뜻이 아닙니다.

DLsite `work_type` 분류는 비공식 JSON 필드에 기반합니다. 사이트에서 형식을 변경할 수 있으므로 비게임 판단을 확정으로 표기하지 않습니다.

## 2. 저장·수정 원칙

1. **원본 이름 보존:** `ReviewStore.add_game(id, name, archive_filename, archive_size)`이 최초 입력의 표시 이름·압축파일 이름·크기를 불변 스냅샷으로 남깁니다.
2. **이름 수정 전후 기록:** `stage_name_change`로 `before_name`, `after_name`, `pending`을 DB에 저장하고, `apply_name_change`로 **DB 표시값에만 적용**합니다. 원본 복구는 `restore_original_name`으로 새 이력을 남깁니다.
3. **압축파일은 절대 자동 변경하지 않음:** `archive_label`은 압축파일에 표시할 **논리적 이름**일 뿐, 실제 ZIP/7z/RAR의 파일명·내용·경로는 변경하지 않습니다. 실제 파일명 변경은 별도 백업·동일성 검사를 포함한 기능으로 추후 설계해야 합니다.
4. **수동 판정 우선:** `manual_classify`로 사용자가 분류를 바꿀 수 있습니다. 재검색 결과는 별도 자동 판정 이력에 남고 수동 선택은 덮어쓰지 않습니다.
5. **배너/아이콘 DB 선기록:** `ArtworkStaging.stage_image`가 바꾸기 전 PNG와 새 PNG를 **실험용 SQLite DB에 BLOB으로 먼저 기록**합니다. 이후 사용자가 `apply_image`를 명시적으로 호출해야 캐시 PNG가 변경됩니다. 충돌이 나면 중단하고, `restore_image`로 DB에 기록된 이전 이미지로 복구합니다.
6. 모든 실험 데이터는 별도 `*.db`에 저장합니다. **기존 PlayDock `playdock.db`에 바로 쓰지 않습니다.**

검색 이력(`search_runs`)에는 자동 판정, DLsite 코드, 확인한 웹페이지 후보와 사유를 기록합니다. 분류 이력, 표시 이름 변경 이력, 이미지 변경 이력은 별도 테이블로 보관합니다.

## 3. 분리된 소스

```text
experiments/                               # 본체 이식 전 독립 실험 코드 폴더
└── dlsite_detector/                       # DLsite 및 일반 웹 검색 판별 실험
    ├── detector.py                        # DLsite 등록/게임 여부 1차 판별
    ├── pipeline.py                        # 일반 인터넷 2차 검색 및 분류
    ├── review_store.py                    # SQLite 원본 이름·분류·변경 이력
    ├── artwork_staging.py                 # 배너·아이콘 DB 먼저 기록 후 파일 적용·복구
    ├── pipeline_cli.py                    # 별도 검색/수동 변경/복구 명령행 도구
    ├── cli.py                             # 기존 DLsite 단일 판별기
    └── README_KO.md                       # 현재 실험 절차 안내

tests/                                     # 프로젝트 전체 자동 검사
├── test_dlsite_detector_experiment.py     # 1차 DLsite 판별 회귀 검사
└── test_dlsite_search_pipeline_experiment.py # 2차 검색·DB 원본 보존·변경 검증
```

## 4. 본체를 실행하지 않고 독립적으로 사용하기

저장소 루트에서 실행. Windows PowerShell 예시:

```powershell
# 라이브러리와 무관한 실험용 DB 파일을 별도로 준비
$DB = ".\experiment_search.db"

# 1건 검색만 허용 (--online 지정 시에만 인터넷 사용)
python -m experiments.dlsite_detector.pipeline_cli --db $DB scan --id game001 --title "게임 제목" --archive "게임 제목.zip" --online

# 인터넷 검색으로도 못 찾은 게임 / 비게임 추정 목록 분리 조회
python -m experiments.dlsite_detector.pipeline_cli --db $DB queue unresolved
python -m experiments.dlsite_detector.pipeline_cli --db $DB queue non-game

# 사용자가 직접 분류 변경 (검색 이후에도 유지)
python -m experiments.dlsite_detector.pipeline_cli --db $DB manual --id game001 --status manual_game --reason "제작사 페이지 직접 확인"

# 이름 변경: 먼저 DB에 전후 값을 기록, 이후 적용
python -m experiments.dlsite_detector.pipeline_cli --db $DB name-stage --id game001 --new "새 표시 이름"
python -m experiments.dlsite_detector.pipeline_cli --db $DB name-apply --change 1

# 언제든 최초 표시 이름으로 복구 (새 변경 이력을 남김)
python -m experiments.dlsite_detector.pipeline_cli --db $DB name-restore --id game001

# 이미지도 DB 기록 → 별도 실제 파일 적용 순서. 경로는 실험용 별도 캐시.
python -m experiments.dlsite_detector.pipeline_cli --db $DB image-stage --id game001 --kind icon --image ".\new-icon.png" --cache-root ".\experiment_cache"
python -m experiments.dlsite_detector.pipeline_cli --db $DB image-apply --change 1 --cache-root ".\experiment_cache"

# 원본 PNG 복구 및 전체 변경 이력
python -m experiments.dlsite_detector.pipeline_cli --db $DB image-restore --change 1 --cache-root ".\experiment_cache"
python -m experiments.dlsite_detector.pipeline_cli --db $DB history --id game001
```

`name-apply` 및 `image-apply`의 요청 번호는 실제 `name-stage`/`image-stage` 출력에 표시된 번호를 사용합니다. 변경 전후 이름은 DB에 저장되지만 실제 압축파일 이름 변경은 하지 않습니다.

**주의:** 이미지 변경 이력 DB에 이전/새 이미지 BLOB이 들어가므로 파일이 커질 수 있습니다. 백업 및 주기적 정리 정책은 본체 이식 전에 정해야 합니다.

## 5. 검증 범위와 향후 통합 조건

```bash
python -m pytest -q tests/test_dlsite_detector_experiment.py tests/test_dlsite_search_pipeline_experiment.py
```

- 네트워크 응답은 모두 모의한 자동 테스트입니다. 실제 DLsite 사이트/일반 웹의 최신 검색 정확도는 아직 검증되지 않았습니다.
- 이미 존재하는 `src/playdock/` 저장·백업·복원 기능은 **변경하지 않았으며**, 새 실험 DB는 기존 `playdock.db`와 아직 연동되지 않았습니다.
- 실제 이미지 파일 반영은 실험용 `--cache-root`에 한정해 수동으로 시험하세요.
- 일반 웹 검색 결과를 원본 출처에서 직접 검증하는 정확도 개선, 추가 변형 제목·현지화 검증, 실제 사이트 차단 및 접속 실패 처리, 이미지 BLOB 크기/백업 정책을 검토한 뒤 별도 PR로 본체에 이식합니다.
- 본체 이식 시 기존 사용자 게임 목록·모음집·파일·기존 캐시를 보존하고, **원본 이름과 변경 이력 마이그레이션을 먼저 수행**해야 합니다.

## 6. 게임 정체 확인용 압축파일 내부 목록 검사 (추가 실험)

**게임 정체 확인이 우선**입니다. DLsite나 일반 웹에서 정체를 확인하지 못했을 때 로컬 게임 압축파일의 파일 목록을 **압축 해제 없이** 읽어 추가 단서를 얻을 수 있습니다.

```powershell
# 압축 해제, 실행, 파일 수정, DB 저장, 인터넷 요청 없이 단서만 출력
python -m experiments.dlsite_detector.archive_cli "D:\\games\\Unknown Game.7z"

# 다른 독립 검색 모듈과 연동할 수 있는 JSON 출력
python -m experiments.dlsite_detector.archive_cli "D:\\games\\Unknown Game.zip" --json
```

**확인하는 정보:** 압축파일 내부의 파일·폴더 이름, 파일 크기, 파일 수, RJ/VJ/BJ/EJ 형식의 작품 코드 후보, `.exe` 이름에서 찾은 제목 후보, Unity·Ren'Py·RPG Maker·Godot·Unreal 같은 엔진 단서.

**확인하지 않는 정보:** 게임 실행파일의 진짜 제품명이나 서명, 내부 텍스트 파일 내용, 압축을 실제로 풀어야만 알 수 있는 데이터. `Game.exe` 또는 `launcher.exe` 같은 일반 이름은 후보에서 제외합니다. 엔진 단서가 있어도 실제 게임의 정체를 확정하지 않습니다.

**안전 원칙:** 원본 ZIP/7z/RAR은 읽기 전용으로 열고 내부 파일 목록 메타데이터만 확인합니다. 내부 파일 압축 해제·실행·내용 읽기·DB 쓰기·웹 전송을 하지 않습니다. 파일 수 제한과 위험한 경로 건너뛰기를 적용합니다. 암호화된 7z/RAR 헤더는 파일 목록을 볼 수 없을 수도 있습니다.

### 검색 흐름에 이식할 때의 위치

1. DLsite 1차 조회 → 확인된 게임은 즉시 통과, 비게임 추정은 별도 분류.
2. 애매하거나 미확인인 경우 일반 인터넷 2차 조회.
3. **정체가 여전히 불명확한 경우에만** 압축파일 목록을 읽어 EXE 제목·작품 코드·폴더명 등을 단서로 추출.
4. 단서가 충분하면 그 단서로 외부 정보의 동일 작품 여부를 다시 교차 확인. 파일 목록 자체만으로는 자동 확정하지 않음.
5. 최종적으로 근거가 부족하면 🔴 조회 불가 목록에 남기고 수동 분류·수정 허용.

현재 코드는 **3번의 독립 조사기만 구현**한 상태입니다. 전체 검색 파이프라인에 자동 연결하거나 사용자 DB에 검색 단서를 쓰는 것은 충분한 실험 후 별도 작업으로 진행합니다.

## 7. 최종 개발 목표: 압축파일 하나로 게임 정체 확인

**독립 실행 프로그램 `identify_cli.py`가 구현되었습니다.** 기존 `src/playdock/`는 수정하지 않고 별도 실험 브랜치에서 개발합니다.

### 실행 순서

1. **1단계 · 압축파일 이름으로 검색:** 파일명에서 확장자를 제외한 문자열로 DLsite → 일반 인터넷 검색을 수행합니다.
2. **게임 확인 시 즉시 종료:** 더 이상 내부 파일을 읽지 않습니다. DLsite 비게임 작품은 비게임 **추정**으로 별도 분류합니다.
3. **1단계 실패 시 2단계:** ZIP/7z/RAR을 풀지 않고 내부 파일 목록을 확인해 EXE 이름·최상위 폴더·작품 코드 후보를 추출합니다.
4. **2단계 재검색:** 단서에서 얻은 서로 다른 제목 후보 최대 4개와 작품 코드 최대 2개로 DLsite·일반 인터넷 검색을 다시 시도합니다.
5. **정체 후보 발견:** 실제 게임 작품은 확인되더라도 **압축파일과 같은 게임이라는 검증은 남았으므로 수동 확인 필요**로 표시합니다. 여러 게임이 나오면 복수 후보를 보여주고 자동 선택하지 않습니다.
6. **모든 검색 실패:** 🔴 조회 불가로 표시합니다. 원본 파일을 수정하지 않습니다.

```powershell
# 기본: 인터넷 검색 없이 압축파일 내부 파일 목록의 단서만 확인
python -m experiments.dlsite_detector.identify_cli "D:\\games\\Unknown Game.zip"

# 1차 파일명 → 실패하면 2차 내부 목록 + 재검색 (실제 웹 접속)
python -m experiments.dlsite_detector.identify_cli "D:\\games\\Unknown Game.zip" --online

# 전 단계 판정/근거를 구조화된 JSON으로 출력
python -m experiments.dlsite_detector.identify_cli "D:\\games\\Unknown Game.zip" --online --json
```

실행 과정에서 **파일명 전체 경로는 웹에 전송하지 않으며**, 2단계 검색 시에는 내부 경로 대신 추출된 짧은 제목/품번 후보만 검색어로 사용합니다. 검색기는 압축파일을 풀거나 안의 실행파일을 실행하지 않습니다.

`identify_archive(path)` 함수는 매 단계 결과와 내부 목록 근거를 구조화된 결과로 반환합니다. 직접 DB를 수정하거나 PlayDock 본체 설정을 건드리지 않으므로, 검색기 검증 후 별도 Service를 통해 이식할 수 있습니다.

### 아직 남은 검증

실제 DLsite·일반 사이트 검색 정확도, 다국어·동일 제목 게임, 합본/패치/불필요한 내부 폴더의 오탐, 암호화된 파일 목록, Windows 실사용을 확인해야 합니다. **현재는 모의 검색/임시 압축파일 기반 자동 테스트만 통과한 단계입니다.**

## 8. 우선 개발: 인터넷 검색 정확도 개선

압축 안의 README나 EXE 메타데이터를 읽기 전에 **기존 파일명 검색 성공률부터 높이는 개선**입니다.

- `search_terms.py`: `PASEC_v2.2566.zip` → 검색어 `PASEC`처럼 파일명 뒤의 명시적 버전, 한국어 번역·패치 태그, 작품 코드를 검색어에서 제외합니다. `Game 2`와 `Game 3`을 구분하며 **원본 파일과 DB 이름은 변경하지 않습니다**.
- `detector.py`: DLsite 이름 검색에서 정리한 제목을 먼저 조회하고, 필요한 경우 원래 파일명으로 제한적으로 재검색합니다. DLsite 작품 코드와 공식 작품명·유형의 검증은 그대로 유지합니다.
- `pipeline.py`: 일반 웹 검색 시 한국어는 `게임`, 일본어는 `ゲーム`, 그 외는 `game` 키워드를 이용하고 정확한 제목 검색으로 재시도합니다. 결과 URL은 중복 제거합니다.
- 출처 2곳 이상에서 비슷한 결과를 찾더라도 **검색 결과 제목·요약만으로 작품을 확정하지 않습니다.** `internet_candidate`(원본 작품 페이지 확인 필요)로 남기며, 이름 변경이나 DB 작품 연결을 자동 실행하지 않습니다.
- `archive_identity.py`: 1단계에서 인터넷 검색 후보를 찾으면 '후보 확인 필요'로 끝냅니다. 실패한 경우에만 내부 목록 분석으로 내려갑니다. 2단계 후보 역시 사용자가 검토하도록 남깁니다.

```bash
python -m pytest -q tests/test_search_quality_experiment.py
```

검색 결과에 대한 **실제 작품 페이지 확인과 게임 제작사/발매일 교차검증, 다국어 별칭·오역 대응**은 후속 정확도 개선 과제입니다. 지금은 검색 엔진 자체의 성능과 오탐 방지에 집중하고 있으며, PlayDock 본체와는 여전히 분리되어 있습니다.
