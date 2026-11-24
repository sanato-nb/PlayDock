"""Bounded artwork rendering cache: original files and refresh behavior."""
from pathlib import Path
import os

import pytest
from PIL import Image
from PySide6.QtGui import QPixmapCache, QIcon
from PySide6.QtWidgets import QApplication
from ui.widgets import artwork_cache as cache
from ui.widgets import game_icons as icons
from ui.widgets.launcher import Banner
from ui.collection_board import ArtworkTile

@pytest.fixture
def qt():
    app = QApplication.instance() or QApplication([])
    QPixmapCache.clear()
    yield app
    QPixmapCache.clear()

def put(path, color="red", size=(1600,520)):
    Image.new("RGB",size,color).save(path)
    return path

def test_tile_scaled_and_full_banner_unchanged(qt,tmp_path):
    path=put(tmp_path/"hero.png")
    before=path.read_bytes()
    thumbnail=cache.artwork_pixmap(path,max_edge=cache.TILE_MAX_EDGE)
    full=cache.artwork_pixmap(path)
    assert (full.width(),full.height())==(1600,520)
    assert (thumbnail.width(),thumbnail.height())==(768,250)
    assert thumbnail.toImage().pixelColor(100,100).red()==255
    tile=ArtworkTile("Game","", [path])
    assert tile.artwork[0].size()==thumbnail.size()
    banner=Banner()
    banner.set_game("Game","",path)
    assert banner.image.size()==full.size()
    assert path.read_bytes()==before
    print("TILE_PIXEL_BYTES_RGBA_ESTIMATE",1600*520*4,"->",768*250*4)

def test_cache_reuses_decode_and_replacement_refreshes(qt,tmp_path,monkeypatch):
    path=put(tmp_path/"hero.png")
    original=cache._read_pixmap
    calls=[]
    def counted(*args):
        calls.append(args)
        return original(*args)
    monkeypatch.setattr(cache,"_read_pixmap",counted)
    first=cache.artwork_pixmap(path,max_edge=cache.TILE_MAX_EDGE)
    second=cache.artwork_pixmap(path,max_edge=cache.TILE_MAX_EDGE)
    assert first.cacheKey()==second.cacheKey()
    assert len(calls)==1
    cache.artwork_pixmap(path)
    assert len(calls)==2  # distinct full-resolution variant
    revision=cache.file_revision(path)
    replacement=put(tmp_path/"new.png","blue")
    os.replace(replacement,path)
    os.utime(path,ns=(revision[1]+2_000_000_000,revision[1]+2_000_000_000))
    updated=cache.artwork_pixmap(path,max_edge=cache.TILE_MAX_EDGE)
    assert updated.toImage().pixelColor(100,100).blue()==255
    assert len(calls)==3
    path.unlink()
    assert cache.artwork_pixmap(path).isNull()
    assert cache.artwork_pixmap(path,max_edge=cache.TILE_MAX_EDGE).isNull()
    print("REPEATED_TILE_DECODE 2 -> 1; UPDATED_ART_REFRESHED")

def test_invalid_missing_and_fifth_fallback(qt,tmp_path,monkeypatch):
    bad=tmp_path/"bad.png";bad.write_bytes(b"invalid image")
    paths=[put(tmp_path/f"{i}.png",size=(256,256)) for i in range(5)]
    assert cache.artwork_pixmap(bad).isNull()
    assert cache.artwork_pixmap(None).isNull()
    assert cache.artwork_pixmap(tmp_path).isNull()
    tile=ArtworkTile("A","",[bad,*paths[:4]])
    assert len(tile.artwork)==4
    original=cache._read_pixmap
    calls=[]
    def counted(*args):
        calls.append(args)
        return original(*args)
    monkeypatch.setattr(cache,"_read_pixmap",counted)
    QPixmapCache.clear()
    tile2=ArtworkTile("B","",paths)
    assert len(tile2.artwork)==4
    assert len(calls)==4
    assert all(p.size().width()==256 for p in tile2.artwork)

def test_icon_pixmap_is_shared_and_missing_icon_falls_back(qt,tmp_path,monkeypatch):
    path=put(tmp_path/"icon.png",size=(256,256))
    fallback=QIcon()
    icons._cached_normalized_icon.cache_clear()
    original=icons.normalized_icon_png
    calls=[]
    def counted(*args):
        calls.append(args)
        return original(*args)
    monkeypatch.setattr(icons,"normalized_icon_png",counted)
    a=icons.game_art_icon(path,fallback)
    b=icons.game_art_icon(path,fallback)
    assert not a.isNull() and not b.isNull()
    assert len(calls)==1
    assert icons._cached_normalized_icon.cache_info().hits==0
    assert a.pixmap(96,96).toImage().pixelColor(48,48).red()==255
    path.unlink()
    assert icons.game_art_icon(path,fallback) is fallback

def test_cache_eviction_can_reload_without_changing_global_limit(qt,tmp_path):
    path=put(tmp_path/"hero.png")
    limit=QPixmapCache.cacheLimit()
    first=cache.artwork_pixmap(path,max_edge=cache.TILE_MAX_EDGE)
    QPixmapCache.clear()
    second=cache.artwork_pixmap(path,max_edge=cache.TILE_MAX_EDGE)
    assert first.size()==second.size()
    assert second.toImage().pixelColor(100,100).red()==255
    assert QPixmapCache.cacheLimit()==limit
