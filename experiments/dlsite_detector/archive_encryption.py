"""압축파일 암호 상태만 확인하는 보수적 사전 검사.

암호화된 파일은 게임 정체 판단에 **오직 압축파일 자체의 이름**을 사용한다.
ZIP 중앙 디렉터리는 암호 플래그만 읽으며 멤버명/내용을 단서로 반환하지 않는다.
7z/RAR 역시 헤더의 암호 여부만 확인한다. 실패하면 안전하게 unknown 처리.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import zipfile


@dataclass(frozen=True)
class EncryptionProbe:
    state: str  # clear / encrypted / unknown
    reason: str

    @property
    def is_encrypted(self) -> bool:
        return self.state == "encrypted"


def probe_archive_encryption(path: Path) -> EncryptionProbe:
    archive = Path(path)
    if not archive.is_file() or archive.is_symlink():
        return EncryptionProbe("unknown", "유효한 로컬 일반 파일이 아닙니다.")
    suffix = archive.suffix.casefold()
    try:
        if suffix == ".zip":
            with zipfile.ZipFile(archive) as zf:
                # 이름은 결코 읽거나 검색 후보로 반환하지 않는다.
                encrypted = any(
                    bool(entry.flag_bits & 1) or entry.compress_type == 99
                    for entry in zf.infolist()
                )
            return EncryptionProbe(
                "encrypted" if encrypted else "clear",
                "ZIP 내부 항목의 암호화 플래그 감지" if encrypted
                else "ZIP 항목 암호화 플래그가 없습니다.",
            )
        if suffix == ".7z":
            import py7zr
            with py7zr.SevenZipFile(archive, mode="r") as zf:
                encrypted = bool(zf.needs_password())
            return EncryptionProbe(
                "encrypted" if encrypted else "clear",
                "7z 헤더 또는 압축 데이터 암호화 감지" if encrypted
                else "7z 비밀번호 필요 표시가 없습니다.",
            )
        if suffix == ".rar":
            import rarfile
            with rarfile.RarFile(archive) as zf:
                encrypted = bool(zf.needs_password())
            return EncryptionProbe(
                "encrypted" if encrypted else "clear",
                "RAR 암호화 플래그 감지" if encrypted
                else "RAR 비밀번호 필요 표시가 없습니다.",
            )
        return EncryptionProbe("unknown", "지원하지 않는 압축 형식입니다.")
    except Exception as exc:
        # 비밀번호 보호된 헤더는 라이브러리에 따라 헤더 열기부터 실패한다.
        # 상태가 확실하지 않으면 이름만 검색하고 내부 분석은 생략한다.
        detail = str(exc).lower()
        if any(word in detail for word in (
            "password", "encrypted", "encryption", "wrong password",
            "bad password", "암호", "비밀번호",
        )):
            return EncryptionProbe("encrypted", "암호 보호된 헤더를 열 수 없습니다.")
        return EncryptionProbe(
            "unknown", f"암호화 여부를 안전하게 확인할 수 없습니다: {type(exc).__name__}",
        )
