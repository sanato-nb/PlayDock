"""Measure title metadata reads and preserve sidebar/collection behavior."""
from collections import Counter
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from core import Game, Library
from models.library_tree import make_sidebar_groups
from services.localized_titles import localized_title_for
from models.game_codes import effective_product_code, title_with_code

def legacy_title(library, game):
    meta = library.meta(game)
    code = library.product_code(game)
    translated = localized_title_for(meta, library.settings, original_name=game.name, product_code=code)
    if meta.get("prefer_manual_title") is True and meta.get("title"):
        title = str(meta["title"])
    else:
        title = translated or str(meta.get("title") or game.name)
    return title_with_code(title, library.product_code(game))

@pytest.mark.parametrize("metadata", [
    {}, {"title":"Manual title","prefer_manual_title":True},
    {"localized_titles":{"ko":"한국어","en":"English"}},
    {"localized_titles":{"ja":"日本語"},"product_code":"RJ123456"},
    {"product_code":"","title":"Cleared code"},
    {"title":"Edited","product_code":"RJ654321"},
])
@pytest.mark.parametrize("lang", ["ko","en","ja"])
def test_title_snapshot_matches_previous_behavior(tmp_path,metadata,lang):
    lib=Library(tmp_path/"data")
    game=Game("g","Example [RJ123456] [v1.0]",tmp_path,archive=tmp_path/"Example [RJ123456] [v1.0].zip")
    lib.settings["title_language"]=lang
    lib.update_meta(game, **metadata)
    assert lib.title(game)==legacy_title(lib,game)

def test_title_reads_metadata_once_and_edits_are_immediate(tmp_path,monkeypatch):
    lib=Library(tmp_path/"data")
    game=Game("g","Example RJ123456",tmp_path)
    original=lib.meta
    calls=[]
    def counted(g):
        calls.append(g.key)
        return original(g)
    monkeypatch.setattr(lib,"meta",counted)
    expected=legacy_title(lib,game)
    assert len(calls)==3
    calls.clear()
    assert lib.title(game)==expected
    assert len(calls)==1
    print("TITLE_METADATA_READS 3 -> 1")
    # Separate instance simulates edits from the other title-editor window.
    other=Library(lib.store)
    other.update_meta(game,title="Edited",prefer_manual_title=True)
    assert lib.title(game).startswith("Edited")
    other.set_product_code(game,"")
    assert lib.title(game)=="Edited"

def old_groups(games, collections, title_of, filter_mode, search, sort_mode):
    words=search.casefold().strip().split()
    filtered=[g for g in games if (filter_mode=="all" or g.installed==(filter_mode=="installed"))
              and all(term in (title_of(g)+" "+g.name).casefold() for term in words)]
    if sort_mode=="name": filtered.sort(key=lambda g:title_of(g).casefold())
    elif sort_mode=="name_desc": filtered.sort(key=lambda g:title_of(g).casefold(),reverse=True)
    elif sort_mode=="installed": filtered.sort(key=lambda g:(not g.installed,title_of(g).casefold()))
    else:
        def size(g):
            try: return g.archive.stat().st_size if g.archive else 0
            except OSError: return 0
        filtered.sort(key=lambda g:(-size(g),title_of(g).casefold()))
    grouped=set()
    result=[]
    for col in collections:
        ids=set(col["game_ids"]); grouped.update(ids)
        matched=tuple(g.id for g in filtered if g.id in ids)
        if matched or not search.strip(): result.append((col["id"],col["name"],matched))
    uncategorized=tuple(g.id for g in filtered if g.id not in grouped)
    if uncategorized or not search.strip(): result.append(("__uncategorized__","미분류",uncategorized))
    return result

@pytest.mark.parametrize("sort_mode",["name","name_desc","installed","archive_size"])
@pytest.mark.parametrize("filter_mode",["all","installed","uninstalled"])
@pytest.mark.parametrize("search",["","alpha game","missing"])
def test_sidebar_search_and_sort_equivalence(tmp_path,sort_mode,filter_mode,search):
    games=[]
    for i,name in enumerate(["Alpha Game","Alpha Game","Beta","Gamma"]):
        archive=tmp_path/f"{i}.zip";archive.write_bytes(b"x"*(i+1))
        folder=tmp_path/f"installed-{i}" if i%2 else None
        if folder: folder.mkdir()
        games.append(Game(str(i),name,tmp_path,archive=archive,folder=folder))
    cols=[{"id":"rpg","name":"RPG","game_ids":[games[0].id,games[2].id]},
          {"id":"fav","name":"Fav","game_ids":[games[0].id,games[1].id]},
          {"id":"empty","name":"Empty","game_ids":[]}]
    title=lambda g:g.name
    expected=old_groups(games,cols,title,filter_mode,search,sort_mode)
    calls=Counter()
    def counted(g):
        calls[g.key]+=1
        return title(g)
    actual=make_sidebar_groups(games,cols,counted,filter_mode,search,sort_mode)
    assert [(r.id,r.title,tuple(g.id for g in r.games)) for r in actual]==expected
    assert all(n==1 for n in calls.values())

def test_real_sidebar_reuses_title_for_duplicate_collection_entries(tmp_path,monkeypatch):
    import app as application
    qt=QApplication.instance() or QApplication([])
    archives=tmp_path/"archives";archives.mkdir()
    installed=tmp_path/"installed";installed.mkdir()
    (archives/"Alpha Game.zip").write_bytes(b"archive")
    lib=Library(tmp_path/"data")
    lib.settings.update(archives=str(archives),library=str(installed))
    lib.save_settings()
    monkeypatch.setattr(application,"Library",lambda:lib)
    window=application.MainWindow()
    try:
        game=window.games[0]
        a=window.collections.create("A")
        b=window.collections.create("B")
        window.collections.set_game_memberships(game.id,{a,b})
        original=lib.title
        calls=[]
        def counted(g):
            calls.append(g.id)
            return original(g)
        monkeypatch.setattr(lib,"title",counted)
        # Isolate the sidebar from the separate selected-game detail renderer.
        monkeypatch.setattr(window,"present_game",lambda:None)
        window.search.blockSignals(True)
        window.search.setText("alpha game")
        window.search.blockSignals(False)
        window.populate_games(game.id)
        assert calls==[game.id]
        labels=[window.tree.topLevelItem(i).child(0).text(0)
                for i in range(window.tree.topLevelItemCount())
                if window.tree.topLevelItem(i).childCount()]
        assert labels==["Alpha Game","Alpha Game"]
        print("SIDEBAR_TWO_TERMS_TWO_COLLECTIONS_TITLE_CALLS 5 -> 1")
        calls.clear()
        lib.update_meta(game,title="Alpha Game Edited",prefer_manual_title=True)
        window.populate_games(game.id)
        assert calls==[game.id]
        assert all(window.tree.topLevelItem(i).child(0).text(0)=="Alpha Game Edited"
                   for i in range(window.tree.topLevelItemCount())
                   if window.tree.topLevelItem(i).childCount())
    finally:
        window.close()
