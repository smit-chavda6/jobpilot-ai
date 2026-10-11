"""Hardened file upload validator with MIME, magic-byte, and size caps."""

import os
import uuid
from typing import Tuple

from fastapi import HTTPException, UploadFile, status

from apps.api.config import settings

# Magic byte signatures for authorized file types
MAGIC_SIGNATURES = {
    "application/pdf": [b"%PDF-"],
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [b"PK\x03\x04"],
    "text/plain": [],  # plain text validated via UTF-8 decoding
}


def sanitize_filename(filename: str) -> str:
    """Sanitizes uploaded filename to prevent directory traversal attacks."""
    basename = os.path.basename(filename)
    clean_name = "".join(c for c in basename if c.isalnum() or c in "._-")
    return clean_name or "uploaded_file"


async def validate_and_save_upload(file: UploadFile) -> Tuple[str, str, int, str]:
    """
    Validates file MIME type, magic-bytes, and size limit.
    Saves file to secure upload directory with random UUID filename.
    Returns: (stored_file_path, original_filename, file_size_bytes, mime_type)
    """
    content = await file.read()
    file_size = len(content)

    # 1. Size cap validation
    if file_size > settings.MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)}MB.",
        )

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # 2. Content-Type and Magic bytes verification
    content_type = file.content_type or "application/octet-stream"
    original_name = sanitize_filename(file.filename or "resume")

    # Magic byte checks
    is_valid_magic = False
    if content[:5] == b"%PDF-":
        content_type = "application/pdf"
        is_valid_magic = True
    elif content[:4] == b"PK\x03\x04" and original_name.endswith(".docx"):
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        is_valid_magic = True
    else:
        # Check if valid text
        try:
            content.decode("utf-8")
            content_type = "text/plain"
            is_valid_magic = True
        except UnicodeDecodeError:
            is_valid_magic = False

    if not is_valid_magic:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file format. Please upload a valid PDF, DOCX, or TXT document.",
        )

    # 3. Ensure upload directory exists
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    # 4. Save with random storage key
    ext = os.path.splitext(original_name)[1].lower() or ".bin"
    safe_filename = f"{uuid.uuid4().hex}{ext}"
    stored_path = os.path.join(settings.UPLOAD_DIR, safe_filename)

    with open(stored_path, "wb") as f:
        f.write(content)

    return stored_path, original_name, file_size, content_type
