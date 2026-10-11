"""Demo seed script creating realistic candidate persona and 30 diverse jobs labeled [DEMO]."""

import asyncio
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession

import os
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.config import settings
from apps.api.database import Base
from apps.api.models.application import Application, ApplicationActivity
from apps.api.models.fact import ProfileFact
from apps.api.models.job import Job, JobMatch
from apps.api.models.profile import UserProfile
from apps.api.models.resume import Resume, ResumeVersion
from apps.api.models.security import ApprovalRecord
from apps.api.security.passwords import hash_password


async def get_working_engine_and_session():
    """Attempts PostgreSQL; if unavailable, falls back gracefully to local SQLite demo database."""
    target_url = os.getenv("DEMO_DATABASE_URL") or os.getenv("DATABASE_URL") or settings.DATABASE_URL
    try:
        engine = create_async_engine(target_url, pool_pre_ping=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print(f"[*] Connected to database: {target_url.split('@')[-1] if '@' in target_url else target_url}")
        return engine, async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    except Exception as e:
        print(f"[!] PostgreSQL not reachable ({type(e).__name__}). Falling back to local SQLite: sqlite+aiosqlite:///./jobpilot_demo.db")
        sqlite_url = "sqlite+aiosqlite:///./jobpilot_demo.db"
        engine = create_async_engine(sqlite_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return engine, async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def seed_demo():
    print("[*] Initializing database...")
    engine, session_factory = await get_working_engine_and_session()

    async with session_factory() as session:
        # 1. Create Demo User
        demo_email = "demo@jobpilot.ai"
        pw_hash = hash_password("Password123!")

        from apps.api.models.user import User
        from sqlalchemy import select

        stmt = select(User).where(User.email == demo_email)
        existing_user = (await session.execute(stmt)).scalar_one_or_none()

        if existing_user:
            print(f"[!] Demo user {demo_email} already exists. Removing to ensure clean seed...")
            await session.delete(existing_user)
            await session.commit()

        user = User(
            email=demo_email,
            hashed_password=pw_hash,
            is_active=True,
            is_verified=True,
            role="candidate",
        )
        session.add(user)
        await session.flush()

        # 2. Profile
        profile = UserProfile(
            user_id=user.id,
            full_name="Elena Rostova",
            headline="Full-Stack Engineer pivoting to Distributed Systems",
            location="San Francisco, CA",
            target_roles=["Senior Full-Stack Engineer", "Senior Backend Engineer"],
            target_locations=["San Francisco, CA", "Remote"],
            min_salary=160000,
            remote_preference="remote",
        )
        session.add(profile)

        # 3. Confirmed & Unconfirmed Facts (Truth over Polish)
        confirmed_facts_data = [
            ("Architected FastAPI microservices handling 500 RPS with 99.9% uptime at Stripe.", "experience", {"company": "Stripe", "metrics": ["500 RPS", "99.9%"]}),
            ("Optimized PostgreSQL queries, reducing p99 latency by 45%.", "experience", {"metrics": ["45%"]}),
            ("Built React/TypeScript client-side design system used by 45 engineers.", "experience", {"metrics": ["45 engineers"]}),
            ("Earned B.S. in Computer Science from University of Michigan with 3.8 GPA.", "education", {"degree": "B.S. in Computer Science", "institution": "University of Michigan"}),
            ("Python", "skill", {}),
            ("TypeScript", "skill", {}),
            ("FastAPI", "skill", {}),
            ("React", "skill", {}),
        ]

        unconfirmed_facts_data = [
            ("Led multi-region Kubernetes cluster disaster recovery exercise.", "experience", {"skills": ["Kubernetes"]}),
            ("Go", "skill", {}),
        ]

        created_facts = []
        for text, cat, ent in confirmed_facts_data:
            fact = ProfileFact(
                user_id=user.id,
                text=text,
                category=cat,
                confirmation_status="confirmed",
                source_type="resume",
                entities=ent,
            )
            session.add(fact)
            created_facts.append(fact)

        for text, cat, ent in unconfirmed_facts_data:
            fact = ProfileFact(
                user_id=user.id,
                text=text,
                category=cat,
                confirmation_status="candidate",  # Unusable until candidate confirms
                source_type="resume",
                entities=ent,
            )
            session.add(fact)

        await session.flush()

        # 4. Master Resume
        resume = Resume(
            user_id=user.id,
            filename="elena_rostova_master.pdf",
            file_path="uploads/demo_elena_master.pdf",
            file_size=24500,
            mime_type="application/pdf",
            raw_text="Elena Rostova\nFull-Stack Engineer\nSan Francisco, CA\n...",
            parsed_data={
                "skills": ["Python", "TypeScript", "FastAPI", "React", "PostgreSQL"],
                "summary": "Experienced engineer with verified track record across Python, TypeScript, and modern distributed systems.",
            },
            is_primary=True,
        )
        session.add(resume)
        await session.flush()

        # 5. Seed 30 Diverse Jobs labeled [DEMO]
        job_templates = [
            # High Fit / Verified
            ("[DEMO] Senior Full-Stack Engineer", "Retool", "San Francisco, CA", "remote", 175000, 220000, ["python", "typescript", "react"], ["fastapi", "postgresql"], "greenhouse"),
            ("[DEMO] Senior Backend Engineer - Core API", "Stripe", "Remote", "remote", 185000, 235000, ["python", "fastapi", "postgresql"], ["redis"], "greenhouse"),
            ("[DEMO] Full-Stack Product Engineer", "Linear", "San Francisco, CA", "remote", 170000, 210000, ["typescript", "react", "python"], [], "url_paste"),
            ("[DEMO] Platform Engineer", "Vercel", "Remote", "remote", 180000, 225000, ["typescript", "react"], ["python"], "greenhouse"),
            ("[DEMO] Senior Systems Developer", "Datadog", "Remote", "remote", 190000, 240000, ["python", "postgresql"], ["fastapi"], "file_import"),

            # Unknown Salary (Confidence Lowered)
            ("[DEMO] Staff Software Engineer", "Stealth AI", "San Francisco, CA", "remote", None, None, ["python", "react"], [], "url_paste"),
            ("[DEMO] Senior Application Engineer", "Enterprise Global", "New York, NY", "hybrid", None, None, ["python", "fastapi"], ["typescript"], "file_import"),
            ("[DEMO] Backend Infrastructure Engineer", "Fintech Labs", "Remote", "remote", None, None, ["python", "postgresql"], [], "eml_alert"),

            # Partial Matches (Missing skills: Go, Kubernetes)
            ("[DEMO] Distributed Systems Engineer", "HashiCorp", "Remote", "remote", 180000, 220000, ["go", "kubernetes"], ["python"], "greenhouse"),
            ("[DEMO] Cloud Infrastructure Engineer", "Coinbase", "Remote", "remote", 195000, 245000, ["kubernetes", "go", "terraform"], ["python"], "greenhouse"),
            ("[DEMO] DevOps & Reliability Specialist", "Scale AI", "San Francisco, CA", "on-site", 160000, 200000, ["kubernetes", "docker"], ["python"], "url_paste"),

            # Scam / Predatory Signal Jobs (Transparently flagged)
            ("[DEMO] Urgent: Entry Level Virtual Assistant", "Global Logistics LLC", "Remote", "remote", 300000, 350000, [], [], "eml_alert",
             "Immediate hire without interview! We send cashier's check to purchase equipment from our vendor. Contact on Telegram @hiring_now."),
            ("[DEMO] Work From Home Data Clerk", "Fast Financials", "Remote", "remote", 280000, 320000, [], [], "url_paste",
             "Wire transfer required for background verification. Guaranteed $300k starting compensation."),

            # Multiple other realistic jobs across permitted sources
            ("[DEMO] Senior Frontend Engineer", "Figma", "San Francisco, CA", "remote", 175000, 215000, ["react", "typescript"], [], "greenhouse"),
            ("[DEMO] Backend Engineer - Search", "Pinterest", "Remote", "remote", 165000, 205000, ["python"], ["postgresql"], "greenhouse"),
            ("[DEMO] Software Engineer - Workflows", "Notion", "San Francisco, CA", "hybrid", 170000, 210000, ["typescript", "react"], [], "greenhouse"),
            ("[DEMO] Senior Python Developer", "Automattic", "Remote", "remote", 160000, 195000, ["python"], ["fastapi"], "url_paste"),
            ("[DEMO] Full-Stack Growth Engineer", "Loom", "Remote", "remote", 165000, 200000, ["react", "python"], [], "url_paste"),
            ("[DEMO] Core Backend Engineer", "Ramp", "New York, NY", "hybrid", 180000, 225000, ["python", "postgresql"], ["fastapi"], "file_import"),
            ("[DEMO] Application Engineer", "Sentry", "San Francisco, CA", "remote", 170000, 210000, ["python", "react"], ["typescript"], "greenhouse"),
            ("[DEMO] Senior Product Engineer", "Pave", "San Francisco, CA", "remote", 165000, 205000, ["typescript", "react", "python"], [], "url_paste"),
            ("[DEMO] API Platform Engineer", "Plaid", "San Francisco, CA", "remote", 185000, 230000, ["python", "postgresql"], [], "greenhouse"),
            ("[DEMO] Software Engineer - Platform", "Discord", "San Francisco, CA", "hybrid", 175000, 220000, ["python"], ["react"], "greenhouse"),
            ("[DEMO] Senior Backend Engineer", "Benchling", "Remote", "remote", 170000, 215000, ["python", "postgresql"], [], "file_import"),
            ("[DEMO] Full-Stack Systems Engineer", "Asana", "San Francisco, CA", "hybrid", 170000, 210000, ["typescript", "python"], ["react"], "greenhouse"),
            ("[DEMO] Infrastructure Engineer", "Zapier", "Remote", "remote", 165000, 205000, ["python"], ["postgresql"], "url_paste"),
            ("[DEMO] Senior Cloud Engineer", "Apollo GraphQL", "Remote", "remote", 175000, 215000, ["typescript", "react"], [], "file_import"),
            ("[DEMO] Full-Stack Developer", "Carta", "San Francisco, CA", "remote", 160000, 200000, ["python", "react"], ["postgresql"], "greenhouse"),
            ("[DEMO] Software Engineer - Payments", "Affirm", "Remote", "remote", 175000, 215000, ["python", "postgresql"], [], "greenhouse"),
            ("[DEMO] Backend Engineer", "Dropbox", "Remote", "remote", 165000, 205000, ["python"], ["postgresql"], "greenhouse"),
        ]

        seeded_jobs = []
        for idx, item in enumerate(job_templates):
            title, company, loc, remote_type, s_min, s_max, req_sk, pref_sk, src = item[:9]
            desc = item[9] if len(item) > 9 else f"Looking for talented {title} to contribute to high-impact products at {company}. Must be dedicated to engineering excellence."

            fp = hashlib.sha256(f"{company}|{title}|{loc}|demo-{idx}".encode()).hexdigest()
            job = Job(
                user_id=user.id,
                job_fingerprint=fp,
                title=title,
                company=company,
                location=loc,
                remote_type=remote_type,
                salary_min=s_min,
                salary_max=s_max,
                required_skills=req_sk,
                preferred_skills=pref_sk,
                source_id=src,
                description=desc,
                raw_description=desc,
            )
            session.add(job)
            seeded_jobs.append(job)

        await session.flush()

        # 6. Seed Application Flow across funnel
        # App 1: Submitted Confirmed (Retool)
        retool_job = seeded_jobs[0]
        app1 = Application(
            user_id=user.id,
            job_id=retool_job.id,
            status="submitted_confirmed",
            applied_at=datetime.now(timezone.utc).isoformat(),
            cover_letter="Grounded cover letter citing verified facts for Retool.",
        )
        session.add(app1)
        await session.flush()

        canonical_payload = {
            "application_id": app1.id,
            "job_id": retool_job.id,
            "resume_version_id": None,
            "cover_letter": app1.cover_letter,
            "screening_answers": [],
            "external_url": "",
        }
        p_hash = hashlib.sha256(json.dumps(canonical_payload, sort_keys=True).encode()).hexdigest()

        approval1 = ApprovalRecord(
            user_id=user.id,
            action_type="application_submission",
            entity_id=app1.id,
            payload_hash=p_hash,
        )
        session.add(approval1)

        act1 = ApplicationActivity(
            application_id=app1.id,
            user_id=user.id,
            from_status="submitting",
            to_status="submitted_confirmed",
            activity_type="status_change",
            message="Application submitted with explicit human confirmation.",
            activity_metadata={"confirmed_by_user": True},
        )
        session.add(act1)

        # App 2: Interviewing (Stripe)
        stripe_job = seeded_jobs[1]
        app2 = Application(
            user_id=user.id,
            job_id=stripe_job.id,
            status="interviewing",
            applied_at=datetime.now(timezone.utc).isoformat(),
        )
        session.add(app2)

        # App 3: Ready for review (Linear)
        linear_job = seeded_jobs[2]
        app3 = Application(
            user_id=user.id,
            job_id=linear_job.id,
            status="ready_for_review",
        )
        session.add(app3)

        # App 4: Saved (Vercel)
        vercel_job = seeded_jobs[3]
        app4 = Application(
            user_id=user.id,
            job_id=vercel_job.id,
            status="saved",
        )
        session.add(app4)

        await session.commit()

        print("[+] Demo seed completed successfully!")
        print(f"[+] Candidate: Elena Rostova ({demo_email} / Password123!)")
        print(f"[+] ProfileFacts: 8 Confirmed, 2 Candidate (Unconfirmed)")
        print(f"[+] Jobs: {len(seeded_jobs)} diverse jobs tagged [DEMO]")
        print(f"[+] Applications: 4 tracked across pipeline stages")


if __name__ == "__main__":
    asyncio.run(seed_demo())
