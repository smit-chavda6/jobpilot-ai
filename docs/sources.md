# JobPilot AI — Source Compliance Registry

In accordance with Operating Principle #3 (*Compliance over coverage*), JobPilot AI interacts with external sources only through permitted, officially supported, or user-mediated mechanisms.

---

## Registry of Sources

| Source Name | Category | Permitted Access Method | Terms Review Date | Default State | Justification & Policies |
|---|---|---|---|---|---|
| **Greenhouse Public Boards** | ATS Public API | Public JSON API endpoint (`boards-api.greenhouse.io`) | 2026-10-11 | **Enabled** | Public read-only endpoints intended for candidate-facing job discovery. |
| **Lever Public Postings** | ATS Public API | Public JSON API endpoint (`api.lever.co/v0/postings`) | 2026-10-11 | **Enabled** | Public candidate postings provided for applicant consumption. |
| **User Direct URL / Text Paste** | User Manual | Manual copy/paste or direct URL fetch with robots.txt check | 2026-10-11 | **Enabled** | User-directed import for their personal review and organization. |
| **Structured File Import (CSV/JSON)** | User Upload | Direct parsing of exported job data | 2026-10-11 | **Enabled** | Offline data supplied directly by user. |
| **Email Job Alerts (.eml/.mbox)** | User Upload | Local parsing of uploaded MIME email message files | 2026-10-11 | **Enabled** | Safe user-initiated upload without requiring live OAuth mailbox access for P0. |
| **LinkedIn Job Search** | Commercial Platform | Browser Assisted Manual / Import Extension | 2026-10-11 | **Disabled (Auto)** | Automated scraping prohibited under LinkedIn Terms of Service. Guided manual / paste flow provided. |
| **Indeed Job Search** | Commercial Platform | Guided Manual / Paste | 2026-10-11 | **Disabled (Auto)** | Automated scraping prohibited. Users import listings manually. |

---

## Policy on Disallowed Platforms
When an applicant attempts to import from an automated-prohibited source without authorized API keys:
1. The backend refuses direct automated headless scraping.
2. The UI provides a "Guided Manual Import" modal instructing the candidate to paste text or upload an alert file.
3. Transparent status explanation is displayed directly in the user interface.
