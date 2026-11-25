"""Local image discovery inspects each candidate once without changing scores."""
from io import BytesIO

from PIL import Image

import artwork
from core import Game, Library


def test_discovery_reuses_dimensions_and_preserves_candidate_priority(tmp_path, monkeypatch):
    library = Library(tmp_path / "data")
    game = Game("example", "Example", tmp_path)
    folder = tmp_path / "artwork_library"
    folder.mkdir()
    supplied = folder / "banner.png"
    local = tmp_path / "icon.png"
    invalid = tmp_path / "broken.png"
    Image.new("RGB", (800, 400), "red").save(supplied)
    Image.new("RGB", (128, 128), "blue").save(local)
    invalid.write_bytes(b"not an image")
    buffer = BytesIO()
    Image.new("RGB", (128, 128), "green").save(buffer, "PNG")
    embedded = buffer.getvalue()
    monkeypatch.setattr(artwork, "_find_artwork_library", lambda *_: [supplied, local, invalid])
    monkeypatch.setattr(artwork, "_archive_artwork_candidates", lambda *_: [("cover.png", embedded)])

    real_open = Image.open
    inspected = []
    saved = []

    def counted(source, *args, **kwargs):
        inspected.append(source)
        return real_open(source, *args, **kwargs)

    def save(source, target, kind):
        saved.append((source.getvalue() if isinstance(source, BytesIO) else source, kind))
        target.write_bytes(b"cached result")

    monkeypatch.setattr(artwork.Image, "open", counted)
    monkeypatch.setattr(artwork, "save_image", save)
    assert artwork.discover_local(library, game) == ["hero", "icon"]
    assert len(inspected) == 4
    # Preserve the original floating-point score order: the archive bonus
    # is added in two steps and is slightly larger than the local score.
    assert 128 * 128 / 1_000_000 + 5 + 20 > 128 * 128 / 1_000_000 + 25
    assert saved == [(supplied, "hero"), (embedded, "icon")]
    assert artwork.discover_local(library, game) == []
    assert len(inspected) == 4
    assert len(saved) == 2

    # Existing banner remains untouched if only the icon is missing.
    dest = library.art_dir(game)
    (dest / "hero.png").write_bytes(b"user banner")
    (dest / "icon.png").unlink()
    assert artwork.discover_local(library, game) == ["icon"]
    assert len(inspected) == 8
    assert saved[-1] == (embedded, "icon")
    assert (dest / "hero.png").read_bytes() == b"user banner"
