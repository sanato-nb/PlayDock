from pathlib import Path
import pytest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import Library, install


def test_7z_install_if_py7zr_available(tmp_path):
    py7zr = pytest.importorskip("py7zr")
    root = tmp_path / "game"
    root.mkdir()
    source = tmp_path / "source"
    source.mkdir()
    (source / "Hello.exe").write_bytes(b"MZ\0")
    archives = tmp_path / "archives"
    archives.mkdir()
    archive = archives / "Example.7z"
    with py7zr.SevenZipFile(archive, "w") as writer:
        writer.writeall(source, arcname="Example")
    library = Library(tmp_path / "config")
    library.change_root(root)
    library.change_archive_root(archives)
    installed = install(library.scan()[0])
    assert (installed / "Hello.exe").is_file()
