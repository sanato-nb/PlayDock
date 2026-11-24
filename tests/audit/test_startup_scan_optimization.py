"""Installed game discovery need not rank every executable."""
from pathlib import Path
from time import perf_counter

import pytest
from services import launch_service as launch
from services import library_service as library

def put(root, relative):
    p=root/relative
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes(b"MZ")
    return p

@pytest.mark.parametrize("paths,expected", [
    ([], False),
    (["setup.exe", "uninstall.exe", "README.txt"], False),
    (["redist/game.exe", "support/game.exe", "backup/game.exe"], False),
    (["a/b/c/d/e/f/game.exe"], False),
    (["a/b/c/d/e/game.exe"], True),
    (["setup.exe","GAME.EXE"], True),
    (["a/b/Game-Win64-Shipping.exe"], True),
])
def test_presence_matches_ranked_candidate_contract(tmp_path, paths, expected):
    for path in paths:
        put(tmp_path,path)
    assert launch.has_executable_candidate(tmp_path) is expected
    assert bool(launch.executable_candidates(tmp_path,"Game")) is expected

def test_executable_ranking_keeps_priority(tmp_path):
    game=put(tmp_path,"Example.exe")
    other=put(tmp_path,"Other.exe")
    deeper=put(tmp_path,"a/b/Unrelated.exe")
    put(tmp_path,"setup.exe")
    assert launch.executable_candidates(tmp_path,"Example")==[game,other,deeper]

def test_scan_early_exit_and_stat_counts(tmp_path,monkeypatch):
    put(tmp_path,"Game.exe")
    for i in range(40):
        put(tmp_path,f"folder-{i}/other.exe")
    original_walk=launch.os.walk
    original_stat=Path.stat
    counts={"directories":0,"exe_stats":0}
    def counted_walk(*args,**kwargs):
        for row in original_walk(*args,**kwargs):
            counts["directories"]+=1
            yield row
    def counted_stat(path,*args,**kwargs):
        if path.suffix.casefold()==".exe":
            counts["exe_stats"]+=1
        return original_stat(path,*args,**kwargs)
    monkeypatch.setattr(launch.os,"walk",counted_walk)
    monkeypatch.setattr(Path,"stat",counted_stat)
    assert len(launch.executable_candidates(tmp_path,"Game"))==41
    old=counts.copy()
    counts.update(directories=0,exe_stats=0)
    assert launch.has_executable_candidate(tmp_path)
    new=counts.copy()
    assert old=={"directories":41,"exe_stats":41}
    assert new=={"directories":1,"exe_stats":0}
    print("DISCOVERY_DIRECTORIES 41 -> 1; EXE_SIZE_STATS 41 -> 0")

def test_library_scan_results_match_ranked_discovery(tmp_path,monkeypatch):
    root=tmp_path/"installed";root.mkdir()
    archives=tmp_path/"archives";archives.mkdir()
    lib=library.Library(tmp_path/"data")
    lib.change_root(root)
    lib.change_archive_root(archives)
    for i in range(25):
        name=f"Game {i:02}"
        put(root,f"{name}/{name}.exe")
        for j in range(5):
            put(root,f"{name}/extra-{j}/other.exe")
        if i%2:
            (archives/f"{name}.zip").write_bytes(b"archive")
    put(root,"Not Game/setup.exe")
    put(root,"Not Game/redist/game.exe")
    (archives/"Archive Only.7z").write_bytes(b"archive")
    def snapshot(games):
        return [(g.id,g.name,g.archive,g.folder,g.external) for g in games]
    new_discovery=library.has_executable_candidate
    monkeypatch.setattr(library,"has_executable_candidate",lambda folder:bool(launch.executable_candidates(folder,folder.name)))
    start=perf_counter()
    expected=snapshot(lib.scan())
    old_time=perf_counter()-start
    monkeypatch.setattr(library,"has_executable_candidate",new_discovery)
    start=perf_counter()
    actual=snapshot(lib.scan())
    new_time=perf_counter()-start
    assert actual==expected
    assert len(actual)==26
    print(f"SYNTHETIC_SCAN_25_FOLDERS baseline={old_time:.6f}s optimized={new_time:.6f}s")

def test_configured_roots_do_not_probe_default_folders(tmp_path,monkeypatch):
    lib=library.Library(tmp_path/"data")
    root=tmp_path/"installed"
    archives=tmp_path/"archives"
    lib.settings.update(library=str(root),archives=str(archives))
    def unexpected():
        raise AssertionError("configured path should not probe default folders")
    monkeypatch.setattr(library,"default_library",unexpected)
    assert lib.root==root
    assert lib.archive_root==archives
    del lib.settings["archives"]
    assert lib.archive_root==root
