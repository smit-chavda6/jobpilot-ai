"""Greenhouse Public ATS Board Adapter."""

from typing import Any, AsyncIterator, Dict

import httpx
from bs4 import BeautifulSoup

from apps.api.adapters.base import (
    AdapterCapabilities,
    ComplianceInfo,
    JobDraft,
    JobSourceAdapter,
    RawJob,
)
from apps.api.services.resume_parser_service import extract_skills_from_text


class GreenhouseAdapter(JobSourceAdapter):
    id: str = "greenhouse_public_board"
    capabilities = AdapterCapabilities(
        discover=True,
        import_listing=True,
        verify_listing=True,
        assisted_apply=False,
        api_apply=False,
    )
    compliance = ComplianceInfo(
        tos_url="https://www.greenhouse.com/privacy-policy",
        reviewed_on="2026-10-11",
        allowed_methods=["HTTP GET public JSON board endpoints"],
        notes="Uses public candidate job board API (boards-api.greenhouse.io). No authentication required.",
        is_enabled=True,
    )

    async def fetch(self, ctx: Dict[str, Any]) -> AsyncIterator[RawJob]:
        board_token = ctx.get("board_token", "").strip().lower()
        if not board_token:
            return

        url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("jobs", []):
                    yield RawJob(
                        source_id=self.id,
                        external_id=str(item.get("id")),
                        raw_payload={**item, "company": board_token.capitalize()},
                    )

    def normalize(self, raw: RawJob) -> JobDraft:
        payload = raw.raw_payload
        title = payload.get("title", "Untitled Position")
        company = payload.get("company", "Unknown Organization")
        raw_content = payload.get("content", "")

        # Clean HTML content into readable text
        soup = BeautifulSoup(raw_content, "html.parser")
        clean_desc = soup.get_text(separator="\n").strip() or title

        location = (
            payload.get("location", {}).get("name")
            if isinstance(payload.get("location"), dict)
            else "Remote"
        )
        remote_type = (
            "remote"
            if "remote" in str(location).lower() or "remote" in title.lower()
            else "on-site"
        )

        skills = extract_skills_from_text(clean_desc)

        return JobDraft(
            title=title,
            company=company,
            description=clean_desc,
            location=location,
            remote_type=remote_type,
            employment_type="full-time",
            required_skills=skills[:6],
            preferred_skills=skills[6:10],
            source_id=self.id,
            source_url=payload.get("absolute_url"),
        )
