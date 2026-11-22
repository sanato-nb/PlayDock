PlayDock — 품번→공식 작품명 확인 · 검사 완료 후 AI 프롬프트 제공
Windows 10/11용 콘솔 실행파일: PlayDock-ID-Scan-And-Prompt.exe

설명
  이 EXE는 단 한 가지 작업을 합니다.
  사용자의 ZIP / 7z / RAR 게임 압축파일 이름에서 이미 명시된 품번을 찾고
  DLsite 우선 → 실패 시 Steam 공식 작품명을 확인합니다.
  전체 검사가 종료되면 실패 목록과 AI 프롬프트를 저장합니다.
  AI나 이름 변경 기능을 프로그램 안에 탑재하지 않습니다.

사용법 (더블클릭)
  1. PlayDock-ID-Scan-And-Prompt.exe 더블클릭.
  2. 게임 압축파일이 있는 폴더 전체 경로를 입력하고 Enter.
     예: C:\Games\Archive
  3. 진행률과 마지막 분류 수를 확인합니다.
  4. 검사 완료 후 자동으로 결과 저장 위치가 표시됩니다.
     기본 위치: 입력 폴더\PlayDock_Results\검사일시\
  5. 실패 파일이 있다면 자동으로 세 파일이 생성됩니다.
       PlayDock_Scan_Results.json    전체 검사 결과
       PlayDock_Excluded_Games.json 실패한 게임 이름만
       PlayDock_AI_Prompt.txt       이용자 자신의 AI에 보낼 조사 지침
  6. 이용자가 자신의 ChatGPT/Claude 등 AI에 제외 목록 JSON과 프롬프트 TXT를 첨부합니다.
     AI가 DLsite→Steam 동일 작품 여부를 조사한 뒤 별도 파일명 변경 도구와
     미확인 수동 처리 목록을 제공하도록 요청하는 내용입니다.
  7. 게임을 모두 확인했다면 전체 결과 JSON 하나만 생성됩니다.
     실패가 없으므로 AI 프롬프트를 생성하지 않습니다.

명령줄 사용
  PlayDock-ID-Scan-And-Prompt.exe "C:\Games\Archive"
  PlayDock-ID-Scan-And-Prompt.exe "C:\Games\Archive" --output "D:\ScanResults"
  PlayDock-ID-Scan-And-Prompt.exe "C:\Games\Archive" --top-level

주의사항
  - 기존에 있던 품번만 확인하는 기능입니다. 제목 자동 검색은 하지 않습니다.
  - DLsite 품번 RJ/VJ/BJ/EJ 또는 파일명에 'Steam 1091500', 'AppID 1091500'처럼
    명시된 Steam App ID만 인식합니다.
  - 두 식별번호가 있으면 DLsite가 우선입니다.
  - Steam은 API 키가 필요 없는 공개 Store 상품 정보를 이용합니다.
  - 같은 품번은 같은 실행 중 캐시 결과를 재사용합니다.
  - 제외는 미등록·가짜 게임이라는 판정이 아닙니다.
  - 수동 변경/AI 단계에서는 본편·DLC·합본의 작품번호를 반드시 구별해야 합니다.
  - 게임 압축파일은 열거나 압축 해제하지 않습니다.
  - 선택한 폴더 아래 하위 폴더들도 검색합니다 (심볼릭 링크 제외).
  - 결과 파일에는 파일명만 포함하고 폴더 전체 경로는 넣지 않습니다.
  - AI 프롬프트에는 개발자 GitHub/사용자명/브랜치/경로를 넣지 않습니다.
  - 공개 EXE에 이용자 게임 목록, API 키, 개인 설정, 캐시가 없습니다.
  - 도중에 Ctrl+C를 누르면 검사가 중단되고 AI 프롬프트를 생성하지 않습니다.
  - 검사 가능한 압축파일은 한번에 최대 1000개입니다. 더 많으면 폴더를 나눠 실행하세요.
  - 프롬프트는 검사가 정상 완료된 뒤 실패 항목이 있을 때에만 생성됩니다.
