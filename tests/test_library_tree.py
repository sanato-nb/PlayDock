from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from types import SimpleNamespace
from models.library_tree import make_sidebar_groups


def game(name, installed=False):
    return SimpleNamespace(id=name.casefold(), name=name, installed=installed)


def test_uncategorized_and_duplicate_memberships():
    games = [game('Alpha'), game('Beta'), game('Gamma')]
    cols = [dict(id='rpg', name='RPG', game_ids=[games[0].id, games[1].id]),
            dict(id='favorite', name='즐겨찾기', game_ids=[games[0].id])]
    groups = make_sidebar_groups(games, cols, lambda g:g.name)
    assert [x.title for x in groups] == ['RPG', '즐겨찾기', '미분류']
    assert [[g.name for g in group.games] for group in groups] == [['Alpha', 'Beta'], ['Alpha'], ['Gamma']]


def test_filter_and_search():
    games = [game('A Game', True), game('B Game'), game('Third', True)]
    col = [dict(id='rpg', name='RPG', game_ids=[g.id for g in games])]
    assert [g.name for g in make_sidebar_groups(games,col,lambda g:g.name,'installed','game')[0].games] == ['A Game']
    assert [g.name for g in make_sidebar_groups(games,col,lambda g:g.name,'uninstalled','game')[0].games] == ['B Game']
    assert make_sidebar_groups(games,col,lambda g:g.name,'all','NO_MATCH') == []


def test_empty_custom_group_kept_without_search():
    cols = [dict(id='empty', name='빈 모음집', game_ids=[])]
    groups = make_sidebar_groups([], cols, lambda g:g.name)
    assert [g.title for g in groups] == ['빈 모음집', '미분류']
    assert all(not g.games for g in groups)
