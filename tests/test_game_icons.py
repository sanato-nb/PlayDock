from refactor_test_support import launcher_source, editor_source

from pathlib import Path
_ui_main = launcher_source()
from io import BytesIO

from PIL import Image

from ui.widgets.game_icons import normalized_icon_png, game_art_icon


def _image_from_png(blob: bytes):
    return Image.open(BytesIO(blob)).convert('RGBA')


def test_tiny_centered_icon_is_expanded_to_consistent_size(tmp_path: Path):
    src = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    src.paste(Image.new('RGBA', (16, 16), (255, 20, 20, 255)), (120, 120))
    path = tmp_path / 'tiny.png'
    src.save(path)
    output = _image_from_png(normalized_icon_png(path))
    bbox = output.getchannel('A').getbbox()
    assert output.size == (96, 96)
    assert bbox is not None
    assert bbox[2] - bbox[0] >= 80
    assert bbox[3] - bbox[1] >= 80


def test_regular_icon_is_not_distorted(tmp_path: Path):
    image = Image.new('RGBA', (32, 64), (50, 90, 200, 255))
    path = tmp_path / 'narrow.png'
    image.save(path)
    output = _image_from_png(normalized_icon_png(path))
    bbox = output.getchannel('A').getbbox()
    assert bbox is not None
    width, height = bbox[2] - bbox[0], bbox[3] - bbox[1]
    assert height > width
    assert abs(width / height - 0.5) < .06


def test_opaque_art_is_preserved(tmp_path: Path):
    path = tmp_path / 'opaque.png'
    Image.new('RGB', (48, 48), '#123456').save(path)
    output = _image_from_png(normalized_icon_png(path))
    assert output.getpixel((48, 48)) == (18, 52, 86, 255)


def test_original_icon_cache_is_not_modified(tmp_path: Path):
    path = tmp_path / 'icon.png'
    Image.new('RGBA', (256, 256), (0, 0, 0, 0)).save(path)
    before = path.read_bytes()
    normalized_icon_png(path)
    assert path.read_bytes() == before


def test_missing_icon_returns_fallback_without_qt(tmp_path: Path):
    sentinel = object()
    assert game_art_icon(tmp_path / 'absent.png', sentinel) is sentinel


def test_sidebar_uses_normalized_icon_for_both_paths():
    app = (Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8') + _ui_main
    assert 'self.tree.setIconSize(QSize(22, 22))' in app
    assert 'item.setIcon(0, game_art_icon(art, game_placeholder_icon()))' in app
    assert 'current_item.setIcon(0, game_art_icon(art_file, game_placeholder_icon()))' in app
