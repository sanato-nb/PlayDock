# PlayDock 본체 — 정체 판독기 공식 작품정보 가져오기

## 데이터 이동

정체 판독기는 Windows 사용자별 %LOCALAPPDATA%\PlayDock\official_works.sqlite3에 저장합니다.
PlayDock 본체는 시작 시 또는 '새로고침'을 누르면 이 파일을 읽고,
PlayDock 자체 사용자 데이터 폴더(data/playdock.db)의 official_works 테이블로 가져옵니다.
원본 SQLite 파일은 삭제·이동·수정하지 않습니다.

## 가져오는 필드

| 열 | 설명 |
|---|---|
| store | dlsite 또는 steam |
| product_id | DLsite 작품 품번 또는 Steam App ID |
| official_title | 공식 작품명 |
| category | 사이트별 작품 종류·분류 |
| page_url | 공식 작품 페이지 URL |
| verified_at_utc | 최종 공식 확인 시각 |

게임을 선택하면 상세 패널에 정보가 표시됩니다.
게임 관리 및 우클릭 메뉴의 '저장된 공식 작품 페이지 열기'를 통해 URL을 엽니다.
Steam ID는 파일명에 Steam 1091500처럼 명시적으로 표시된 경우에만 연결합니다.

## 안전한 처리

- 기존 works 테이블, 사용자 이름·모음집·이미지 및 게임 파일은 변경하지 않습니다.
- 공식 정보가 없으면 게임 상세 화면에서 공식 필드를 표시하지 않습니다.
- 기존 DB 버전 1은 테이블을 추가하는 버전 2 마이그레이션으로 업그레이드합니다.
- 가져온 작품정보는 PlayDock 내장 백업 기능에 포함됩니다.
- 사용자의 개인 DB를 공개 EXE나 GitHub 배포 파일에 넣지 않습니다.
- 정체 판독기를 더 이상 실행하지 않아도 이미 가져온 정보는 남아 있습니다.
- 게임 품번과 공식 작품 정보의 일치는 실제 압축파일의 내용 동일성을 보장하지 않습니다.

## 다른 PC에서 가져올 때

사용자별 검사 DB가 없는 환경에서는 가져올 기록이 없습니다.
기존 사용자가 다른 PC에 저장된 스캐너 DB를 옮기려면
대상 PC의 %LOCALAPPDATA%\PlayDock 폴더에 official_works.sqlite3를 배치한 뒤
PlayDock의 '새로고침'을 누르면 됩니다.
