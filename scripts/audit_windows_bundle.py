"""Check actual frozen Windows archive contents, not merely build flags."""
import argparse
import hashlib
import json
from pathlib import Path
from PyInstaller.archive.readers import CArchiveReader

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("exe",type=Path)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    archive=CArchiveReader(str(a.exe))
    names=set(archive.toc)
    pyz_names=[n for n in names if n.lower().endswith(".pyz")]
    assert pyz_names, "Missing Python module archive"
    modules=set()
    for name in pyz_names:
        modules.update(archive.open_embedded_archive(name).toc)
    required=["title_editor","ui.dialogs.file_dialog","workers.title","database.work_repository",
              "pyzipper","py7zr","rarfile","keyring","ddgs","send2trash","send2trash.win"]
    missing=[p for p in required if not any(m==p or m.startswith(p+".") for m in modules)]
    excluded=[m for m in modules if m=="send2trash.mac" or m.startswith("send2trash.mac.") or
              m in {"send2trash.plat_gio","send2trash.plat_other"}]
    qt=[n for n in names if n.lower().endswith(("qt6core.dll","qt6gui.dll","qt6widgets.dll"))]
    assert not missing, missing
    assert not excluded, excluded
    assert len(qt)>=3, qt
    assert any("qwindows.dll" in n.lower() for n in names), "Missing Windows Qt platform"
    report={"exe":a.exe.name,"bytes":a.exe.stat().st_size,
            "sha256":hashlib.sha256(a.exe.read_bytes()).hexdigest(),
            "archive_members":len(names),"python_modules":len(modules),
            "required":required,"excluded_non_windows":excluded,
            "qt_dlls":sorted(qt),"send2trash_modules":sorted(m for m in modules if m.startswith("send2trash"))}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print("WINDOWS_FROZEN_CONTENTS_VERIFIED",json.dumps(report,ensure_ascii=False))
if __name__=="__main__":
    main()
