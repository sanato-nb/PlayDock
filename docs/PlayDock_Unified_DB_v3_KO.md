# PlayDock 통합 SQLite DB v3

현재 DB 저장 위치는 **설치된 PlayDock 폴더의 `data/playdock.db`** (B안) 한 곳입니다.
PlayDock 본체와 독립 정체 판독기가 동일한 SQLite DB를 사용합니다.

## 테이블은 정확히 2개

### works: 사이트별 공식 작품정보
| 항목 | 의미 |
|---|---|
| store | dlsite, steam |
| code | 공식 품번 또는 App ID |
| title | 기본 공식 작품명 |
| category | 해당 사이트 원본 분류 |
| maker | 개발사·제작사 |
| page_url | 검증된 공식 작품 페이지 |
| checked_at | 최종 확인 시각(UTC) |
| titles_json | 언어별 제목 JSON 객체 |
| tags_json | 태그·장르 JSON 배열 |
| images_json | 공식 이미지 URL·종류·순서의 JSON 배열 |

**고유 키: (store, code)**. 같은 코드라도 사이트가 다르면 다른 작품입니다.
발매일, source_url, source_type과 별도의 중복 제목 필드는 저장하지 않습니다.

### library_links: 수동 확인된 게임 연결
| 항목 | 의미 |
|---|---|
| game_id | PlayDock 로컬 게임 ID |
| store | 사용자가 선택한 판매처 |
| code | 사용자가 지정한 작품 코드 |

압축파일명에서 자동 추출한 번호는 필요할 때 읽고, 사용자가 명시적으로 확정·수정한 경우만
링크를 저장합니다. 원본 파일명·압축파일명·확인 시각은 중복 저장하지 않습니다.
게임 이름·모음집·개인 설정은 기존 JSON과 이미지 캐시를 그대로 사용합니다.

## 기존 데이터 이전
1. 과거 v1/v2 `playdock.db`를 SQLite 온라인 백업으로
   `data/backups/playdock_pre_v3_*.db`에 보관하고 무결성을 확인합니다.
2. 동일 DB 내 기존 `works`, `work_titles`, `work_tags`,
   `work_images`, `official_works`, `library_links`를 트랜잭션으로 이전합니다.
3. 중복 DLsite 공식정보가 있으면 `works`의 기존 상세 제목과 제작사·언어별 제목을 보존하고
   공식 종류/URL을 보충합니다. Steam도 같은 works 테이블에 들어갑니다.
4. 이전 정체 판독기만 가지고 있던 `%LOCALAPPDATA%\PlayDock\official_works.sqlite3`는
   PlayDock 최초 시작 시 읽기 전용으로 한 번만 가져옵니다.
5. 예전 DB 파일과 백업은 자동 삭제하지 않습니다. 복사 전 손상·버전 오류를 확인합니다.

## 독립 정체 판독기 연결
- 스캐너가 설치 위치를 모르면 설치된 PlayDock 폴더를 한 번 지정합니다.
- 설치 표식 `PlayDock.install.json`(또는 공식 레거시 표식)을 확인하고
  그 하위 `data/playdock.db`만 저장 대상으로 사용합니다.
- 기억한 설치 경로는 DB가 아닌 작은 사용자별 JSON 설정 파일입니다.
- PlayDock가 없는 PC에서는 TXT 스캔은 가능하지만 **새 SQLite 파일을 임의로 만들지 않습니다**.
- 동시 접근은 SQLite 트랜잭션과 busy_timeout을 이용합니다.
- 공개 배포 EXE에는 개인 DB, 사용자 파일명, 사용자 설정·자격증명을 포함하지 않습니다.

## 현재 상태 확인
PlayDock 상단 **설정 → DB 상태 확인**에서 works 건수, 사이트별 건수,
사용자가 직접 지정한 라이브러리 연결 수와 SQLite 무결성을 확인할 수 있습니다.
DB 하나만 읽기 전용으로 조회합니다.

정확한 SQLite 구조 예시는 `docs/PlayDock_DB_Schema_v3.sql`에 있습니다.
