"""Seed a DEMO account: sample profile, 30 demo jobs and a few demo applications.

Everything goes through the real HTTP API in-process (same validation, grounding, approval and
state-machine rules as the UI). Every job and application is flagged is_demo and shown with a DEMO
badge; analytics exclude demo records unless you opt in. Job URLs use the reserved example.com domain.

Usage (from apps/api):  python -m scripts.seed_demo [--email demo@example.com] [--password ...]
Requires the database to be migrated (alembic upgrade head). Safe to re-run: an existing demo
account is left untouched.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import random
import sys
from pathlib import Path

import httpx

DEMO_RESUME = """DEMO Candidate (sample data)
demo.candidate@example.com | Bengaluru, India

SUMMARY
Data scientist with 4 years of experience building machine learning models and data pipelines in Python.

EXPERIENCE
Data Scientist — DEMO Analytics Co (Jan 2022 – Present)
- Built a customer churn prediction model using Python, scikit-learn and XGBoost that improved retention campaign precision by 18%.
- Designed Airflow pipelines that process 2 million events per day into PostgreSQL.
- Deployed models as FastAPI services in Docker on AWS.

Junior Data Analyst — DEMO Retail Ltd (Jun 2020 – Dec 2021)
- Automated weekly sales reporting with SQL and Pandas, saving 6 hours per week.
- Created Tableau dashboards for 12 regional managers.

PROJECTS
Resume Matcher (2023)
- Built an NLP pipeline with Hugging Face transformers to rank job postings against resumes.

EDUCATION
M.Sc. Data Science, DEMO University (2018 – 2020)

SKILLS
Python, SQL, Pandas, scikit-learn, XGBoost, PyTorch, Airflow, Docker, AWS, Tableau, Statistics
"""

ROLES = [
    (
        "Machine Learning Engineer",
        "Python, PyTorch, Docker and AWS. 3+ years of experience. Bachelor's degree required.",
        "hybrid",
    ),
    ("Data Scientist", "Python, SQL, scikit-learn and statistics. 3+ years of experience.", "remote"),
    (
        "Senior Data Scientist",
        "Python, XGBoost, experimentation and stakeholder communication. 6+ years of experience.",
        "hybrid",
    ),
    ("Data Analyst", "SQL, Tableau and Excel. 2+ years of experience.", "onsite"),
    ("Analytics Engineer", "SQL, dbt, Airflow and PostgreSQL. 3+ years of experience.", "remote"),
    ("MLOps Engineer", "Kubernetes, Docker, MLflow and AWS. 4+ years of experience.", "remote"),
    (
        "NLP Engineer",
        "Python, Hugging Face transformers and PyTorch. 3+ years of experience. Master's preferred.",
        "hybrid",
    ),
    ("Backend Engineer", "Java, Spring and Kubernetes. 5+ years of experience.", "onsite"),
    ("Data Engineer", "Python, Spark, Airflow and AWS. 4+ years of experience.", "hybrid"),
    ("BI Developer", "Power BI, SQL Server and DAX. 3+ years of experience.", "onsite"),
]
COMPANIES = [
    "Nimbus Labs",
    "Orbit Analytics",
    "Quill Health",
    "Larkspur Retail",
    "Tidewater Fintech",
    "Kestrel Mobility",
]
LOCATIONS = ["Bengaluru, India", "Pune, India", "Hyderabad, India", "Remote", "Chennai, India"]

# (job index, outcome) - outcomes are applied after a confirmed submission.
APPLICATIONS = [
    (0, "interviewing"),
    (1, "rejected"),
    (2, None),
    (4, "ghosted"),
    (6, "offer"),
    (8, "prepare_only"),
]


def demo_jobs_csv(n: int = 30, seed: int = 7) -> bytes:
    rng = random.Random(seed)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(
        [
            "title",
            "company",
            "location",
            "url",
            "description",
            "salary_min",
            "salary_max",
            "employment_type",
            "remote_policy",
            "is_demo",
        ]
    )
    for i in range(n):
        title, desc, remote = ROLES[i % len(ROLES)]
        company = f"{COMPANIES[i % len(COMPANIES)]} (DEMO)"
        location = "Remote" if remote == "remote" else LOCATIONS[rng.randrange(len(LOCATIONS) - 1)]
        low = rng.choice([1_200_000, 1_800_000, 2_400_000, 3_000_000])
        w.writerow(
            [
                title,
                company,
                location,
                f"https://jobs.example.com/demo/{i + 1}",
                f"DEMO listing - not a real job. {title} at {company}. {desc}",
                low,
                low + 800_000,
                "full_time",
                remote,
                "true",
            ]
        )
    return out.getvalue().encode("utf-8")


class Client:
    def __init__(self, http: httpx.AsyncClient):
        self.http = http
        self.csrf = ""

    async def init(self) -> None:
        self.csrf = (await self.http.get("/api/auth/csrf")).json()["csrf_token"]

    async def call(self, method: str, url: str, expect: tuple[int, ...] = (200, 201), **kw: object) -> httpx.Response:
        headers = {"X-CSRF-Token": self.csrf, **kw.pop("headers", {})}  # type: ignore[dict-item]
        r = await self.http.request(method, url, headers=headers, **kw)  # type: ignore[arg-type]
        if r.status_code not in expect:
            raise RuntimeError(f"{method} {url} -> {r.status_code}: {r.text[:300]}")
        return r


async def seed(email: str, password: str) -> None:
    from app.main import create_app

    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://seed") as http:
        c = Client(http)
        await c.init()
        r = await c.call(
            "POST", "/api/auth/register", json={"email": email, "password": password}, expect=(201, 409, 422)
        )
        if r.status_code != 201:
            print(f"Account {email} already exists (or was rejected: {r.status_code}); leaving it untouched.")
            return

        await c.call("POST", "/api/consents", json={"purpose": "ai_processing", "granted": True})
        await c.call(
            "PATCH",
            "/api/profile",
            json={
                "full_name": "DEMO Candidate",
                "headline": "Data Scientist (DEMO profile)",
                "location": "Bengaluru, India",
                "years_experience": 4,
                "education_level": "master",
                "target_titles": ["Data Scientist", "Machine Learning Engineer"],
                "preferred_locations": ["Bengaluru", "Remote"],
                "remote_preference": "any",
                "employment_types": ["full_time"],
            },
        )
        up = await c.call(
            "POST", "/api/resumes", files={"file": ("demo_resume.txt", DEMO_RESUME.encode(), "text/plain")}
        )
        fact_ids = [f["id"] for f in up.json()["facts"]]
        await c.call("POST", "/api/facts/status", json={"fact_ids": fact_ids, "status": "confirmed"})
        await c.call("PATCH", "/api/profile", json={"onboarding_step": 5, "onboarding_completed": True})

        imp = await c.call(
            "POST", "/api/jobs/import/file", files={"file": ("demo_jobs.csv", demo_jobs_csv(), "text/csv")}
        )
        created = imp.json()["created"]
        print(f"Imported {len(created)} DEMO jobs.")

        submitted = 0
        for idx, outcome in APPLICATIONS:
            if idx >= len(created):
                continue
            app_id = (await c.call("POST", "/api/applications", json={"job_id": created[idx]["id"]})).json()["id"]
            await c.call("POST", f"/api/applications/{app_id}/prepare")
            if outcome == "prepare_only":
                continue
            await c.call("POST", f"/api/applications/{app_id}/ready")
            review = (await c.call("POST", f"/api/applications/{app_id}/request-approval")).json()
            await c.call("POST", f"/api/applications/{app_id}/approve", json={"payload_hash": review["payload_hash"]})
            await c.call("POST", f"/api/applications/{app_id}/handoff")
            await c.call(
                "POST",
                f"/api/applications/{app_id}/confirm-submission",
                json={"confirmed": True, "note": "DEMO - seeded"},
            )
            submitted += 1
            if outcome:
                await c.call("POST", f"/api/applications/{app_id}/move", json={"status": outcome})
        print(
            f"Created {len(APPLICATIONS)} DEMO applications ({submitted} through the full approval + confirmation flow)."
        )
        print(f"\nSign in as {email} / {password}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--email", default="demo@example.com")
    p.add_argument("--password", default="DemoPassw0rd!")
    args = p.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    asyncio.run(seed(args.email, args.password))


if __name__ == "__main__":
    main()
