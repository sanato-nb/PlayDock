PlayDock — 품번 → 공식 이름 확인 → 결과 TXT 하나로 AI 인계
Windows 10/11 콘솔 실행파일: PlayDock-ID-Scan-And-Prompt.exe

이 프로그램의 역할
  ZIP / 7z / RAR 압축파일의 파일명만 읽어
  DLsite(RJ/VJ/BJ/EJ) 우선, 실패하면 명시된 Steam App ID로
  공식 작품명을 조회합니다. 제목 자동 검색이나 AI API는 사용하지 않습니다.
  마지막 파일까지 검사가 끝난 후 단 하나의 TXT를 생성합니다.

사용법
  1. EXE를 실행합니다.
  2. 검사할 게임 압축파일 폴더의 전체 경로를 입력하고 Enter를 누릅니다.
     예: C:\Games\Archive
  3. 진행률과 DLsite→Steam 검사 결과가 끝날 때까지 확인합니다.
  4. 기본 저장 위치:
       검사 폴더\PlayDock_Results\검사일시\
  5. 검사 결과 파일은 하나입니다:
       PlayDock_Complete_Scan_And_AI_Prompt.txt

검사에 실패한 게임이 있다면 TXT 내용:
  - 요약: 전체/공식 확인/일부 확인/제외 수
  - 1부: AI 조사·이름 변경 도구 지침과 제외된 게임만
      A. 식별번호 없음 (공식 사이트 조회를 시작하지 않은 파일)
      B. 식별번호 존재하지만 공식 조회 실패 (기존 품번부터 재검증)
  - 2부: 공식 확인·일부 확인 게임만 간결하게 기록 (참고용)
      1부에 나온 제외 게임을 2부에 반복하지 않아 복사할 내용이 줄어듭니다.
  - AI에게는 표준 마크다운 결과표(원본/품번/공식 URL/근거/검증 상태/새 이름)와
    playdock-ai-review-v1 결과 JSON을 요구합니다.
  - 상태는 official_confirmed / candidate / unknown만 허용합니다.
    후보/미확인 항목의 파일명은 변경하지 않습니다.

이용자가 해야 할 일:
  TXT를 메모장으로 엽니다.
  Ctrl+A → Ctrl+C → 자신의 ChatGPT/Claude 등 AI 채팅창에서 Ctrl+V.
  TXT 1개만 복사하면 됩니다. JSON이나 다른 TXT를 첨부할 필요가 없습니다.
  AI 조사 대상은 1부에 명시된 '제외' 게임만입니다.
  이후 AI가 제공하는 이름 변경 도구는 미리보기와 최종 승인 후에 실행합니다.
  끝까지 찾지 못한 게임은 수동으로 확인하거나 원래 파일명을 유지합니다.

검사에 실패한 게임이 하나도 없다면:
  똑같이 TXT 하나만 생성되며, 전체 검사 결과와 'AI 조사 불필요' 안내만 들어갑니다.
  AI 조사 프롬프트는 포함되지 않습니다.

실행 명령줄 예시:
  PlayDock-ID-Scan-And-Prompt.exe "C:\Games\Archive"
  PlayDock-ID-Scan-And-Prompt.exe "C:\Games\Archive" --output "D:\ScanResults"
  PlayDock-ID-Scan-And-Prompt.exe "C:\Games\Archive" --top-level

안전/프라이버시
  - 결과는 UTF-8 BOM을 사용해 Windows 메모장에서 한글을 표시합니다.
  - 게임 압축파일을 풀거나 내부 내용을 읽지 않습니다.
  - 전체 폴더 경로는 TXT에 넣지 않습니다. 파일명·품번·공식 URL만 기록합니다.
  - 개인 GitHub 계정, 개발 브랜치, 개발 자료는 TXT 및 공개 EXE에 넣지 않습니다.
  - AI 조회나 이름 변경은 이용자가 자신의 AI와 별도 진행합니다.
  - 조회 실패는 미등록, 비게임, 잘못된 게임이라는 판정이 아닙니다.
  - 하위 폴더까지 압축파일을 찾지만 심볼릭 링크를 따라가지 않습니다.
  - 같은 이름의 파일이 여러 곳에 있으면 자동 이름 변경을 권장하지 않습니다.
  - 프로그램에서 AI API 키·사용자 인증키·개인 게임 목록을 수집하지 않습니다.
  - 검사 중 중단하거나 실패하면 정상 완료된 TXT로 표시하지 않습니다.
