"""Job fingerprinting (exact dedup) and trigram similarity (potential-duplicate flagging)."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_COMPANY_SUFFIXES = re.compile(
    r"\b(inc|llc|ltd|limited|corp|corporation|co|gmbh|plc|pvt|private|technologies|technology|labs)\b\.?"
)
_TRACKING_PARAMS = re.compile(r"^(utm_.*|gh_src|lever-source|source|ref|referrer|trk|fbclid|gclid|mc_.*)$", re.I)
_TITLE_NOISE = re.compile(r"\b(sr|senior)\b")


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    v = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    v = re.sub(r"[^a-z0-9+#]+", " ", v)
    return re.sub(r"\s+", " ", v).strip()


def normalize_company(value: str | None) -> str:
    return re.sub(r"\s+", " ", _COMPANY_SUFFIXES.sub(" ", normalize_text(value))).strip()


def normalize_title(value: str | None) -> str:
    return re.sub(r"\s+", " ", _TITLE_NOISE.sub("senior", normalize_text(value))).strip()


def normalize_location(value: str | None) -> str:
    v = normalize_text(value)
    return "remote" if v in {"remote", "anywhere", "work from home", "wfh", "fully remote"} else v


def canonicalize_url(url: str | None) -> str:
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return ""
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return ""
    host = parts.hostname.lower().removeprefix("www.")
    path = re.sub(r"/+$", "", parts.path) or "/"
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query) if not _TRACKING_PARAMS.match(k)))
    return urlunsplit(("https", host, path, query, ""))


def job_fingerprint(company: str | None, title: str | None, location: str | None, url: str | None) -> str:
    key = "|".join(
        [normalize_company(company), normalize_title(title), normalize_location(location), canonicalize_url(url)]
    )
    return hashlib.sha256(key.encode()).hexdigest()


def trigrams(value: str) -> set[str]:
    v = f"  {normalize_text(value)} "
    return {v[i : i + 3] for i in range(len(v) - 2)}


def trigram_similarity(a: str, b: str) -> float:
    ta, tb = trigrams(a), trigrams(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


DUPLICATE_THRESHOLD = 0.72


def duplicate_key(company: str | None, title: str | None) -> str:
    return f"{normalize_company(company)} {normalize_title(title)}"
