# 2-C 불필요한 AI 기능 정리

기준: 49d7de255ded0b8937513f4abaec11d8b83d2387. 2-B 전체 Windows 검증 1103 passed, 1 skipped.
수정: 1d9697a975363f35b82e678168f6130560add001.

## 제거
- 현재 메뉴에 연결되지 않는 AI 설정 창 SettingsDialog와 MainWindow.settings_dialog, 관련 UI import.
- artwork.generate_ai_art, ai_providers.image_bytes, IMAGE_URL, 이미지 생성용 base64 처리 및 OpenAI/Gemini/OpenRouter 생성 요청.
- 기존 이미지 생성 테스트 4개를 폐기 기능 부재 테스트 1개로 통합한다. 기존 생성 이미지 저장 테스트는 수동 이미지 저장과 크기 검증으로 대체한다. Gemini 이미지 오류 테스트는 텍스트 요청 오류 및 비밀키 노출 방지로 교체한다.

## 유지
- 현재 공식 이미지 적용, 로컬 이미지 선택·캐시 저장·자르기, 원본 게임과 기존 생성 이미지.
- 이름 편집기의 텍스트 AI 추천/번역, 환경 변수와 기존 자격증명 참조, API 요청에 대한 기존 비용 확인.
- 기존 AI 모델 설정 필드와 설정 저장 서비스(호환), keyring 등 기존 의존성. PROVIDERS의 image/image_model은 과거 설정을 보존하기 위한 메타데이터로 남으며 이미지 생성 지원을 의미하지 않는다.
- 게임 정보 수집의 외부 AI 조사 TXT·PowerShell 인계 기능.
- AI 설정 창 제거 후 예전 편집기의 누락 키 안내는 환경 변수 또는 기존 Windows 자격 증명 저장소 확인으로 바뀐다.
- 모든 사용자 데이터·DB·설정·키·독립 실험·빌드 의존성 보존. 파일을 삭제하지 않음.

## 검증
6개 본체 소스만 변경. 정적 감사에서 제거 심볼/생성 요청 경로의 잔존 여부 확인, 필수 텍스트 AI와 이미지 저장·탐색 함수 AST 동일 확인, 나머지 본체 및 실험 SHA 보존. 전체 Windows 회귀 테스트 실행. 검증 전 main 병합 금지. 역사적 1-B/2-B 전용 검증은 원래 커밋에 고정하였다.
