PlayDock — DLsite 우선 · Steam 식별번호 확인기

실행파일: PlayDock-DLsite-Steam-Checker.exe

조회 순서
  1) 파일명에 DLsite 품번(RJ/VJ/BJ/EJ)이 있으면 공식 DLsite 작품 페이지 조회
  2) DLsite 품번이 없거나 DLsite에서 확인한 작품이 하나도 없다면
     파일명에 명시된 Steam App ID로 Steam 상점 페이지 조회
  3) DLsite/Steam 어느 쪽도 공식 작품명을 확인하지 못하면 [제외]
  4) DLsite 품번과 Steam App ID가 모두 있으면 DLsite를 우선 적용하며,
     DLsite 확인이 성공하면 Steam은 조회하지 않습니다.

인식되는 예시
  Game [RJ01052720].7z
  Game [Steam 1091500].zip
  Game [SteamAppID=1091500].rar
  Game [AppID:1091500].zip
  Game [RJ01052720] [Steam 1091500].7z
  1091500 (직접 입력창에 입력한 숫자만 허용)

인식하지 않는 예시
  Game [v1.1091500].zip / Game 1091500.zip
  위 파일의 숫자는 Steam 식별번호인지 알 수 없으므로 자동 검색하지 않습니다.

사용 방법
  [압축파일 선택] 또는 [폴더의 압축파일 선택] → [DLsite → Steam 확인 시작].
  파일명에 식별번호가 없다면 제목으로 인터넷 검색하지 않고 [제외]로 분류합니다.
  폴더를 선택하면 바로 아래 ZIP/7z/RAR만 검사하며 하위 폴더와 압축 내부는 열지 않습니다.
  다중 품번은 각각 확인하며, DLsite에서 하나라도 확인되면 DLsite 결과를 우선합니다.
  [CSV 저장]/[JSON 저장]으로 결과와 사이트별 조회 기록을 보존할 수 있습니다.
  공식 페이지를 확인한 행은 더블클릭하여 브라우저로 열 수 있습니다.
  같은 실행에서 같은 식별번호를 반복 조회하지 않도록 메모리 캐시를 사용합니다.

판정 안내
  [공식 이름 확인] = 선택된 사이트의 모든 식별번호에서 공식 작품명을 확인
  [일부 확인] = 선택된 사이트의 식별번호 일부만 공식 작품명 확인
  [제외 · 확인되지 않음] = DLsite/Steam 모두 확인 실패 또는 명시적 번호 없음
  제외는 미등록/비게임/파일이 가짜라는 뜻이 아닙니다.
  공식 작품명 확인은 실제 압축파일 속 게임의 동일성까지 확인한 결과가 아닙니다.

주의
  DLsite는 공식 HTML을 사용합니다. Steam은 API 키가 필요 없는 공개 Store
  상품정보 JSON을 먼저 확인하고 실패 시 공식 HTML을 시도합니다.
  별도의 API 키·유료 API를 요구하지 않습니다. Bing RSS, DDGS, Google 제목 검색,
  기계번역은 사용하지 않습니다.
  Steam App ID는 파일명에 Steam 또는 AppID 등으로 명시된 경우만 인정합니다.
  조회 실패는 사이트의 차단/연령 확인/장애일 수 있습니다.
  사용자 개인 경로와 게임 목록을 공개 배포판에 넣지 않습니다.
  최대 1000개 입력/파일명 일괄 처리, 진행률·중단 기능을 제공합니다.

빌드 및 검사: GitHub Actions -> PlayDock DLsite→Steam Windows 빌드
