"""Ensure the independent release audit detects unexpected files and altered bytes."""
from pathlib import Path
from zipfile import ZipFile
import pytest
from make_public_release import EXECUTABLES, MANUAL_FILENAME, build_public_release
from verify_public_bundle import verify

@pytest.fixture
def bundle(tmp_path):
    dist=tmp_path/"dist";dist.mkdir()
    for name in EXECUTABLES:
        (dist/name).write_bytes(b"MZ"+name.encode()+b"\0"*100001)
    manual=tmp_path/MANUAL_FILENAME
    manual.write_bytes(b"%PDF-1.4\n%%EOF")
    result=build_public_release(dist,tmp_path/"public",manual)
    return result,dist,manual

def test_actual_packaging_output_matches_checksums(bundle):
    r,d,m=bundle
    report=verify(r["zip"],r["setup"],d,m,"fixture")
    assert report["empty_data"]
    assert len(report["archive_members"])==9

def test_unexpected_user_data_is_rejected(bundle):
    r,d,m=bundle
    with ZipFile(r["zip"],"a") as z:
        z.writestr("data/settings.json","PRIVATE_FIXTURE")
    with pytest.raises(AssertionError,match="Unexpected archive members"):
        verify(r["zip"],r["setup"],d,m,"fixture")

def test_mismatched_exe_rejected(bundle):
    r,d,m=bundle
    with (d/"PlayDock.exe").open("ab") as f:
        f.write(b"changed")
    with pytest.raises(AssertionError,match="PlayDock.exe"):
        verify(r["zip"],r["setup"],d,m,"fixture")
