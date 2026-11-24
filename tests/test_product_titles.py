from datetime import datetime, timezone
from pathlib import Path
import json

from core import Game, Library
from product_titles import (
    extract_code, clean_title, display_title, _parse_response, lookup_title,
)


def test_detect_codes_in_names():
    assert extract_code('ㄹㄹㅌ의 메시아 [v25.08.01] [수정2] [RJ01373814]') == 'RJ01373814'
    assert extract_code('RJ405582 Night of Revenge.zip') == 'RJ405582'
    assert extract_code('게임 설명', 'RJ01710819.zip') == 'RJ01710819'
    assert extract_code('IRC01373814 pretend') is None
    assert extract_code('RJ12345') is None


def test_keep_version_and_revision_and_work_code():
    original = 'ㄹㄹㅌ의 메시아 [v25.08.01] [수정2] [RJ01373814]'
    actual = display_title('확인된 작품명', original, 'RJ01373814')
    assert actual == '확인된 작품명 [v25.08.01] [수정2] [RJ01373814]'
    assert actual.count('RJ01373814') == 1


def test_bad_titles():
    assert clean_title('*****') is None
    assert clean_title('<html>bad</html>') is None
    assert clean_title('') is None


def test_parse_response_accepts_matching_product_only():
    data = [{'workno': 'RJ01234567', 'work_name': '엉뚱한 작품'},
            {'workno': 'RJ01373814', 'work_name': '확인된 제목'}]
    assert _parse_response(data, 'RJ01373814') == '확인된 제목'
    assert _parse_response({'workno': 'RJ01234567', 'work_name': '다른 것'}, 'RJ01373814') is None
    assert _parse_response({'work_name': '식별 번호 없는 제목'}, 'RJ01373814') is None


def test_lookup_cache_reuses_confirmed_online_result(tmp_path):
    cache_file = tmp_path / 'titles.json'
    calls = []
    def fake_fetch(code):
        calls.append(code)
        return '정확한 작품명', 'https://www.dlsite.com/soft/api/product.json'
    title, source = lookup_title('RJ01234567', cache_file, fetcher=fake_fetch)
    assert title == '정확한 작품명'
    title2, source2 = lookup_title('RJ01234567', cache_file,
                                   fetcher=lambda code: (_ for _ in ()).throw(Exception('should not call')))
    assert title2 == title and source2 == source
    assert calls == ['RJ01234567']


def test_lookup_does_not_guess_unresolved_titles(tmp_path):
    try:
        lookup_title('RJ01234567', tmp_path / 'cache.json', fetcher=lambda code: None)
    except LookupError:
        pass
    else:
        raise AssertionError('unverified title should not be accepted')


def test_known_code_works_without_paid_api_or_network(tmp_path):
    title, source = lookup_title('RJ01373814', tmp_path / 'cache.json',
                                  fetcher=lambda code: (_ for _ in ()).throw(Exception('must not call')))
    assert '메시아 오브 로리타' == title
    assert '로컬' in source


def test_meta_display_name_does_not_rename_archive(tmp_path):
    root = tmp_path / 'installs'; root.mkdir()
    archive_dir = tmp_path / 'archives'; archive_dir.mkdir()
    archive = archive_dir / 'RJ01373814_name.zip'
    archive.write_bytes(b'unchanged')
    library = Library(store=tmp_path / 'appstore')
    g = Game(key='rj01373814_name', name='RJ01373814_name', root=root, archive=archive)
    library.update_meta(g, title='확인된 작품명 [RJ01373814]')
    assert library.title(g).startswith('확인된 작품명')
    assert archive.is_file() and archive.read_bytes() == b'unchanged'
