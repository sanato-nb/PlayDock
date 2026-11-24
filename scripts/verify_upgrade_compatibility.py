"""Cross-revision, offline upgrade compatibility using real release payloads."""
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch
from zipfile import ZipFile

def snapshot(root):
    return {p.relative_to(root).as_posix():sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}

def imports(source):
    sys.path[:0]=[str(source/"src/playdock"),str(source)]
    from core import Library
    from work_db import WorkDatabase
    try:
        from storage.collections import CollectionStore
        from storage.local import write_install_marker
        from services.simple_title_edit import save_display_title
    except ModuleNotFoundError:
        from game_collections import CollectionStore
        from local_storage import write_install_marker
        from simple_title_edit import save_display_title
    return Library,WorkDatabase,CollectionStore,write_install_marker,save_display_title

def describe(root,lib,db,collections):
    games=lib.scan()
    return {"games":[{"id":g.id,"title":lib.title(g),"meta":lib.meta(g),"installed":g.installed,
                      "external":g.external,"archive":g.archive.name if g.archive else None,
                      "link":db.get_link(g.id)} for g in games],
            "collections":collections.list(),"works":db.count_works(),
            "official":db.get_official_work("dlsite","RJ123456")}

def prepare(source,root):
    Library,WorkDatabase,CollectionStore,marker,save_title=imports(source)
    from PIL import Image
    program=root/"program";program.mkdir()
    marker(program)
    # Old program binaries are placeholders. Existing user data is generated
    # by the actual historical source, not hand-written schema assumptions.
    for name in ("PlayDock.exe","PlayDock_Uninstall.exe","PlayDock_TitleEditor.exe"):
        (program/name).write_bytes(b"MZ historical placeholder")
    (program/"personal.txt").write_bytes(b"keep personal file")
    archives=root/"archives";archives.mkdir()
    games=root/"games";games.mkdir()
    external=root/"external";external.mkdir()
    with ZipFile(archives/"Example [RJ123456].zip","w") as z:
        z.writestr("Game.exe",b"MZ example")
    with ZipFile(archives/"Other.zip","w") as z:
        z.writestr("Game.exe",b"MZ other")
    folder=games/"Example [RJ123456]";folder.mkdir()
    (folder/"Game.exe").write_bytes(b"MZ installed")
    (folder/"save.dat").write_bytes(b"game save untouched")
    (external/"Manual.exe").write_bytes(b"MZ external")
    lib=Library(program/"data")
    lib.change_root(games);lib.change_archive_root(archives)
    lib.settings.update(first_run_complete=True,title_language="ja",custom_preference="preserve",auto_art=False)
    lib.save_settings()
    lib.add_manual_executable(external/"Manual.exe")
    game=next(g for g in lib.scan() if "RJ123456" in g.name)
    lib.update_meta(game,original_archive_name=game.archive.name,product_code="RJ123456",
                    product_store="dlsite",executable="Game.exe",launch_arguments="--example")
    save_title(lib,game,"기존 수동 제목")
    save_title(lib,game,"보존할 게임 이름")
    art=lib.art_dir(game)
    Image.new("RGB",(1600,520),"blue").save(art/"hero.png")
    Image.new("RGB",(256,256),"green").save(art/"icon.png")
    cols=CollectionStore(lib.store)
    cols.set_game_memberships(game.id,{cols.create("첫 모음집"),cols.create("두 번째 모음집")})
    db=WorkDatabase(lib.store)
    db._upsert_verified([{"store":"dlsite","code":"RJ123456","title":"Official Example",
                         "page_url":"https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"}])
    assert db.save_verified_game_link(game.id,"dlsite","RJ123456")
    db.save_official_image_urls("dlsite","RJ123456",{"hero":"https://img.dlsite.jp/cover.jpg"})
    for d in ("backups","logs"):
        (lib.store/d).mkdir(exist_ok=True)
    with ZipFile(lib.store/"backups"/"old-backup.zip","w") as z:
        z.writestr("manifest.json","{}")
    (lib.store/"logs"/"prior.log").write_text("existing log",encoding="utf-8")
    (root/"expected.json").write_text(json.dumps(describe(root,lib,db,cols),ensure_ascii=False),encoding="utf-8")

def verify(source,root,dist,out):
    Library,WorkDatabase,CollectionStore,_,_=imports(source)
    import setup_wizard as setup
    import install_management as mgr
    from storage.local import marker_is_valid
    from PyInstaller.archive.readers import CArchiveReader
    program=root/"program";data=program/"data"
    expected=json.loads((root/"expected.json").read_text(encoding="utf-8"))
    before=snapshot(data)
    gamefiles={d:snapshot(root/d) for d in ("archives","games","external")}
    # Actual installer payload, byte-for-byte equal to standalone build outputs.
    bundle=CArchiveReader(str(dist/"PlayDock_Setup.exe"))
    for name in ("PlayDock.exe","PlayDock_Uninstall.exe"):
        members=[n for n in bundle.toc if n.replace("\\","/")=="payload/"+name]
        assert len(members)==1,members
        assert sha256(bundle.extract(members[0])).hexdigest()==sha256((dist/name).read_bytes()).hexdigest()
    lib=Library(data);db=WorkDatabase(data);cols=CollectionStore(data)
    def check():
        actual=describe(root,lib,db,CollectionStore(data))
        assert json.loads(json.dumps(actual,ensure_ascii=False))==expected
        assert snapshot(data)==before
        assert all(snapshot(root/d)==v for d,v in gamefiles.items())
        assert (program/"personal.txt").read_bytes()==b"keep personal file"
    check()
    # Manual binary replacement does not write to user data.
    shutil.copy2(dist/"PlayDock.exe",program/"PlayDock.exe")
    check()
    # Invoke the actual installer business path; isolate host registry/shortcuts.
    class Wizard:
        install_archive=str(root/"archives")
        install_game_dir=str(root/"games")
        install_program_dir=program
        install_desktop=False
        messages=queue.Queue()
    with ExitStack() as stack:
        for name,value in {
            "payload_executable":lambda:dist/"PlayDock.exe",
            "payload_uninstaller":lambda:dist/"PlayDock_Uninstall.exe",
            "app_install_directory":lambda:program,
            "legacy_data_dir":lambda:root/"nonexistent-legacy",
            "register_uninstall_entry":lambda p:None,
            "create_shortcut":lambda a,b:None,
            "desktop_directory":lambda:root/"desktop",
            "shortcut_points_to":lambda a,b:False,
        }.items():
            stack.enter_context(patch.object(setup,name,value))
        wizard=Wizard()
        setup.SetupWizard.install(wizard)
        messages=[]
        while not wizard.messages.empty():
            messages.append(wizard.messages.get_nowait())
        assert messages[-1][0]=="done",messages
        assert not any(m[0]=="error" for m in messages),messages
    assert marker_is_valid(program)
    assert not (program/"PlayDock_TitleEditor.exe").exists()
    for name in ("PlayDock.exe","PlayDock_Uninstall.exe"):
        assert sha256((program/name).read_bytes()).hexdigest()==sha256((dist/name).read_bytes()).hexdigest()
    # Settings are rewritten atomically; compare JSON meaning and other files by SHA.
    old_settings=lib.settings.copy()
    lib=Library(data)
    assert lib.settings==old_settings
    after=snapshot(data)
    assert {k:v for k,v in after.items() if k!="settings.json"}=={k:v for k,v in before.items() if k!="settings.json"}
    before=after
    check()
    with ExitStack() as stack:
        stack.enter_context(patch.object(mgr,"app_install_directory",lambda:program))
        stack.enter_context(patch.object(mgr,"expected_shortcuts",lambda:[]))
        stack.enter_context(patch.object(mgr,"remove_uninstall_entry",lambda:None))
        removed=mgr.uninstall_application()
    assert not marker_is_valid(program)
    assert not any((program/n).exists() for n in mgr.INSTALLED_FILES)
    check()
    report={"historical_data_created":True,"manual_binary_replace":True,"installer_payload_verified":True,
            "installer_upgrade":True,"uninstall_preserves_data":True,"game_files_preserved":True,
            "preserved_data_files":len(before),"preserved_game_files":sum(map(len,gamefiles.values())),
            "games":len(expected["games"]),"collections":len(expected["collections"]),"removed":removed,
            "scope":"source install/uninstall business logic, actual EXE payload; host registry and shortcuts isolated"}
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("UPGRADE_COMPATIBILITY_VERIFIED",json.dumps(report,ensure_ascii=False))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--baseline",type=Path,required=True)
    ap.add_argument("--source",type=Path,required=True)
    ap.add_argument("--dist",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--prepare",type=Path)
    a=ap.parse_args()
    if a.prepare:
        prepare(a.baseline.resolve(),a.prepare)
        return
    with tempfile.TemporaryDirectory(prefix="playdock-upgrade-") as tmp:
        root=Path(tmp)
        subprocess.run([sys.executable,__file__,"--baseline",str(a.baseline.resolve()),
                        "--source",str(a.source.resolve()),"--dist",str(a.dist.resolve()),
                        "--output",str(a.output.resolve()),"--prepare",str(root)],check=True,
                       cwd=a.baseline.resolve(),env={k:v for k,v in os.environ.items() if k!="PYTHONPATH"})
        verify(a.source.resolve(),root,a.dist.resolve(),a.output.resolve())

if __name__=="__main__":
    main()
