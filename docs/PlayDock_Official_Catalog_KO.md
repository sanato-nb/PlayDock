# PlayDock — 공식 작품정보 공유 DB

## 목적
독립 게임 정체 판독기에서 이미 성공적으로 조회한 DLsite/Steam 공식 정보를
PlayDock의 다른 기능에서 재사용합니다. 사용자의 게임 목록, 파일명, 저장 경로,
설정 및 게임 압축파일과 **완전히 분리된 공개 메타데이터**만 저장합니다.

## 저장 위치
- Windows: `%LOCALAPPDATA%\PlayDock\official_works.sqlite3`
- 실제 파일은 공식 작품 확인이 최소 1건 성공한 경우에만 생성됩니다.
- 스캔 폴더의 `PlayDock_Results`에는 기존처럼 TXT 하나만 생성됩니다.
- 테스트용으로 `PLAYDOCK_OFFICIAL_CATALOG_PATH` 환경변수로 DB 경로를 지정할 수 있습니다.
- 사용자별 DB이므로 GitHub에 올리거나 배포 ZIP에 넣지 않습니다.

## 테이블
```sql
CREATE TABLE official_works (
  store TEXT NOT NULL,              -- dlsite / steam
  product_id TEXT NOT NULL,         -- RJ... / Steam App ID
  official_title TEXT NOT NULL,     -- 공식 작품명
  category TEXT NOT NULL,           -- 사이트가 반환한 원본 작품 종류·분류
  page_url TEXT NOT NULL,           -- 공식 작품 페이지 URL
  verified_at_utc TEXT NOT NULL,    -- 최종 성공 조회 시각 (UTC)
  PRIMARY KEY(store, product_id)
);
```

동일한 (사이트, 품번) 조합은 중복 저장하지 않고 최신 성공 조회값으로 갱신합니다.
조회 실패, 제외, 미확인 상태는 저장하지 않으며 이전 성공 기록을 지우지 않습니다.
DLsite `category`는 사이트의 카테고리 값(예: `maniax`), Steam `category`는 상품 종류(예: `game`)입니다.
두 사이트의 값이 반드시 같은 의미나 장르를 뜻하지는 않습니다.

## 다른 PlayDock 기능에서 읽기
다른 앱 코드에서 `src/playdock`를 Python 모듈 경로로 사용한다면:

```python
from database.official_catalog import OfficialWorkCatalog
db = OfficialWorkCatalog()
work = db.get_work("dlsite", "RJ01234567")
# work["official_title"], work["category"], work["page_url"]
steam = db.get_work("steam", "1091500")
```

파일 조회는 SQLite 읽기 전용으로 이루어지고, 없는 데이터는 `None`을 돌려줍니다.
별도 네트워크 요청도 발생하지 않습니다.

## 기존 PlayDock 작품 DB와의 관계
기존 설치 데이터의 `playdock.db`는 DLsite 중심 메타데이터와 로컬
라이브러리 연결 정보가 들어 있습니다. 이를 임의로 변경·이관하지 않습니다.
새 공식정보 DB는 **별개 데이터베이스**이며 다른 PlayDock 기능에서 읽도록
추가 연결해야 합니다. 기존 `playdock.db` 백업에는 이 파일이 자동 포함되지
않으므로 추후 앱 백업 기능에 포함하는 작업이 필요합니다.

## 안전
- EXE에서 사용자의 이름 변경, DB 라이브러리 연결, ZIP/7z/RAR 바이트 변경 없음
- 공식 사이트에서 검증된 데이터만 기록; 로컬 경로·파일명·API 키 없음
- 스캔 중단, TXT 생성 실패 시 저장하지 않음
- SQLite 저장에 실패해도 기존 통합 TXT 생성 성공 결과는 유지
