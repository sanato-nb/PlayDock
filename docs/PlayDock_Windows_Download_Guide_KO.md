# PlayDock Windows 다운로드 종류 안내

기존에는 하나의 GitHub Actions 아티팩트 안에 `PlayDock.exe`, `PlayDock_Setup.exe`,
`PlayDock_Public_v0.8.3.zip`을 모두 중복으로 포함해 다운로드 파일이 약 345MB였습니다.

이제 **다운로드를 세 종류로 분리**합니다.

| GitHub Actions 아티팩트 | 내용 | 추천 사용자 |
|---|---|---|
| `PlayDock-Update-EXE-Windows` | `PlayDock.exe`, `SHA256SUMS.txt` | PlayDock가 이미 설치되어 있고 기존 실행파일만 업데이트하려는 사용자 |
| `PlayDock-Installer-Only-Windows` | `PlayDock_Setup_v0.8.3.exe` | 새로 설치하거나 설치 마법사가 필요한 사용자 |
| `PlayDock-Full-Package-Windows` | 전체 배포 ZIP과 검사 결과 | 설치기·실행파일을 한꺼번에 보관해야 하는 사용자 |

GitHub Actions는 선택한 아티팩트 하나만 ZIP으로 다운로드합니다.
GitHub 아티팩트 자체를 압축하는 과정에서 PyInstaller EXE나 기존 ZIP 파일은
대개 이미 압축되어 있으므로, 아티팩트에는 불필요한 추가 압축을 적용하지 않습니다.

## 업데이트 절차
1. PlayDock를 종료합니다.
2. 기존 `data` 폴더와 설정·이미지 캐시는 그대로 유지합니다. 가능하면 데이터 백업을 만듭니다.
3. `PlayDock-Update-EXE-Windows` 아티팩트를 내려받아 압축을 풉니다.
4. 설치된 PlayDock의 `PlayDock.exe`만 새 파일로 교체합니다.
5. 기존 사용자 파일·설정 폴더를 통째로 지우거나 설치 폴더를 초기화하지 않습니다.

설치 위치가 쓰기 보호된 경우 관리자 권한이 필요할 수 있으므로,
실행파일 수동 교체가 어렵다면 설치용 아티팩트를 사용합니다.

이 변경은 **배포 방식만 변경**합니다. 게임 정체 판독·공식 이미지 적용,
기존 사용자 데이터, PlayDock DB는 수정하지 않습니다.
