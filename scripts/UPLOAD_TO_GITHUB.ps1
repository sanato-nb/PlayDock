$ErrorActionPreference = 'Stop'
$Source = (Resolve-Path (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) '..')).Path
$Remote = 'https://github.com/sanato-nb/PlayDock.git'
$Working = Join-Path $env:TEMP ('PlayDockGitUpload_' + [Guid]::NewGuid().ToString('N'))
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git for Windows를 먼저 설치해 주세요: https://git-scm.com/download/win' }
Write-Host 'PlayDock GitHub 저장소를 복제합니다.'
& git clone $Remote $Working
if ($LASTEXITCODE -ne 0) { throw 'git clone 실패: GitHub 로그인 및 연결 상태를 확인하세요.' }
Write-Host '개인 데이터가 없는 v0.8.3 소스 파일을 복사합니다.'
$exDirs = @('.git', '.venv', 'venv', 'build', 'dist', '__pycache__', '.pytest_cache', 'data', 'public_release', 'release', 'backups')
$exFiles = @('*.pyc', '*.pyo', '*.pyd', '*.log', '*.zip', '*.7z', '*.rar', '*.db', '*.sqlite', '*.sqlite3', 'settings.json', 'collections.json', 'manual_games.json', 'product_titles.json', 'PlayDock.install.json', 'LocalGameShelf.install.json', '.env', '.env.*', 'UPLOAD_TO_GITHUB.ps1', '02_UPLOAD_TO_GITHUB.bat')
& robocopy $Source $Working /E /XD $exDirs /XF $exFiles /NFL /NDL /NJH /NJS /NC /NS
if ($LASTEXITCODE -gt 7) { throw '소스 복사 중 오류가 발생했습니다.' }
& git -C $Working add -A
if ($LASTEXITCODE -ne 0) { throw 'git add 실패' }
& git -C $Working diff --cached --quiet
if ($LASTEXITCODE -eq 0) { Write-Host '추가할 변경사항이 없습니다.'; exit 0 }
Write-Host '개인 data 폴더는 복사하지 않고 한글 커밋 메시지로 등록합니다.'
& git -C $Working commit -m '구조: 프로젝트 폴더 정리 및 소스 파일 분류'
if ($LASTEXITCODE -ne 0) { throw '커밋 실패: git 사용자 이름/이메일 설정을 확인하세요.' }
& git -C $Working push origin HEAD:main
if ($LASTEXITCODE -ne 0) { throw '업로드 실패: GitHub 인증이나 저장소 권한을 확인하세요.' }
Write-Host '완료: https://github.com/sanato-nb/PlayDock'
