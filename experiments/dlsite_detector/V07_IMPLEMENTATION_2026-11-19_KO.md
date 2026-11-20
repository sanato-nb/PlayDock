# PlayDock 게임 정체 판독기 v0.7 — 내부 파일명 중심 개발 기록 (2026-11-19)

## 개발 목적 및 기본 정책

- **사용자가 의도한 내부 분석:** 압축파일 내부 파일·폴더의 **이름/상대 경로/확장자/크기/엔진 특유의 배치 구조**를 근거로 게임을 유추한다. EXE·JSON·INI·엔진 설정파일의 **내용**은 기본 판독에서 읽지 않는다.
- **README 예외:** `README`, `README.txt`, `README.md` 및 제한된 언어별 README 최대 2개만 열어, 명시적인 게임명/품번/Steam ID 같은 라벨 필드를 추출한다. README 전체 원문·비밀번호·기타 문장은 검색에 전송하지 않는다.
- **암호화 또는 암호 여부 불명:** 내부 목록/README를 읽지 않고 압축파일명으로만 검색한다.
- **수집 → 검색 순서:** 압축파일 이름 + 내부 파일명·폴더 구조 + (해당하면) 제한된 README 정보를 **전부 수집한 후**, 검색어를 통합·정렬하고 인터넷 검색 및 최종 검증한다.
- **검색 누락 방지:** 빠른 모드 3개, 상세 모드 6개라는 검색어 상한을 유지하되, 정상적인 **압축파일명 제목**은 내부 품번/제목 후보에 밀려 빠지지 않는다. 작품번호의 공식 조회가 성공해도 압축파일명 제목 검색을 생략하지 않는다.
- **최종 판정:** 엔진·EXE/게임 데이터·번역 관련 구조는 게임 정체의 **보조 근거**다. 실제 원본과 동일하다고 자동 확정하거나 PlayDock DB를 고치지 않는다.

## 구현 및 호환성

- `internal_metadata.py`: `inspect_readme_metadata()` 추가, 레거시 심층 `inspect_metadata()`와 분리. README 최대 2개, 기존 파일당 최대 32KiB / 누적 최대 128KiB 등 제한 유지. ZIP/7z/RAR 원본 변경/실행/전체 추출 없음.
- `archive_identity.py`: 기본 `allow_metadata=True` 호출의 내용 읽기를 README 전용으로 설정. 이전 검색 재검사에서도 README 전용 파서를 사용. 과거 심층 연구 코드는 `metadata_reader=inspect_metadata`로 **명시적** 요청할 때만 사용.
- `search_plan.py`: 검색 계획의 압축파일명 제목 슬롯 보존. 내부 명칭 및 공식 ID는 검색어 후보로 계속 참여.
- `scripts/game_identity_tester.py`: `0.7-test` 라벨, GUI 오프라인 검사 및 Windows 자체 테스트를 README 기본 정책에 맞춤.
- `identify_cli.py`: 기본 온라인 및 `--metadata` 오프라인도 README 전용으로 동작. `--no-metadata`는 README도 읽지 않음.
- `tests/test_v07_filename_structure_readme_experiment.py`: 합성 ZIP으로 JSON/INI/`app.info` 내용 접근 금지, README 라벨 필드, 암호 보호 규칙 보존, 파일 해시 불변, 파일명 검색 보장, 자체 테스트 검증.

## 검증과 남은 과제

- GitHub Actions `python-tests.yml`로 전체 `pytest` 검증.
- 기본 모드에서 기존 메타데이터 기반의 `matched` 판정이 줄 수 있는 것은 **의도적 보수성**이다. 이는 정확도 향상이 측정되었다는 의미가 아니다.
- **실제 129개 압축파일 재검사는 하지 않았다.** v0.5 실측 수치 318.092초/129개 및 공식 후보 79개는 과거 기준으로 유지. v0.7의 발견률·정확도·속도 개선은 사용자 비공개 데이터로 별도 측정해야 한다.
- Windows EXE 빌드와 실제 GUI 클릭/파일 재검사 검증은 하지 않았다. EXE는 수동 빌드만 허용.
- 작업 브랜치 `experiment-dlsite-game-detector-20261117`, Draft PR #2 유지. `main` 병합 금지. 실제 개인 파일명·API 키·검사 JSON 공개 업로드 금지.
