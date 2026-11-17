"""암호화된 아카이브는 파일명만 조회하며 내부 어떤 단서도 사용하지 않는다."""
from __future__ import annotations

from io import BytesIO
import json
import struct
import sys
import types
import zipfile

import pytest

from experiments.dlsite_detector.archive_encryption import probe_archive_encryption
from experiments.dlsite_detector.archive_identity import identify_archive
from experiments.dlsite_detector.archive_inspector import inspect_archive
from experiments.dlsite_detector.internal_metadata import inspect_metadata
from experiments.dlsite_detector.pipeline import SearchDecision
from experiments.dlsite_detector import identify_cli


def archive_with_zip_encryption_flag(tmp_path):
    """암호를 풀거나 구현하지 않고 ZIP 헤더의 암호 플래그를 재현한 테스트 픽스처."""
    archive = tmp_path / "Unknown [한글패치].zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("Public/README.txt", "Title: Public Game\n")
        z.writestr("Private/secret_Game.ini", "Title=Secret Game\n")
        z.writestr("Private/Secret Game.exe", b"FAKE EXECUTABLE")
    raw = bytearray(archive.read_bytes())
    # 두 번째 ZIP 멤버만 암호화 플래그로 지정. ZIP 콘텐츠는 실제로
    # 암호화하지 않았으므로 디스크에서 열거나 실행해서는 안 된다.
    local_sig = b"PK\x03\x04"
    central_sig = b"PK\x01\x02"
    for marker, offset in ((local_sig, 6), (central_sig, 8)):
        cursor = 0
        found = []
        while True:
            idx = raw.find(marker, cursor)
            if idx < 0:
                break
            found.append(idx)
            cursor = idx + 4
        assert len(found) == 3
        index = found[1]
        old = struct.unpack_from("<H", raw, index + offset)[0]
        struct.pack_into("<H", raw, index + offset, old | 1)
    archive.write_bytes(raw)
    return archive


def absent(title):
    return SearchDecision("lookup_unavailable", title, reason="모의 파일명 검색 실패")


def candidate(title):
    return SearchDecision("internet_candidate", title, proposed_title="Night of Revenge")


def confirmed(title):
    return SearchDecision("confirmed_game", title, proposed_title="Night of Revenge",
                          dlsite_code="RJ405582")


def test_zip_any_member_encrypted_even_when_others_are_clear(tmp_path):
    path = archive_with_zip_encryption_flag(tmp_path)
    assert probe_archive_encryption(path).state == "encrypted"
    inspect = inspect_archive(path)
    meta = inspect_metadata(path)
    assert inspect.encrypted is True and inspect.state == "encrypted"
    assert inspect.title_candidates == ()
    assert inspect.product_codes == ()
    assert inspect.evidence == ()
    assert inspect.localization_signals == ()
    assert meta.state == "encrypted"
    assert meta.title_candidates == () and meta.read_bytes == 0


@pytest.mark.parametrize("metadata", (False, True))
def test_encrypted_zip_name_failure_is_unclassifiable_and_never_reads_members(
    tmp_path, metadata, monkeypatch,
):
    archive = archive_with_zip_encryption_flag(tmp_path)
    called = []
    def classifier(query):
        called.append(query)
        return absent(query)
    monkeypatch.setattr(zipfile.ZipFile, "open", lambda *_: pytest.fail("encrypted member open forbidden"))
    monkeypatch.setattr(zipfile.ZipFile, "extract", lambda *_: pytest.fail("unzip forbidden"))
    monkeypatch.setattr(zipfile.ZipFile, "extractall", lambda *_: pytest.fail("unzip forbidden"))
    out = identify_archive(
        archive, classifier=classifier, allow_metadata=metadata,
        inspector=lambda _: pytest.fail("never read encrypted index for identity"),
        metadata_reader=lambda _: pytest.fail("never read encrypted contents"),
    )
    assert out.status == "unclassifiable"
    assert out.label.startswith("분류 불가")
    assert out.stage == 1
    assert out.inspection is None and out.metadata is None
    assert out.to_dict()["status"] == "unclassifiable"
    assert called == [archive.stem]


def test_encrypted_zip_name_candidate_still_kept_without_metadata(tmp_path):
    archive = archive_with_zip_encryption_flag(tmp_path)
    result = identify_archive(
        archive, classifier=candidate, allow_metadata=True,
        inspector=lambda _: pytest.fail("no encrypted index for identity"),
        metadata_reader=lambda _: pytest.fail("no encrypted metadata"),
    )
    assert result.stage == 1
    assert result.status == "candidate_found"
    assert result.proposed_title == "Night of Revenge"
    assert result.inspection is None


def test_encrypted_zip_name_confirmed_still_works(tmp_path):
    archive = archive_with_zip_encryption_flag(tmp_path)
    result = identify_archive(
        archive, classifier=confirmed, allow_metadata=True,
        inspector=lambda _: pytest.fail("no index"),
        metadata_reader=lambda _: pytest.fail("no metadata"),
    )
    assert result.status == "confirmed_game"
    assert result.stage == 1


def test_rar_password_flag_is_detected_without_listing(tmp_path, monkeypatch):
    archive = tmp_path / "Unknown.rar"
    archive.write_bytes(b"RAR TEST FILE")
    class FakeRar:
        def __init__(self, path):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def needs_password(self):
            return True
        def infolist(self):
            pytest.fail("RAR file list is private")
    monkeypatch.setitem(sys.modules, "rarfile", types.SimpleNamespace(RarFile=FakeRar))
    result = identify_archive(
        archive, classifier=absent, allow_metadata=True,
        inspector=lambda _: pytest.fail("no RAR list"),
        metadata_reader=lambda _: pytest.fail("no RAR content"),
    )
    assert result.status == "unclassifiable"
    assert probe_archive_encryption(archive).is_encrypted


def test_7z_password_flag_is_detected_without_listing(tmp_path, monkeypatch):
    archive = tmp_path / "Unknown.7z"
    archive.write_bytes(b"7z TEST FILE")
    class FakeSeven:
        def __init__(self, path, mode):
            assert mode == "r"
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def needs_password(self):
            return True
        def list(self):
            pytest.fail("7z member list must never be read")
    monkeypatch.setitem(sys.modules, "py7zr", types.SimpleNamespace(SevenZipFile=FakeSeven))
    assert probe_archive_encryption(archive).state == "encrypted"
    out = identify_archive(archive, classifier=absent, allow_metadata=True,
                           inspector=lambda _: pytest.fail("no index"))
    assert out.status == "unclassifiable" and out.stage == 1


def test_encrypted_header_read_error_is_treated_as_encrypted(tmp_path, monkeypatch):
    archive = tmp_path / "Hidden.7z"
    archive.write_bytes(b"test")
    class Locked:
        def __init__(self, path, mode):
            raise ValueError("encrypted header: password required")
    monkeypatch.setitem(sys.modules, "py7zr", types.SimpleNamespace(SevenZipFile=Locked))
    assert probe_archive_encryption(archive).state == "encrypted"
    assert identify_archive(archive, classifier=absent).status == "unclassifiable"


def test_undetermined_encryption_does_not_read_archive_content(tmp_path, monkeypatch):
    path = tmp_path / "Corrupt.zip"
    path.write_bytes(b"not a zip")
    assert probe_archive_encryption(path).state == "unknown"
    out = identify_archive(
        path, classifier=absent, allow_metadata=True,
        inspector=lambda _: pytest.fail("unknown encryption must not inspect"),
        metadata_reader=lambda _: pytest.fail("unknown encryption must not read"),
    )
    assert out.status == "lookup_unavailable"
    assert out.inspection.state == "unavailable"


def test_unencrypted_zip_still_falls_back_to_member_names(tmp_path):
    path = tmp_path / "Unknown.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Actual Story/Actual Story.exe", b"placeholder")
    called = []
    def classifier(query):
        called.append(query)
        return candidate(query) if query == "Actual Story" else absent(query)
    out = identify_archive(path, classifier=classifier, allow_metadata=True)
    assert out.status == "candidate_found" and out.stage == 2
    assert called == ["Unknown", "Actual Story"]


def test_offline_cli_reports_encrypted_without_exposing_members(tmp_path, capsys):
    archive = archive_with_zip_encryption_flag(tmp_path)
    assert identify_cli.main([str(archive), "--metadata", "--json"]) != 0
    out = json.loads(capsys.readouterr().out)
    assert out["state"] == "encrypted"
    assert out["metadata"]["state"] == "encrypted"
    assert out["title_candidates"] == []
    assert out["product_codes"] == []
