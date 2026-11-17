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
    ├── search_terms.py                    # 파일명에서 검색용 제목 추출
    ├── identity_hints.py                  # DLsite/Steam 코드와 배포 유형 단서 분리
    ├── steam_client.py                    # Steam 앱 원본 상품 데이터 검증
    ├── enhanced_search.py                # 원본 교차검증·별칭 재검색
    ├── archive_inspector.py              # ZIP/7z/RAR 내부 목록·실행파일·엔진 단서
    ├── internal_metadata.py              # 작은 README/INI/JSON 내부 제목 선택적 읽기
    ├── archive_identity.py               # 이름→내부 목록→선택적 메타 3단계 순서 제어
    ├── identify_cli.py                   # 단일 압축파일 실험 명령행 실행기
    ├── filename_batch.py                 # PowerShell 파일 목록 대량 실험 도구
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

**오프라인 기본 모드의 안전 원칙:** 원본 ZIP/7z/RAR은 읽기 전용으로 열고 내부 파일 목록 메타데이터만 확인합니다. 오프라인 기본 모드에서는 내부 파일 압축 해제·실행·내용 읽기·DB 쓰기·웹 전송을 하지 않습니다. 오프라인 `--metadata` 또는 온라인 기본 실행에서는 정해진 작은 텍스트 파일만 선택적으로 메모리에서 압축 해제해 게임명 필드를 읽습니다. 파일 수 제한과 위험한 경로 건너뛰기를 적용합니다. 암호화된 7z/RAR 헤더는 파일 목록을 볼 수 없을 수도 있습니다.

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
2. **2단계 · 이름 기반 외부 작품 검색:** DLsite·Steam 및 일반 웹에서 작품 후보를 확인합니다. 이름으로 찾았더라도 압축파일 정체는 아직 미확정입니다.
3. **3단계 · 암호화 여부 확인:** 암호화된 ZIP/7z/RAR은 이름 기반 결과만 유지하고, 실패하면 '분류 불가'로 중단합니다.
4. **4단계 · 비암호화 압축파일 전체 목록 분석:** 파일명 검색에 성공해도 EXE·최상위 폴더·게임 데이터·번역 폴더·작품 코드를 모두 검사합니다. 안전 제한(최대 120,000항목)을 넘으면 '전체 검사 미완료'로 보고합니다. 필요 시 목록에서 얻은 제목 최대 4개·품번 최대 2개로 재검색합니다.
5. **5단계 · 작은 메타데이터 읽기:** 온라인 실행에서는 기본적으로 작은 README·INI·JSON 등을 선택적으로 읽습니다(파일당 32KiB, 총 128KiB). 파일명 검색 성공 시에도 내부 작품 이름을 수집합니다. 다른 제목이 나타나면 자동 확정하지 않고 검토가 필요하다고 표시합니다.
6. **5단계까지는 근거 수집:** 찾은 작품은 압축파일 동일성 '후보'로 남겨 6단계 최종 교차검증을 나중에 진행합니다. 암호화 파일만 이름 기반 검색 결과를 별도로 기록합니다. 원본 파일·DB는 수정하지 않습니다.

```powershell
# 기본: 인터넷 검색 없이 압축파일 내부 파일 목록의 단서만 확인
python -m experiments.dlsite_detector.identify_cli "D:\\games\\Unknown Game.zip"

# 온라인 이름 검색 → 암호 확인 → 비암호화 목록 전체 → 작은 메타데이터 분석
python -m experiments.dlsite_detector.identify_cli "D:\\games\\Unknown Game.zip" --online

# 후보 출처 단계(stage)와 실제 수행한 1~5단계(completed_steps)를 JSON으로 출력
python -m experiments.dlsite_detector.identify_cli "D:\\games\\Unknown Game.zip" --online --json
```

실행 과정에서 **파일명 전체 경로는 웹에 전송하지 않으며**, 내부 목록이나 메타데이터로 재검색할 때도 추출된 짧은 제목/품번만 검색어로 사용합니다. 검색기는 압축파일을 풀거나 안의 실행파일을 실행하지 않습니다.

`identify_archive(path)` 함수는 매 단계 결과와 내부 목록 근거를 구조화된 결과로 반환합니다. 직접 DB를 수정하거나 PlayDock 본체 설정을 건드리지 않으므로, 검색기 검증 후 별도 Service를 통해 이식할 수 있습니다.

### 아직 남은 검증

실제 DLsite·일반 사이트 검색 정확도, 다국어·동일 제목 게임, 합본/패치/불필요한 내부 폴더의 오탐, 암호화된 파일 목록, Windows 실사용을 확인해야 합니다. **현재는 모의 검색/임시 압축파일 기반 자동 테스트만 통과한 단계입니다.**

## 8. 우선 개발: 인터넷 검색 정확도 개선

압축 안의 README나 EXE 메타데이터를 읽기 전에 **기존 파일명 검색 성공률부터 높이는 개선**입니다.

- `search_terms.py`: `PASEC_v2.2566.zip` → 검색어 `PASEC`처럼 파일명 뒤의 명시적 버전, 한국어 번역·패치 태그, 작품 코드를 검색어에서 제외합니다. `Game 2`와 `Game 3`을 구분하며 **원본 파일과 DB 이름은 변경하지 않습니다**.
- `detector.py`: DLsite 이름 검색에서 정리한 제목을 먼저 조회하고, 필요한 경우 원래 파일명으로 제한적으로 재검색합니다. DLsite 작품 코드와 공식 작품명·유형의 검증은 그대로 유지합니다.
- `pipeline.py`: 일반 웹 검색 시 한국어는 `게임`, 일본어는 `ゲーム`, 그 외는 `game` 키워드를 이용하고 정확한 제목 검색으로 재시도합니다. 결과 URL은 중복 제거합니다.
- 출처 2곳 이상에서 비슷한 결과를 찾더라도 **검색 결과 제목·요약만으로 작품을 확정하지 않습니다.** `internet_candidate`(원본 작품 페이지 확인 필요)로 남기며, 이름 변경이나 DB 작품 연결을 자동 실행하지 않습니다.
- `archive_identity.py`: 이름 검색으로 후보를 찾더라도 **비암호화 파일은 4단계 전체 목록, 5단계 소형 메타데이터까지 확인**합니다. 암호화된 파일만 이름 검색 후 종료합니다. 내부 정보는 자동 게임 확정이 아니라 후속 검토용 근거로 저장합니다.

```bash
python -m pytest -q tests/test_search_quality_experiment.py
```

검색 결과에 대한 **실제 작품 페이지 확인과 게임 제작사/발매일 교차검증, 다국어 별칭·오역 대응**은 후속 정확도 개선 과제입니다. 지금은 검색 엔진 자체의 성능과 오탐 방지에 집중하고 있으며, PlayDock 본체와는 여전히 분리되어 있습니다.

## 9. 파일명 검색 기능 2차 보강 (Steam·DLsite 식별자 및 원본 검증)

이 개선은 **AI를 사용하지 않습니다.** PlayDock 본체 `src/playdock/`에는 연결하지 않았으며, 압축파일 원본·이름·DB 사용자 설정도 자동 수정하지 않습니다.

### 식별 근거의 우선순위

1. **Steam App ID가 파일명에 명시됨:** `[Steam 1621540]` 표기를 찾으면 공개 Steam Store `appdetails` 원본 JSON을 조회합니다. 요청한 숫자 ID, 응답의 App ID, 상품명, `type=game`인지 확인합니다. 정식 이름이 같으면 `platform_confirmed_game`으로 기록합니다. 서버팩·패치·DLC·합본 표기는 원본 게임으로 자동 단정하지 않습니다.
2. **DLsite 품번:** RJ/VJ/BJ/EJ 작품 ID와 작품 종류를 기존 DLsite 검색기에서 검증합니다. DLsite와 Steam ID가 둘 다 있을 때는 두 출처가 다른 작품 또는 다른 유형을 가리키는지 확인하고, 불일치하면 후보 검토로 돌립니다.
3. **일반 인터넷 검색:** 기존의 검색어 정리와 한국어·일본어·영어별 검색식 사용. 검색 결과에 실제 Steam 상품 링크가 있으면 해당 App ID를 공개 Store JSON으로 **다시 확인**합니다. 검색 결과 제목만 믿지 않습니다.
4. **명시적인 작품 별칭:** `거인의 비보 (Giant Treasure)`처럼 원본 파일명에 직접 병기된 괄호 속 작품명만 추가 검색합니다. `[번역 수정]`처럼 배포 주석으로 보이는 대괄호 정보는 작품명 별칭으로 사용하지 않습니다. 자동 번역·AI 추측은 수행하지 않습니다.
5. **최종 분류:** 게임 출처를 확인하지 못하면 조회 불가, 검색 결과만 일치하면 후보 확인 필요로 남깁니다. 파일 종류(본편 추정, 한국어 적용 상태 미확인, 별도 패치 명시, DLC 추정, 서버 패키지 추정, 합본 추정)는 게임의 **작품 정체와 별도**로 기록합니다.

### 실제 예시

| 파일명 | 분리해 얻는 정보 |
|---|---|
| `Spooky Milk Life [Steam 1621540].7z` | 제목 `Spooky Milk Life`, Steam App ID `1621540` |
| `Eliminator 카에데씨 [RJ209760·Steam 1122040].7z` | DLsite 작품 ID + Steam App ID 개별 검증 대상 |
| `Craft to Exile 2 [Server v1.1.3].zip` | 제목 `Craft to Exile 2`, 서버용 자료 **추정**, Minecraft 모드팩인지 자동 단정하지 않음 |
| `SummertimeSaga [한국어 패치 Fix2].zip` | 작품명 `SummertimeSaga`, **한국어 적용본일 수 있음·구성 미확인** |
| `Fate Empire of Dirt + Made in Heaven.7z` | 여러 작품이 포함됐을 가능성, 합본 **추정** |

### 실행/시험

```powershell
# 실제 ZIP/7z/RAR 파일 경로 하나를 선택해 실행합니다.
python -m experiments.dlsite_detector.identify_cli "D:\\Games\\Spooky Milk Life [Steam 1621540].7z" --online --json

# 기존 독립 검증용 DB에서는 원본 파일명과 검색·수동 판정 이력을 보존합니다.
python -m experiments.dlsite_detector.pipeline_cli --db ".\\identity-experiment.db" scan --id game01 --title "Spooky Milk Life [Steam 1621540]" --archive "Spooky Milk Life [Steam 1621540].7z" --online

# 파일명 검색·원본 ID 검증·패치/서버팩 오분류 방지 테스트
python -m pytest -q tests/test_platform_identity_enrichment_experiment.py
```

**제약사항:** Steam Store `appdetails`은 비공식 공개 엔드포인트이며 일시적 차단이나 응답 오류가 발생할 수 있습니다. 이때 오류는 비등록의 증거가 아니며 일반 검색으로 넘어갑니다. itch.io·GOG 등은 **아직 원본 페이지 내용을 직접 검증하는 어댑터가 없습니다.** 일부 원본이 제한되거나 Steam 페이지가 삭제됐을 수 있으므로 검색 결과를 곧바로 확정하지 않습니다. 130개 파일명 목록은 실험의 테스트 사례를 뽑는 근거로만 사용했으며, 사용자의 로컬 파일명 전체를 공개 저장소의 테스트 데이터로 올리지 않았습니다.

추후 실제 인터넷 접속을 허용한 실험에서 **자동 검색 확인 비율·후보 비율·조회 불가 비율·오분류 비율**을 별도로 측정해야 합니다.

## 10. PowerShell 파일 목록 129개 배치 재검사

Windows PowerShell `ls` 출력(긴 파일명이 자동 줄바꿈된 경우 포함)을 읽어 **압축파일을 열지 않고 파일명만 전수 검사**하는 CLI를 제공합니다.

```powershell
# 파일명만 오프라인 검사. 기본 설정에서는 인터넷 사용 안 함.
python -m experiments.dlsite_detector.filename_batch ".\\powershell-list.txt" `
  --exclude "Craft to Exile 2 [Server v1.1.3].zip" `
  --csv ".\\offline-name-results.csv" `
  --json-output ".\\offline-name-results.json"

# 실제 게임 정체 온라인 조회 (명시적인 --online 필요)
# 처음에는 5건으로 제한해 서버 접속과 판정을 확인하세요.
python -m experiments.dlsite_detector.filename_batch ".\\powershell-list.txt" `
  --exclude "Craft to Exile 2 [Server v1.1.3].zip" `
  --online --max-online 5 --delay 2 `
  --json-output ".\\online-smoke-results.json"
```

- 오프라인 보고서의 `title_search`/`title_and_id_lookup`/`direct_id_lookup`는 **어떤 검색 경로로 보내야 하는지의 규칙 분석 결과**이며 실제 온라인 게임 확인 성공률이 아닙니다.
- 온라인 결과에는 `online_status`, `online_proposed_title`, 외부 플랫폼·작품 코드·사유를 분리해 기록합니다.
- 자동 검색 중 이미지·압축파일 원본·PlayDock 본체 DB를 변경하지 않습니다. 원본 압축파일 목록을 공개 저장소에 커밋하지 않습니다.
- 파일명 정리 시 배포·번역·패치·버전 태그를 제거하되 알려지지 않은 대괄호는 부제일 수 있으므로 보존합니다.
- **오프라인 전수 테스트**는 사용자가 공유한 목록에서 제외 파일을 제거한 129개를 대상으로 검증했습니다. **129건의 실제 온라인 검색 성공률**은 아직 측정하지 않았습니다.

## 11. 내부 압축파일 근거 검사 (선택적, AI 미사용)

**중요한 정정:** `[한글패치]`라는 파일명 표기만으로 별도 패치 ZIP이라고 분류하면 안 됩니다.
이 표기는 한국어 적용본 게임일 수도 있으므로 `localized_release_unknown`으로 기록합니다.
`[패치 전용]`처럼 *단독 파일*이라고 명시된 경우만 `patch_candidate`로 분류합니다.
기존 게임 정체 판정과 파일 구성 판정은 반드시 별도로 표시합니다.

**온라인 실행은 기본으로 1~5단계까지 수행합니다.** 이름 기반 작품 검색이 성공하더라도 비암호화 ZIP·7z·RAR의 전체 내부 목록을 확인합니다. 작은 메타데이터 파일은 정해진 종류만 선택적으로 읽으며, 내용 읽기를 끄려면 `--no-metadata`를 지정합니다. 오프라인에서는 기존처럼 `--metadata`를 지정해야 내용 분석을 수행합니다.
검색 결과가 게임 후보 또는 공식 등록 작품이어도 로컬 압축파일과 동일하다고 확정하지 않습니다. 내부 제목과 충돌하면 `ambiguous`로 보류합니다.

### 읽을 수 있는 근거

- 내부 파일 목록: 비범용 게임 실행파일 `.exe`, Ren'Py의 `.rpa`, RPG Maker 데이터, `tl/korean/` 등 번역 폴더 경로의 **존재 여부만** 수집 (기존 목록 분석 기능)
- 작은 파일 내용: `README.txt/md`, `Game.ini`, `RPG_RT.ini`, `project.godot`, `game.json`, `metadata.json`, `package.json`, `version.json`, `options.rpy`, `app.info`에서 *명시된 게임명 필드만* 추출
- 설정파일과 README 전체 문장, 사용자 파일 경로·비밀번호·API 키 등은 외부 검색어 또는 결과로 저장하지 않음
- 파일당 최대 32KiB, 총 128KiB, 최대 8개, 비정상 경로/심볼릭 링크/암호화/고압축 항목 제외
- ZIP은 해당 항목을 메모리에서 읽고, RAR은 비-solid/비암호화 항목만 읽기 가능할 때 분석합니다.
- **7z는 py7zr 1.1.4 이상에서 비-solid + 해제 크기 상한을 적용할 수 있는 경우에만 선택적 메모리 읽기.** 솔리드/암호화/검사 불가 파일은 안전을 위해 목록 단서만 사용합니다.
- EXE 파일의 *제품 버전 리소스 본문*을 직접 해제하거나 실행하는 기능은 아직 구현하지 않았습니다. EXE 존재/파일명은 목록 단서로만 사용합니다.

### 실행

```powershell
# 1: 완전 오프라인. ZIP/7z/RAR의 메타데이터 필드만 검사. 인터넷 요청 없음
python -m experiments.dlsite_detector.identify_cli "D:\\Games\\NOR [한글패치].zip" --metadata --json

# 2: 온라인 검색 결과와 관계없이 비암호화 내부 목록·작은 메타데이터까지 조사
python -m experiments.dlsite_detector.identify_cli "D:\\Games\\NOR [한글패치].zip" --online --metadata --json

# 소형 테스트 압축파일로 기능과 보안 경계를 검증
python -m pytest -q tests/test_internal_metadata_experiment.py
```

**실제 압축파일 확인 필요:** 지금까지 사용자가 제공한 자료는 PowerShell 파일명 목록이며
NOR 아카이브 실제 바이트는 전달받지 않았습니다. 따라서 `NOR [한글패치].zip` 내부에
실제로 `Night of Revenge`라는 제목이나 실행파일이 존재하는지는 아직 확인한 사실이 아닙니다.

## 12. 암호화된 ZIP·7z·RAR 분류 정책

**비밀번호가 걸린 압축파일은 오직 외부 압축파일 이름만 정체 판단에 사용합니다.**
암호화된 ZIP이 파일명 목록을 보여 주더라도 목록의 게임 EXE/폴더명·내부 DLsite 품번은 수집하거나 검색하지 않습니다.
7z·RAR 헤더에서 암호 필요 여부만 안전하게 확인하고, 암호화돼 있으면 목록/메타데이터 검사를 모두 생략합니다.

| 이름 검색 결과 | 암호화된 파일의 최종 결과 |
|---|---|
| DLsite/Steam 원본 조회로 작품 확인 | 파일명 기반 작품 확인 (압축 내용 동일성은 미확인) |
| 일반 웹에서 관련 작품 후보 확인 | 후보 발견·수동 확인 필요 (내부 근거는 사용하지 않음) |
| 검색 실패/확인 근거 부족 | **분류 불가** (`unclassifiable`) |

암호화 여부가 불명확하거나 헤더를 열 수 없는 파일은 안전하게 내부 분석을 생략하고 조회 불가(`lookup_unavailable`)로 보관합니다.
비밀번호 입력·저장·추측·해제 시도 기능은 추가하지 않습니다.
`--metadata`를 명시해도 암호화된 파일은 소형 README/INI/JSON을 열지 않습니다.
비암호화 파일은 기존대로 이름 → 내부 파일 목록 → 선택적 내부 메타데이터 순서를 유지합니다.

```powershell
python -m experiments.dlsite_detector.identify_cli "D:\\Games\\Locked Game.zip" --online --metadata --json
```

암호 ZIP의 일부 항목만 보호된 경우에도 **압축파일 전체를 이름만 검색**합니다.
자동 테스트는 암호 ZIP 플래그, 7z/RAR 암호 헤더, 암호 상태 확인 불가, 비암호화 정상 처리 등으로 검증합니다.

## 13. 1~5단계 전수 목록 검사 (최신 동작)

`identify_archive()`의 `stage` 필드는 **후보가 나온 검색 근거(1=파일명, 2=내부 목록, 3=내부 메타데이터)**를 나타내는 기존 호환 필드입니다.
새 `completed_steps` 필드는 이번에 요청한 **실제 1~5단계 처리 이력**을 나타냅니다.

1. 압축파일 이름에서 게임 검색어·DLsite/Steam 코드·배포 태그 추출
2. DLsite·Steam·일반 인터넷으로 후보 확인
3. 암호화 여부 판정. 암호화 파일은 이 단계에서 종료하고 이름 검색 실패 시 `unclassifiable`
4. **게임 검색 성공 여부와 관계없이** 비암호화 압축파일의 내부 목록 검사. 최대 120,000개 항목을 읽으며 제한을 넘으면 `limit_exceeded`; 보고서 `inspection_complete=false`
5. 작은 README·INI·JSON·설정파일에서 제목·품번을 제한적으로 읽어 추가 검색 근거로 보관. `--online`이면 기본 활성화하며 `--no-metadata`로 해제 가능

**6단계 최종 동일성 비교 및 라이브러리 자동 등록/이름 변경은 아직 구현하지 않았습니다.**
외부에서 원본 작품을 확인했더라도 비암호화 파일의 현재 결과는 `candidate_found`로 남겨 사용자 검토를 기다립니다.
출처의 원래 판정은 `attempts`와 `external_status`에 남습니다.
`encryption_state`, `inspection_complete`, `evidence_conflict`를 결과에 포함합니다.

```powershell
# 1~5단계 자동 조사, 결과만 출력 (원본 수정하지 않음)
python -m experiments.dlsite_detector.identify_cli "D:\\Games\\Unknown Game.zip" --online --json

# 내용을 열지 않고 내부 목록까지만 조사
python -m experiments.dlsite_detector.identify_cli "D:\\Games\\Unknown Game.zip" --online --no-metadata --json

# 인터넷 없이 내부 목록 + 허용된 소형 메타데이터만 조사
python -m experiments.dlsite_detector.identify_cli "D:\\Games\\Unknown Game.zip" --metadata --json

# 자동 회귀 검사
python -m pytest -q tests/test_full_five_stage_archive_experiment.py
```
