# Source compliance registry

The code registry lives in `apps/api/app/adapters/sources.py` (`ADAPTERS`, `EMAIL_SOURCE`,
`DISABLED_SOURCES`) and is served at `GET /api/sources`. This page mirrors it. Review dates are the
dates the terms were last checked for this build. **Re-check each source's terms before enabling it
for other users.**

## Enabled sources

| ID | Source | Permitted method | Terms / docs | Reviewed | Notes |
|---|---|---|---|---|---|
| `manual_paste` | Paste job description | user-provided text | n/a | 2026-10-28 | User pastes text they can already see. |
| `manual_url` | Import from URL | single page fetch on user request | n/a | 2026-10-28 | One user-supplied page, robots.txt honoured, schema.org `JobPosting` preferred, SSRF-guarded. Pages behind logins are not fetched. |
| `file_import` | CSV / JSON file | user-provided file | n/a | 2026-10-28 | User uploads their own export. |
| `email_upload` | Job-alert emails (.eml / .mbox) | user-provided file | n/a | 2026-10-28 | No mailbox access needed. |
| `greenhouse` | Greenhouse job boards | public Job Board API (GET) | https://developers.greenhouse.io/job-board.html | 2026-10-28 | Public, unauthenticated GET for displaying a company's openings. Read-only; applications are never submitted via API. |
| `lever` | Lever postings | public Postings API (GET) | https://github.com/lever/postings-api | 2026-10-28 | Published postings exposed for job-site integrations. Read-only. |
| `ashby` | Ashby job boards | public job posting API (GET) | https://developers.ashbyhq.com/docs/public-job-posting-api | 2026-10-28 | Provided for embedding a company's job board. Read-only. |
| `rss` | RSS / Atom feeds | official feed (GET) | per feed | 2026-10-28 | Only feeds a site offers for syndication. |

Every enabled source can be switched off globally (`SOURCE_URL_FETCH_ENABLED`,
`SOURCE_GREENHOUSE_ENABLED`, `SOURCE_LEVER_ENABLED`, `SOURCE_ASHBY_ENABLED`, `SOURCE_RSS_ENABLED`)
and per user (UI → Sources & Integrations, or `PUT /api/sources/{id}`).

Capabilities: every enabled source supports `import`. Greenhouse, Lever, Ashby and RSS also support
`discover` (listing a board's or feed's postings). `manual_url`, Greenhouse, Lever and Ashby support
`verify_listing` (re-checking that a posting is still live). **No source supports `assisted_apply`
or `api_apply`.**
Every application is a manual hand-off that the user submits on the employer's site.

The public-board adapters are implemented against the documented endpoints and tested with mocked
HTTP responses shaped like the documented payloads. They have not been run against the live services.

## Disabled by policy

| Source | Reason | Manual path offered in the UI | Terms |
|---|---|---|---|
| LinkedIn | User Agreement prohibits scraping and automated access | Paste the description, or upload LinkedIn alert emails as .eml | https://www.linkedin.com/legal/user-agreement |
| Indeed | Terms prohibit scraping; publisher job-search API closed to new users | Import the employer's own page by URL, or paste | https://www.indeed.com/legal |
| Glassdoor | Terms prohibit automated collection of content | Paste, or import alert emails | https://www.glassdoor.com/about/terms.htm |
| Naukri | Terms prohibit automated access and data extraction | Paste, or upload Naukri alert emails (.eml) | https://www.naukri.com/termsconditions |

## Email providers

Gmail and Microsoft Graph OAuth ingestion are **not implemented** (P1). The UI lists them as
unavailable, with the read-only scopes they would request (`gmail.readonly`, `Mail.Read`). The
`.eml`/`.mbox` upload path covers the same use without granting mailbox access.
