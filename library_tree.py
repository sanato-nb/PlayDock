"""Pure view model for the Steam-like expandable sidebar.

The tree never changes files and remains usable without a Qt runtime. A game
may occur in several named collections, but uncategorized shows it only once.
"""
from __future__ import annotations

from dataclasses import dataclass


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
    filtered = [g for g in games
                if (filter_mode == 'all' or g.installed == (filter_mode == 'installed'))
                and all(term in (title_of(g) + ' ' + g.name).casefold() for term in words)]
    if sort_mode == 'name':
        filtered.sort(key=lambda g: title_of(g).casefold())
    elif sort_mode == 'name_desc':
        filtered.sort(key=lambda g: title_of(g).casefold(), reverse=True)
    elif sort_mode == 'installed':
        filtered.sort(key=lambda g: (not g.installed, title_of(g).casefold()))
    elif sort_mode == 'archive_size':
        def size(g):
            try:
                return g.archive.stat().st_size if g.archive else 0
            except OSError:
                return 0
        filtered.sort(key=lambda g: (-size(g), title_of(g).casefold()))
    else:
        raise ValueError('알 수 없는 정렬 옵션입니다.')
    grouped_ids = set()
    results = []
    for col in collections:
        member_ids = set(col['game_ids'])
        grouped_ids.update(member_ids)
        matched = tuple(g for g in filtered if g.id in member_ids)
        # Keep empty custom collections visible until an active search hides them.
        if matched or not search.strip():
            results.append(SidebarGroup(col['id'], col['name'], matched))
    uncategorized = tuple(g for g in filtered if g.id not in grouped_ids)
    if uncategorized or not search.strip():
        results.append(SidebarGroup('__uncategorized__', '미분류', uncategorized))
    return results
