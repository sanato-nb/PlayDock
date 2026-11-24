"""Reproducible local-only benchmark, executed independently per source revision."""
from pathlib import Path
import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter
from contextlib import contextmanager

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    root=args.source.resolve()
    sys.path[:0]=[str(root/"src/playdock"),str(root)]
    from core import Game, Library
    from work_db import WorkDatabase
    try:
        from models.library_tree import make_sidebar_groups
    except ModuleNotFoundError:
        from library_tree import make_sidebar_groups
    from PIL import Image
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QPixmap, QPixmapCache
    from PySide6.QtCore import qVersion
    from ui.collection_board import ArtworkTile
    qt=QApplication.instance() or QApplication([])
    result={"commit":subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip(),
            "python":sys.version.split()[0],"os":platform.platform(),"qt":qVersion(),
            "measurements":{}}
    def measure(name, fn, signature, repeats=5):
        warm=fn()
        expected=signature(warm)
        times=[]
        for _ in range(repeats):
            start=time.perf_counter()
            value=fn()
            times.append((time.perf_counter()-start)*1000)
            assert signature(value)==expected, name
        result["measurements"][name]={"median_ms":statistics.median(times),"samples_ms":times,
                                       "digest":hashlib.sha256(json.dumps(expected,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}
        return warm
    with tempfile.TemporaryDirectory(prefix="playdock-bench-") as directory:
        tmp=Path(directory)
        lib=Library(tmp/"data")
        installed=tmp/"installed";installed.mkdir()
        archives=tmp/"archives";archives.mkdir()
        lib.change_root(installed);lib.change_archive_root(archives)
        for i in range(100):
            name=f"Game {i:04}"
            folder=installed/name;folder.mkdir()
            (folder/"Game.exe").write_bytes(b"MZ")
            for j in range(8):
                child=folder/f"extra-{j}";child.mkdir()
                (child/"Other.exe").write_bytes(b"MZ")
            (archives/(name+".zip")).write_bytes(b"test")
        for i in range(100,1000):
            (archives/f"Game {i:04}.zip").write_bytes(b"test")
        games=measure("scan_1000_archives_100_installed",lib.scan,
                      lambda games:[(g.key,g.name,bool(g.archive),bool(g.folder)) for g in games])
        for i,g in enumerate(games):
            lib.update_meta(g,title=f"Localized Game {i:04}",prefer_manual_title=True)
        calls=Counter()
        original=lib.meta
        def counted(game):
            calls["meta"]+=1
            return original(game)
        lib.meta=counted
        measure("titles_1000",lambda:[lib.title(g) for g in games],lambda rows:rows)
        calls.clear()
        [lib.title(g) for g in games]
        result["title_meta_reads"]=calls["meta"]
        cols=[{"id":str(i),"name":str(i),"game_ids":[g.id for g in games[i*20:i*20+60]]} for i in range(50)]
        measure("sidebar_1000_50_collections",lambda:make_sidebar_groups(games,cols,lib.title,"all","localized game","name"),
                lambda groups:[(g.id,g.title,[x.key for x in g.games]) for g in groups])
        db=WorkDatabase(lib.store)
        url="https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"
        db._upsert_verified([{"store":"dlsite","code":"RJ123456","title":"Official Title","page_url":url}])
        ids=[g.id for g in games]
        with db.connect() as con:
            con.executemany("INSERT INTO library_links(game_id,store,code) VALUES(?,?,?)",[(gid,"dlsite","RJ123456") for gid in ids])
        counts=Counter()
        original_connect=db.connect
        @contextmanager
        def counted_connect():
            counts["connections"]+=1
            with original_connect() as con:
                con.set_trace_callback(lambda sql:counts.update(["selects"]) if sql.lstrip().upper().startswith(("SELECT","WITH")) else None)
                yield con
        db.connect=counted_connect
        def read():
            if hasattr(db,"get_linked_official_works"):
                return db.get_linked_official_works(ids)
            return {gid:db.get_official_work(*db.get_link(gid)) for gid in ids}
        # IDs depend on temp paths; compare portable title values in input order.
        measure("official_preflight_1000",read,lambda rows:[(rows[k]["store"],rows[k]["code"],rows[k]["title"]) for k in ids],repeats=3)
        counts.clear()
        read()
        result["db_reads"]=dict(counts)
        art=tmp/"hero.png";Image.new("RGB",(1600,520),"#2468ac").save(art)
        def card():
            return ArtworkTile("Game","", [art])
        def card_signature(tile):
            p=tile.artwork[0]
            color=p.toImage().pixelColor(p.width()//2,p.height()//2)
            return [color.red(),color.green(),color.blue()]
        tile=measure("card_warm_load",card,card_signature)
        result["card_pixels"]=[tile.artwork[0].width(),tile.artwork[0].height()]
        result["card_rgba_bytes_estimate"]=tile.artwork[0].width()*tile.artwork[0].height()*4
        def cold_card():
            QPixmapCache.clear()
            return card()
        measure("card_cold_load",cold_card,card_signature)
        # No persistent user storage and no internet requests.
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))

if __name__=="__main__":
    main()
