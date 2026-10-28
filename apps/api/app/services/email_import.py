"""Parse uploaded .eml / .mbox files (no mailbox OAuth required) into plain messages, and extract
job listings from job-alert emails."""

from __future__ import annotations

import email
import hashlib
import mailbox
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from email import policy
from email.message import EmailMessage as PyEmailMessage
from email.utils import parseaddr, parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, cast

from app.errors import UnprocessableError
from app.services.job_parser import html_to_text

MAX_MESSAGES = 200
MAX_BYTES = 10 * 1024 * 1024


@dataclass
class ParsedEmail:
    message_id: str
    subject: str
    sender: str
    received_at: datetime | None
    text: str
    links: list[tuple[str, str]] = field(default_factory=list)  # (anchor text, href)


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            self.links.append((" ".join("".join(self._buf).split()), self._href))
            self._href = None


def _parse_one(msg: PyEmailMessage) -> ParsedEmail:
    html_body = text_body = ""
    for part in msg.walk() if msg.is_multipart() else [msg]:
        ctype = part.get_content_type()
        if part.get_content_disposition() == "attachment":
            continue  # attachments are never opened
        try:
            content = part.get_content()
        except (LookupError, KeyError, ValueError):
            continue
        if not isinstance(content, str):
            continue
        if ctype == "text/html" and not html_body:
            html_body = content
        elif ctype == "text/plain" and not text_body:
            text_body = content
    links: list[tuple[str, str]] = []
    if html_body:
        lp = _LinkParser()
        lp.feed(html_body)
        links = lp.links
    text = text_body or html_to_text(html_body)
    if not links:
        links = [("", u) for u in re.findall(r"https?://[^\s<>\")]+", text)]
    received = None
    if msg.get("Date"):
        try:
            received = parsedate_to_datetime(str(msg["Date"]))
        except (TypeError, ValueError):
            received = None
    subject = str(msg.get("Subject") or "")[:500]
    sender = parseaddr(str(msg.get("From") or ""))[1].lower()
    mid = (
        str(msg.get("Message-ID") or "").strip()
        or "gen-" + hashlib.sha256(f"{subject}|{sender}|{text[:500]}".encode()).hexdigest()[:32]
    )
    return ParsedEmail(mid[:512], subject, sender, received, text[:50_000], links[:200])


def _mbox_factory(f: Any) -> PyEmailMessage:
    return cast(PyEmailMessage, email.message_from_binary_file(f, policy=policy.default))  # type: ignore[arg-type]


def parse_email_upload(filename: str, data: bytes) -> list[ParsedEmail]:
    if len(data) > MAX_BYTES:
        raise UnprocessableError("Email file exceeds 10 MB", code="upload_rejected")
    name = filename.lower()
    if name.endswith(".eml"):
        msg = cast(PyEmailMessage, email.message_from_bytes(data, policy=policy.default))  # type: ignore[arg-type]
        if not msg.keys():
            raise UnprocessableError("This does not look like an email file", code="upload_rejected")
        return [_parse_one(msg)]
    if name.endswith(".mbox"):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "upload.mbox"
            path.write_bytes(data)
            box = mailbox.mbox(str(path), factory=_mbox_factory)  # type: ignore[arg-type]
            out = [_parse_one(cast(PyEmailMessage, m)) for _, m in zip(range(MAX_MESSAGES), box, strict=False)]
            box.close()
        if not out:
            raise UnprocessableError("No messages found in mbox", code="upload_rejected")
        return out
    raise UnprocessableError("Only .eml or .mbox files are accepted", code="upload_rejected")


_JOBISH = re.compile(
    r"\b(engineer|developer|analyst|scientist|manager|intern|designer|consultant|specialist|architect|"
    r"researcher|associate|lead|administrator|devops|sre|ml|ai|data)\b",
    re.I,
)
_SKIP_ANCHORS = re.compile(r"unsubscribe|privacy|terms|settings|view in browser|manage alerts|help|see all", re.I)


def jobs_from_alert(parsed: ParsedEmail) -> list[dict[str, str]]:
    """Each link whose anchor looks like a job title becomes a job draft; anchor 'Title at Company'
    or 'Title - Company' is split. Unrecognised alerts fall back to a single job from the body."""
    jobs: list[dict[str, str]] = []
    seen: set[str] = set()
    for anchor, href in parsed.links:
        if not anchor or len(anchor) > 140 or _SKIP_ANCHORS.search(anchor) or not _JOBISH.search(anchor):
            continue
        if not href.startswith(("http://", "https://")) or href in seen:
            continue
        seen.add(href)
        title, company = anchor, ""
        if m := re.match(r"^(.+?)\s+(?:at|@|-|–|—|\|)\s+(.+)$", anchor):
            title, company = m.group(1), m.group(2)
        jobs.append({"title": title, "company": company, "url": href})
    return jobs
