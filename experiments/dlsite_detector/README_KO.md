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
| 일반 인터넷 2차 | `internet_confirmed_game` | 동일 작품명 + 게임 근거가 있는 **독립 사이트 2곳 이상** 확인할 때만 게임으로 분류 |
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
