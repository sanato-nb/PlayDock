"""Verify indexed grouping preserves ordering and avoids repeated ID resolution."""
from collections import Counter
from time import perf_counter

import pytest
from models.collection_board import partition_collection_games, member_games
from models.library_tree import make_sidebar_groups

class CountedGame:
    def __init__(self, key, name=None, installed=False):
        self.key=key
        self.name=name or key
        self.installed=installed
        self.id_reads=0

    @property
    def id(self):
        self.id_reads+=1
        return self.key

def legacy_partition(games, collections):
    assigned=set()
    buckets=[]
    for row in collections:
        ids=set(row["game_ids"])
        assigned.update(ids)
        buckets.append([g for g in games if g.id in ids])
    return buckets,[g for g in games if g.id not in assigned]

def signature(result):
    buckets,unassigned=result
    return [[g.key for g in b] for b in buckets],[g.key for g in unassigned]

def test_indexed_partition_preserves_missing_duplicate_and_overlapping_ids():
    games=[CountedGame("b"),CountedGame("a"),CountedGame("a"),CountedGame("c")]
    cols=[
        {"id":"same","name":"A","game_ids":["gone","a","a","b"]},
        {"id":"same","name":"B","game_ids":["b"]},
        {"id":"empty","name":"C","game_ids":[]},
    ]
    expected=legacy_partition(games,cols)
    actual=partition_collection_games(games,cols)
    assert actual==expected
    assert signature(actual)==([["b","a","a"],["b"],[]],["c"])
    assert cols[0]["game_ids"]==["gone","a","a","b"]

@pytest.mark.parametrize("search",["","alpha","no result"])
@pytest.mark.parametrize("sort",["name","name_desc","installed"])
@pytest.mark.parametrize("filter_mode",["all","installed","uninstalled"])
def test_sidebar_order_and_visibility(search,sort,filter_mode):
    games=[CountedGame("b","Alpha",True),CountedGame("a","Alpha"),
           CountedGame("c","Beta",True),CountedGame("d","Gamma")]
    cols=[{"id":"x","name":"X","game_ids":["a","b","gone"]},
          {"id":"y","name":"Y","game_ids":["b","c"]},
          {"id":"empty","name":"Empty","game_ids":[]}]
    filtered=[g for g in games if (filter_mode=="all" or g.installed==(filter_mode=="installed"))
              and all(w in (g.name+" "+g.name).casefold() for w in search.casefold().split())]
    if sort=="installed":
        filtered.sort(key=lambda g:(not g.installed,g.name.casefold()))
    else:
        filtered.sort(key=lambda g:g.name.casefold(),reverse=sort=="name_desc")
    buckets,unassigned=legacy_partition(filtered,cols)
    expected=[(c["id"],c["name"],tuple(b)) for c,b in zip(cols,buckets) if b or not search.strip()]
    if unassigned or not search.strip():
        expected.append(("__uncategorized__","미분류",tuple(unassigned)))
    actual=make_sidebar_groups(games,cols,lambda g:g.name,filter_mode,search,sort)
    assert [(r.id,r.title,r.games) for r in actual]==expected

def test_5000_games_50_collections_single_pass():
    games=[CountedGame(f"g{i:05}") for i in range(5000)]
    cols=[{"id":str(j),"name":str(j),"game_ids":[f"g{i:05}" for i in range(j*70,j*70+100)]}
          for j in range(50)]
    start=perf_counter()
    old=legacy_partition(games,cols)
    old_elapsed=perf_counter()-start
    old_reads=sum(g.id_reads for g in games)
    for g in games:g.id_reads=0
    start=perf_counter()
    new=partition_collection_games(games,cols)
    new_elapsed=perf_counter()-start
    new_reads=sum(g.id_reads for g in games)
    assert new==old
    assert (old_reads,new_reads)==(255000,5000)
    print(f"GROUP_ID_READS {old_reads} -> {new_reads}; synthetic_seconds {old_elapsed:.6f} -> {new_elapsed:.6f}")
    for g in games:g.id_reads=0
    old_board=[member_games(games,row["game_ids"]) for row in cols]
    assert sum(g.id_reads for g in games)==250000
    for g in games:g.id_reads=0
    new_board,_=partition_collection_games(games,cols)
    assert new_board==old_board
    assert sum(g.id_reads for g in games)==5000
    print("BOARD_GROUP_ID_READS 250000 -> 5000")
