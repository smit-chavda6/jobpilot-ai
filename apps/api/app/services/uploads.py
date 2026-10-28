"""Hardened file upload validation and storage (spec §15).

Checks: extension allowlist, magic bytes, declared MIME, size cap, DOCX zip-bomb limits and
macro rejection, PDF active-content rejection. Files are stored under random keys outside the
web root and are never served directly.
"""

from __future__ import annotations

import hashlib
import io
import secrets
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.errors import UnprocessableError

ALLOWED = {
    ".pdf": {"application/pdf"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".txt": {"text/plain"},
}
GENERIC_MIMES = {"application/octet-stream", ""}
MAX_ZIP_ENTRIES = 500
MAX_ZIP_UNCOMPRESSED = 50 * 1024 * 1024
MAX_ZIP_RATIO = 100
PDF_ACTIVE_MARKERS = (b"/JavaScript", b"/JS ", b"/Launch", b"/EmbeddedFile", b"/OpenAction /JavaScript")


@dataclass
class ValidatedUpload:
    filename: str
    ext: str
    mime: str
    data: bytes
    sha256: str


def _reject(msg: str) -> UnprocessableError:
    return UnprocessableError(msg, code="upload_rejected")


def _check_docx(data: bytes) -> None:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise _reject("File is not a valid DOCX document") from exc
    infos = zf.infolist()
    if len(infos) > MAX_ZIP_ENTRIES:
        raise _reject("DOCX contains too many parts")
    total = sum(i.file_size for i in infos)
    compressed = sum(i.compress_size for i in infos) or 1
    if total > MAX_ZIP_UNCOMPRESSED or total / compressed > MAX_ZIP_RATIO:
        raise _reject("DOCX expands to an unsafe size (possible zip bomb)")
    names = {i.filename.lower() for i in infos}
    if "word/document.xml" not in names or "[content_types].xml" not in names:
        raise _reject("File is not a valid DOCX document")
    if any(n.endswith("vbaproject.bin") or n.endswith(".bin") and "vba" in n for n in names):
        raise _reject("Documents containing macros are not accepted")
    ct = zf.read("[Content_Types].xml").lower()
    if b"macroenabled" in ct or b"vbaproject" in ct:
        raise _reject("Documents containing macros are not accepted")


def validate_upload(filename: str, declared_mime: str | None, data: bytes) -> ValidatedUpload:
    settings = get_settings()
    name = Path(filename or "upload").name[:200]
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED:
        raise _reject("Only PDF, DOCX or TXT files are accepted")
    if not data:
        raise _reject("File is empty")
    if len(data) > settings.max_upload_bytes:
        raise _reject(f"File exceeds the {settings.max_upload_mb} MB limit")
    mime = (declared_mime or "").split(";")[0].strip().lower()
    if mime not in ALLOWED[ext] | GENERIC_MIMES:
        raise _reject("File type does not match its extension")
    if ext == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise _reject("File content is not a PDF")
        if any(marker in data for marker in PDF_ACTIVE_MARKERS):
            raise _reject("PDFs with embedded scripts, launch actions or attachments are not accepted")
    elif ext == ".docx":
        if not data.startswith(b"PK\x03\x04"):
            raise _reject("File content is not a DOCX document")
        _check_docx(data)
    else:
        if b"\x00" in data[:4096]:
            raise _reject("Text file contains binary content")
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise _reject("Text file must be UTF-8") from exc
    return ValidatedUpload(name, ext, next(iter(ALLOWED[ext])), data, hashlib.sha256(data).hexdigest())


def store(upload: ValidatedUpload) -> str:
    """Persist bytes under a random key. Returns the storage key (never derived from user input)."""
    key = secrets.token_hex(16)
    directory = get_settings().upload_dir
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{key}.bin").write_bytes(upload.data)
    return key


def load(storage_key: str) -> bytes:
    if not storage_key.isalnum():
        raise _reject("Invalid storage key")
    return (get_settings().upload_dir / f"{storage_key}.bin").read_bytes()


def remove(storage_key: str) -> None:
    if storage_key.isalnum():
        (get_settings().upload_dir / f"{storage_key}.bin").unlink(missing_ok=True)
