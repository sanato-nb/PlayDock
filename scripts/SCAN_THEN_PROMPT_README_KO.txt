PlayDock — 품번 → 공식 이름 확인 → TXT로 복사·붙여넣기
Windows 10/11 콘솔 실행파일: PlayDock-ID-Scan-And-Prompt.exe

이 프로그램의 역할
  ZIP / 7z / RAR 게임 압축파일의 파일명만 읽어
  DLsite(RJ/VJ/BJ/EJ) 우선, 실패하면 명시된 Steam App ID로
  공식 작품명을 확인합니다. 제목 검색이나 AI API는 사용하지 않습니다.
  마지막 파일까지 검사가 끝난 후에만 결과 TXT를 출력합니다.

사용법
  1. PlayDock-ID-Scan-And-Prompt.exe를 실행합니다.
  2. 검사할 게임 압축파일 폴더의 전체 경로를 입력하고 Enter를 누릅니다.
     예: C:\Games\Archive
  3. 검사가 끝날 때까지 진행률을 확인합니다.
  4. 기본 결과 저장 위치:
        검사 폴더\PlayDock_Results\검사일시\
  5. 검사 실패 항목이 있으면 TXT 세 개를 자동 저장합니다.
        PlayDock_Scan_Results.txt     전체 파일, 품번, 공식 작품명과 URL, 실패 사유
        PlayDock_Excluded_Games.txt  공식 확인에 실패한 게임 목록만
        PlayDock_AI_Prompt.txt       AI 지침 + 실제 실패 게임 목록 전체
  6. ★ 사용자가 자기 ChatGPT/Claude 같은 AI에 입력할 것은
        PlayDock_AI_Prompt.txt 딱 한 파일의 전체 내용입니다.
     메모장으로 열기 → Ctrl+A → Ctrl+C → AI 채팅창에 Ctrl+V.
     별도 JSON 파일을 AI에 업로드할 필요가 없습니다.
  7. AI가 조사한 품번을 검토하고, AI가 제공한 안전한 이름 변경 도구는
     변경 전/후 이름을 보고 직접 승인한 뒤에만 실행합니다.
  8. 끝까지 못 찾은 게임은 기존 이름을 유지하고 수동 확인합니다.

실패한 파일이 없는 경우
  PlayDock_Scan_Results.txt 하나만 생성됩니다.
  AI 조사 대상이 없으므로 AI 프롬프트는 만들지 않습니다.

예시
  검사 결과 TXT:
      [1] 공식 확인
      파일명: Test Game [RJ123456].zip
      선택된 판매처: DLSITE
      공식 작품명: (공식 페이지에서 가져온 이름)

  AI 프롬프트 TXT:
      # PlayDock — 실패 게임 품번 조사와 파일명 변경 도구 제작 요청
      ... 조사 지침 ...
      ===== 실제 제외 게임 목록 시작 =====
      [2] Name [v1.2].7z
      기존 DLsite 품번: 없음
      기존 Steam App ID: 없음
      실패 유형: 식별번호 없음
      ===== 실제 제외 게임 목록 끝 =====

명령줄
  PlayDock-ID-Scan-And-Prompt.exe "C:\Games\Archive"
  PlayDock-ID-Scan-And-Prompt.exe "C:\Games\Archive" --output "D:\ScanResults"
  PlayDock-ID-Scan-And-Prompt.exe "C:\Games\Archive" --top-level

안전/프라이버시
  - TXT는 UTF-8(BOM)으로 저장되므로 Windows 메모장에서 정상 표시됩니다.
  - 게임 압축파일을 풀거나 내부 데이터를 읽지 않습니다.
  - 스캔 경로는 파일에 남지 않습니다. 게임 이름과 품번/공식 URL만 기록합니다.
  - AI 프롬프트에 개발자 GitHub/계정/브랜치/개인 경로를 넣지 않습니다.
  - 공개 EXE에 API 키, 개인 게임 목록, 캐시 및 테스트 데이터가 포함되지 않습니다.
  - 이름 변경이나 AI 연구는 사용자 자신의 AI가 별도로 수행합니다.
  - 조회 실패는 작품 미등록의 증거가 아닙니다.
  - 게임 폴더 및 하위 폴더의 압축파일까지 검색합니다. 심볼릭 링크는 제외합니다.
  - 동일 이름의 게임 파일이 서로 다른 폴더에 있으면 AI가 수동 확인하도록 안내합니다.
  - 최대 1000개 파일을 한 번에 검사합니다.
  - 검사 중 중단/실패 시 완성된 검사 결과로 표시하거나 AI 프롬프트를 만들지 않습니다.
