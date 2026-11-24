"""Independently verify a built privacy-clean public archive against exact EXEs."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from zipfile import ZipFile

from make_public_release import (EXECUTABLES, INSTALL_MARKER, MANUAL_FILENAME,
                                 REQUIRED_ZIP, SUMS_FILENAME, VERSION)

def digest(stream):
    h=hashlib.sha256()
    for chunk in iter(lambda:stream.read(1024*1024),b""):
        h.update(chunk)
    return h.hexdigest()

def file_hash(path):
    with path.open("rb") as stream:
        return digest(stream)

def verify(archive, installer, dist, manual, commit):
    expected=set(EXECUTABLES)|{MANUAL_FILENAME}
    with ZipFile(archive) as z:
        names=z.namelist()
        assert len(names)==len(REQUIRED_ZIP) and set(names)==REQUIRED_ZIP, "Unexpected archive members"
        assert z.testzip() is None, "ZIP integrity error"
        assert z.getinfo("data/").is_dir() and z.read("data/")==b"", "Data is not empty"
        assert json.loads(z.read(INSTALL_MARKER))=={"id":"playdock-installed-v1",
            "data_directory":"data","version":VERSION}, "Unexpected installation marker"
        sums={}
        for line in z.read(SUMS_FILENAME).decode("utf-8").splitlines():
            value,name=line.split("  ",1)
            assert name not in sums and len(value)==64, "Invalid checksum record"
            sums[name]=value.lower()
        assert set(sums)==expected, "Checksum member list mismatch"
        for name in sorted(expected):
            path=manual if name==MANUAL_FILENAME else dist/name
            with z.open(name) as stream:
                assert digest(stream)==sums[name]==file_hash(path), name
        assert file_hash(installer)==sums["PlayDock_Setup.exe"], "Installer mismatch"
    return {"commit":commit,"package_version_label":VERSION,
            "archive_members":sorted(names),"empty_data":True,"file_sha256":sums,
            "zip_sha256":file_hash(archive),"zip_bytes":archive.stat().st_size,
            "setup_sha256":file_hash(installer),"setup_bytes":installer.stat().st_size,
            "launcher_bytes":(dist/"PlayDock.exe").stat().st_size,
            "note":"Allowlisted archive and matching checksums verified; not a malware scan or native UI approval."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--dist",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--manual",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    a=p.parse_args()
    commit=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
    report=verify(a.out/f"PlayDock_Public_v{VERSION}.zip",
                  a.out/f"PlayDock_Setup_v{VERSION}.exe",a.dist,a.manual,commit)
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("PUBLIC_PACKAGE_VERIFIED",json.dumps(report,ensure_ascii=False))

if __name__=="__main__":
    main()
