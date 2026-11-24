from refactor_test_support import launcher_source, editor_source
"""0.6.8 regression: optional product codes + physical mouse-pan math."""
from pathlib import Path
_ui_editor = editor_source()


from io import BytesIO

from PIL import Image
import pytest

from core import Library
from game_codes import normalize_code, find_code, effective_product_code, title_with_code
from online_artwork import crop_pan_center, crop_png


def test_code_is_optional_and_never_generated_for_no_code():
    assert normalize_code('') == ''
    assert effective_product_code({}, 'PASEC v2.2566') == ''
    assert title_with_code('PASEC [v2.2566]', '') == 'PASEC [v2.2566]'
    with pytest.raises(ValueError):
        normalize_code('PASEC')


def test_code_is_appended_once_and_uppercased():
    assert title_with_code('게임 [한국어]', normalize_code(' rj01081508 ')) == '게임 [한국어] [RJ01081508]'
    assert title_with_code('게임 [RJ01081508]', 'RJ01081508') == '게임 [RJ01081508]'
    assert title_with_code('게임 [VJ123456]', 'RJ01081508') == '게임 [VJ123456]'
    assert find_code('Game [v1.01] RJ01081508') == 'RJ01081508'


def test_saved_code_is_distinct_from_user_title_and_does_not_rename_archive(tmp_path):
    archive_root = tmp_path / 'archives'
    archive_root.mkdir()
    archive = archive_root / 'PASEC_v2.2566.zip'
    archive.write_bytes(b'not extracted during this test')
    lib = Library(store=tmp_path / 'data')
    lib.settings['archives'] = str(archive_root)
    lib.settings['library'] = str(tmp_path / 'installed')
    game = lib.scan()[0]
    assert lib.title(game) == 'PASEC_v2.2566'
    lib.set_product_code(game, 'rj01081508')
    assert lib.meta(game)['product_code'] == 'RJ01081508'
    assert lib.base_title(game) == 'PASEC_v2.2566'
    assert lib.title(game) == 'PASEC_v2.2566 [RJ01081508]'
    assert archive.exists() and archive.name == 'PASEC_v2.2566.zip'
    assert len(lib.scan()) == 1
    lib.set_product_code(game, '')
    assert lib.title(game) == 'PASEC_v2.2566'
    assert lib.meta(game)['product_code'] == ''


def test_legacy_work_number_is_detected_but_explicit_no_code_wins(tmp_path):
    lib = Library(store=tmp_path / 'data')
    (tmp_path / 'archives').mkdir()
    (tmp_path / 'archives' / 'Game [RJ01081508].7z').touch()
    lib.settings['archives'] = str(tmp_path / 'archives')
    lib.settings['library'] = str(tmp_path / 'installed')
    game = lib.scan()[0]
    assert lib.product_code(game) == 'RJ01081508'
    lib.set_product_code(game, '')
    assert lib.product_code(game) == ''


def test_drag_moving_image_right_moves_crop_left():
    # 900x450 landscape -> 1:1 icon crop with horizontal room
    x, y = crop_pan_center((900, 450), 'icon', 50, 50, 100, 48, 0, (256,256))
    assert x < 50 and y == 50
    x2, y2 = crop_pan_center((900,450), 'icon', x,y,100,-48,0,(256,256))
    assert abs(x2-50) < .001 and y2 == 50


def test_zoom_enables_pan_even_when_original_image_ratio_matches_crop():
    x, y = crop_pan_center((1600,520), 'hero', 50,50,100,60,30,(640,208))
    assert (x, y) == (50,50)
    x, y = crop_pan_center((1600,520), 'hero', 50,50,150,60,30,(640,208))
    assert x < 50 and y < 50


def test_zoomed_crop_moves_pixel_content():
    img = Image.new('RGB', (300,300))
    for x in range(300):
        for y in range(300):
            img.putpixel((x,y), (x%256, y%256, 12))
    raw = BytesIO(); img.save(raw,format='PNG')
    left = Image.open(BytesIO(crop_png(raw.getvalue(),'icon',0,50,zoom=150)))
    right = Image.open(BytesIO(crop_png(raw.getvalue(),'icon',100,50,zoom=150)))
    assert left.getpixel((128,128))[0] < right.getpixel((128,128))[0]


def test_dialog_and_editor_have_separate_code_input_and_drag_preview():
    root = Path(__file__).resolve().parents[1]
    dialog = (root / 'ui/artwork_dialog.py').read_text(encoding='utf-8')
    editor = (root / 'title_editor.py').read_text(encoding='utf-8') + _ui_editor
    assert 'class DragCropPreview(QLabel):' in dialog
    assert 'self.preview.dragged.connect(self.drag_image)' in dialog
    assert 'self.library.set_product_code(self.game, code)' in dialog
    assert "self.search()" in dialog
    assert "self.code_save_btn.clicked.connect(self.save_code)" in editor
    assert 'product_code=code' in editor
