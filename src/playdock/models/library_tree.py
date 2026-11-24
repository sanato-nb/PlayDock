"""Pure view model for the Steam-like expandable sidebar.

The tree never changes files and remains usable without a Qt runtime. A game
may occur in several named collections, but uncategorized shows it only once.
"""
from __future__ import annotations

from dataclasses import dataclass
from models.collection_board import partition_collection_games


@dataclass(frozen=True)
class SidebarGroup:
    id: str
    title: str
    games: tuple


def make_sidebar_groups(games, collections, title_of, filter_mode='all', search='',
                        sort_mode='name', kind_of=None):
    if filter_mode not in ('all', 'installed', 'uninstalled'):
        raise ValueError('잘못된 필터입니다.')
    words = search.casefold().strip().split()
    # Compute a title once per eligible game, rather than for every search
    # term and again during sorting. Preserve stable input-order tie breaking.
    titles = {}
    filtered = []
    for g in games:
        if filter_mode != 'all' and g.installed != (filter_mode == 'installed'):
            continue
        key = id(g)
        if key not in titles:
            titles[key] = title_of(g).casefold()
        searchable = titles[key] + ' ' + g.name.casefold() if words else ''
        if all(term in searchable for term in words):
            filtered.append(g)
    if sort_mode == 'name':
        filtered.sort(key=lambda g: titles[id(g)])
    elif sort_mode == 'name_desc':
        filtered.sort(key=lambda g: titles[id(g)], reverse=True)
    elif sort_mode == 'installed':
        filtered.sort(key=lambda g: (not g.installed, titles[id(g)]))
    elif sort_mode == 'archive_size':
        def size(g):
            try:
                return g.archive.stat().st_size if g.archive else 0
            except OSError:
                return 0
        filtered.sort(key=lambda g: (-size(g), titles[id(g)]))
    else:
        raise ValueError('알 수 없는 정렬 옵션입니다.')
    collections = list(collections)
    buckets, unassigned = partition_collection_games(filtered, collections)
    results = []
    for col, members in zip(collections, buckets):
        matched = tuple(members)
        # Keep empty custom collections visible until an active search hides them.
        if matched or not search.strip():
            results.append(SidebarGroup(col['id'], col['name'], matched))
    uncategorized = tuple(unassigned)
    if uncategorized or not search.strip():
        results.append(SidebarGroup('__uncategorized__', '미분류', uncategorized))
    return results
