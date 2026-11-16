from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANUAL = 'PlayDock_UserManual_KO_v0.7.7.pdf'

def test_batch_files_are_cmd_safe_and_refer_to_existing_manual():
    assert (ROOT / 'docs' / MANUAL).exists()
    for script in ('00_BUILD_WINDOWS_EXE.bat', '01_REPACKAGE_EXISTING_EXES.bat'):
        payload = (ROOT / script).read_bytes()
        assert payload.isascii()
        assert b'\r\n' in payload
        assert payload.count(b'--manual ') == 1
        assert MANUAL.encode('ascii') in payload
        assert b'--source ' in payload

def test_github_workflow_uses_existing_manual():
    script = (ROOT / '.github/workflows/build-windows-exe.yml').read_text(encoding='utf-8')
    assert 'docs/' + MANUAL in script
    assert 'docs/PlayDock_사용자설명서_v0.7.7.pdf' not in script
