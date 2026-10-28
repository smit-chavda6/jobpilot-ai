"""Concrete job-source adapters. Only sources whose terms permit programmatic access are enabled.

Every network adapter goes through `safe_fetch` (SSRF protections, size/time caps, User-Agent).
"""

from __future__ import annotations

import csv
import html
import io
import json
import re
from collections.abc import AsyncIterator
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

from defusedxml import ElementTree

from app.adapters.base import (
    AdapterCapabilities,
    ComplianceInfo,
    DisabledSource,
    FetchContext,
    JobSourceAdapter,
    RawJob,
)
from app.errors import UnprocessableError
from app.services import job_parser
from app.services.job_parser import JobDraft
from app.services.safe_fetch import safe_get_with_retry

_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
MAX_ROWS = 500


def _slug(value: Any, label: str) -> str:
    v = str(value or "").strip()
    if not _SLUG_RE.match(v):
        raise UnprocessableError(f"Invalid {label}", code="invalid_source_params")
    return v


def _iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        if isinstance(value, int | float):
            return datetime.fromtimestamp(value / 1000 if value > 1e11 else value)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, OSError):
        try:
            return parsedate_to_datetime(str(value))
        except (TypeError, ValueError):
            return None


# --------------------------------------------------------------------------- manual / files


class PasteAdapter:
    id, name = "manual_paste", "Paste job description"
    capabilities = AdapterCapabilities()
    compliance = ComplianceInfo("n/a", "2026-10-28", ["user_provided_text"], "User pastes text they can already see.")
    settings_flag = None

    async def fetch(self, ctx: FetchContext) -> AsyncIterator[RawJob]:
        yield RawJob({"text": ctx.params["text"], "url": ctx.params.get("url")}, ref="paste")

    def normalize(self, raw: RawJob) -> JobDraft:
        return job_parser.parse_pasted(raw.payload["text"], raw.payload.get("url"))


class UrlAdapter:
    id, name = "manual_url", "Import from URL"
    capabilities = AdapterCapabilities(verify_listing=True)
    compliance = ComplianceInfo(
        "n/a",
        "2026-10-28",
        ["single_page_fetch_on_user_request"],
        "Fetches one user-supplied page, honouring robots.txt; prefers schema.org JobPosting data. "
        "Pages behind logins are not fetched - paste the text instead.",
    )
    settings_flag = "source_url_fetch_enabled"

    async def fetch(self, ctx: FetchContext) -> AsyncIterator[RawJob]:
        result = await safe_get_with_retry(ctx.params["url"], check_robots=True)
        yield RawJob({"html": result.text, "url": result.url, "ctype": result.content_type}, ref=result.url)

    def normalize(self, raw: RawJob) -> JobDraft:
        page, url = raw.payload["html"], raw.payload["url"]
        draft = job_parser.from_json_ld(page, url)
        if draft is not None:
            return draft
        title_m = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
        h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S | re.I)
        heading = h1_m or title_m
        title = job_parser.html_to_text(heading.group(1)) if heading else "Untitled role"
        body_m = re.search(r"<(main|article)[^>]*>(.*?)</\1>", page, re.S | re.I)
        draft = job_parser.from_html(body_m.group(2) if body_m else page, title=title[:300], url=url)
        return draft


class CsvJsonAdapter:
    id, name = "file_import", "CSV / JSON file"
    capabilities = AdapterCapabilities()
    compliance = ComplianceInfo("n/a", "2026-10-28", ["user_provided_file"], "User uploads their own export.")
    settings_flag = None
    FIELDS = (
        "title",
        "company",
        "location",
        "url",
        "description",
        "salary_min",
        "salary_max",
        "employment_type",
        "remote_policy",
        "posted_at",
    )

    async def fetch(self, ctx: FetchContext) -> AsyncIterator[RawJob]:
        content: str = ctx.params["content"]
        kind: str = ctx.params["format"]
        rows: list[dict[str, Any]]
        if kind == "json":
            try:
                data = json.loads(content)
            except json.JSONDecodeError as exc:
                raise UnprocessableError(f"Invalid JSON: {exc.msg}", code="invalid_file") from exc
            rows = data.get("jobs", []) if isinstance(data, dict) else data
            if not isinstance(rows, list):
                raise UnprocessableError('JSON must be a list of jobs or {"jobs": [...]}', code="invalid_file")
        else:
            rows = list(csv.DictReader(io.StringIO(content)))
        for i, row in enumerate(rows[:MAX_ROWS]):
            if isinstance(row, dict):
                yield RawJob({k.strip().lower(): v for k, v in row.items() if k}, ref=f"row {i + 1}")

    def normalize(self, raw: RawJob) -> JobDraft:
        r = raw.payload
        if not str(r.get("title") or "").strip():
            raise UnprocessableError("Row has no title", code="invalid_row")

        def num(v: Any) -> int | None:
            try:
                return int(float(str(v).replace(",", ""))) if v not in (None, "") else None
            except ValueError:
                return None

        draft = job_parser.from_text(
            str(r.get("description") or ""),
            title=str(r["title"]),
            company=str(r.get("company") or ""),
            location=str(r.get("location") or ""),
            url=(str(r["url"]) if r.get("url") else None),
            salary_min=num(r.get("salary_min")),
            salary_max=num(r.get("salary_max")),
            employment_type=str(r.get("employment_type") or "unknown"),
            remote_policy=str(r.get("remote_policy") or "unknown"),
            posted_at=_iso(r.get("posted_at")),
            is_demo=str(r.get("is_demo", "")).lower() in ("true", "1"),
        )
        return draft


# --------------------------------------------------------------------------- public ATS job boards


class GreenhouseAdapter:
    id, name = "greenhouse", "Greenhouse job boards (public API)"
    capabilities = AdapterCapabilities(discover=True, verify_listing=True)
    compliance = ComplianceInfo(
        "https://developers.greenhouse.io/job-board.html",
        "2026-10-28",
        ["public_job_board_api_GET"],
        "The Job Board API is public and unauthenticated for GET requests and is intended for "
        "displaying a company's openings. We only read listings; applications are never submitted via API.",
    )
    settings_flag = "source_greenhouse_enabled"

    async def fetch(self, ctx: FetchContext) -> AsyncIterator[RawJob]:
        token = _slug(ctx.params.get("board"), "Greenhouse board token")
        res = await safe_get_with_retry(
            f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true", accept="application/json"
        )
        data = json.loads(res.text)
        for job in data.get("jobs", [])[:MAX_ROWS]:
            job.setdefault("company_name", token)
            yield RawJob(job, ref=str(job.get("id")))

    def normalize(self, raw: RawJob) -> JobDraft:
        j = raw.payload
        return job_parser.from_html(
            html.unescape(j.get("content") or ""),
            title=j.get("title", ""),
            company=j.get("company_name", ""),
            location=(j.get("location") or {}).get("name", ""),
            url=j.get("absolute_url"),
            posted_at=_iso(j.get("updated_at")),
            source_ref=str(j.get("id")),
        )


class LeverAdapter:
    id, name = "lever", "Lever job postings (public API)"
    capabilities = AdapterCapabilities(discover=True, verify_listing=True)
    compliance = ComplianceInfo(
        "https://github.com/lever/postings-api",
        "2026-10-28",
        ["public_postings_api_GET"],
        "Lever's Postings API exposes published postings publicly for job-site integrations. Read-only use.",
    )
    settings_flag = "source_lever_enabled"

    async def fetch(self, ctx: FetchContext) -> AsyncIterator[RawJob]:
        company = _slug(ctx.params.get("company"), "Lever company id")
        res = await safe_get_with_retry(
            f"https://api.lever.co/v0/postings/{company}?mode=json", accept="application/json"
        )
        data = json.loads(res.text)
        for job in (data if isinstance(data, list) else [])[:MAX_ROWS]:
            job["_company"] = company
            yield RawJob(job, ref=str(job.get("id")))

    def normalize(self, raw: RawJob) -> JobDraft:
        j = raw.payload
        cats = j.get("categories") or {}
        parts = [j.get("description") or ""]
        for lst in j.get("lists") or []:
            parts.append(f"<h3>{html.escape(lst.get('text', ''))}</h3><ul>{lst.get('content', '')}</ul>")
        parts.append(j.get("additional") or "")
        sal = j.get("salaryRange") or {}
        workplace = {"remote": "remote", "hybrid": "hybrid", "onsite": "onsite"}.get(
            str(j.get("workplaceType", "")).lower(), "unknown"
        )
        commitment = str(cats.get("commitment") or "").lower()
        etype = (
            "full_time"
            if "full" in commitment
            else "part_time"
            if "part" in commitment
            else "internship"
            if "intern" in commitment
            else "contract"
            if "contract" in commitment
            else "unknown"
        )
        return job_parser.from_html(
            "".join(parts),
            title=j.get("text", ""),
            company=j.get("_company", ""),
            location=cats.get("location") or "",
            url=j.get("hostedUrl"),
            remote_policy=workplace,
            employment_type=etype,
            salary_min=sal.get("min"),
            salary_max=sal.get("max"),
            salary_currency=sal.get("currency"),
            posted_at=_iso(j.get("createdAt")),
            source_ref=str(j.get("id")),
        )


class AshbyAdapter:
    id, name = "ashby", "Ashby job boards (public API)"
    capabilities = AdapterCapabilities(discover=True, verify_listing=True)
    compliance = ComplianceInfo(
        "https://developers.ashbyhq.com/docs/public-job-posting-api",
        "2026-10-28",
        ["public_job_posting_api_GET"],
        "Ashby's public job posting API is provided for embedding a company's job board. Read-only use.",
    )
    settings_flag = "source_ashby_enabled"

    async def fetch(self, ctx: FetchContext) -> AsyncIterator[RawJob]:
        org = _slug(ctx.params.get("organization"), "Ashby organization")
        res = await safe_get_with_retry(
            f"https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true",
            accept="application/json",
        )
        for job in json.loads(res.text).get("jobs", [])[:MAX_ROWS]:
            job["_org"] = org
            yield RawJob(job, ref=str(job.get("id")))

    def normalize(self, raw: RawJob) -> JobDraft:
        j = raw.payload
        etype = {"FullTime": "full_time", "PartTime": "part_time", "Intern": "internship", "Contract": "contract"}.get(
            str(j.get("employmentType")), "unknown"
        )
        return job_parser.from_html(
            j.get("descriptionHtml") or "",
            title=j.get("title", ""),
            company=j.get("_org", ""),
            location=j.get("location") or "",
            url=j.get("jobUrl"),
            remote_policy="remote" if j.get("isRemote") else "unknown",
            employment_type=etype,
            posted_at=_iso(j.get("publishedAt")),
            source_ref=str(j.get("id")),
        )


class RssAdapter:
    id, name = "rss", "RSS / Atom job feeds"
    capabilities = AdapterCapabilities(discover=True)
    compliance = ComplianceInfo(
        "n/a (per-feed)",
        "2026-10-28",
        ["official_feed_GET"],
        "Feeds are published for syndication. Only add feeds offered by the site for that purpose.",
    )
    settings_flag = "source_rss_enabled"

    async def fetch(self, ctx: FetchContext) -> AsyncIterator[RawJob]:
        res = await safe_get_with_retry(
            ctx.params["url"], accept="application/rss+xml,application/atom+xml,application/xml"
        )
        try:
            root = ElementTree.fromstring(res.text.encode())
        except Exception as exc:
            raise UnprocessableError("Feed is not valid RSS/Atom XML", code="invalid_feed") from exc
        atom = "{http://www.w3.org/2005/Atom}"
        items = root.findall(".//item") or root.findall(f".//{atom}entry")
        for it in items[:MAX_ROWS]:

            def text(tag: str, node: Any = it) -> str:
                el = node.find(tag)
                if el is None:
                    el = node.find(f"{atom}{tag}")
                return (el.text or "") if el is not None else ""

            link = text("link")
            if not link:
                el = it.find(f"{atom}link")
                link = el.get("href", "") if el is not None else ""
            yield RawJob(
                {
                    "title": text("title"),
                    "link": link,
                    "description": text("description") or text("summary") or text("content"),
                    "date": text("pubDate") or text("updated"),
                },
                ref=link or text("title"),
            )

    def normalize(self, raw: RawJob) -> JobDraft:
        p = raw.payload
        title, company = p["title"], ""
        if m := re.match(r"^(.+?)\s+(?:at|@|-|–|\|)\s+(.+)$", title):
            title, company = m.group(1), m.group(2)
        return job_parser.from_html(
            p["description"], title=title, company=company, url=p["link"] or None, posted_at=_iso(p["date"])
        )


ADAPTERS: dict[str, JobSourceAdapter] = {
    a.id: a  # type: ignore[misc]
    for a in (
        PasteAdapter(),
        UrlAdapter(),
        CsvJsonAdapter(),
        GreenhouseAdapter(),
        LeverAdapter(),
        AshbyAdapter(),
        RssAdapter(),
    )
}

# Email import (.eml/.mbox) is handled by app.services.email_import and registered here for the registry view.
EMAIL_SOURCE = {
    "id": "email_upload",
    "name": "Uploaded job-alert emails (.eml / .mbox)",
    "enabled": True,
    "capabilities": {
        "discover": False,
        "import": True,
        "verify_listing": False,
        "assisted_apply": False,
        "api_apply": False,
    },
    "compliance": {
        "tos_url": "n/a",
        "reviewed_on": "2026-10-28",
        "allowed_methods": ["user_provided_file"],
        "notes": "User exports their own emails. No mailbox access is needed.",
    },
}

DISABLED_SOURCES = [
    DisabledSource(
        "linkedin",
        "LinkedIn",
        "LinkedIn's User Agreement prohibits scraping and automated access to the site.",
        "Open the posting, copy the description and use 'Paste job description', or forward LinkedIn job-alert "
        "emails and upload them as .eml.",
        "https://www.linkedin.com/legal/user-agreement",
        "2026-10-28",
    ),
    DisabledSource(
        "indeed",
        "Indeed",
        "Indeed's terms prohibit scraping; its publisher job-search API is closed to new users.",
        "Use 'Import from URL' only for the employer's own page, or paste the description.",
        "https://www.indeed.com/legal",
        "2026-10-28",
    ),
    DisabledSource(
        "glassdoor",
        "Glassdoor",
        "Glassdoor's terms prohibit automated collection of content.",
        "Paste the description or import job-alert emails.",
        "https://www.glassdoor.com/about/terms.htm",
        "2026-10-28",
    ),
    DisabledSource(
        "naukri",
        "Naukri",
        "Naukri's terms prohibit automated access and data extraction.",
        "Paste the description or upload Naukri job-alert emails (.eml).",
        "https://www.naukri.com/termsconditions",
        "2026-10-28",
    ),
]
