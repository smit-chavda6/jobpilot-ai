"""Generate the SYNTHETIC matching evaluation dataset (clearly labelled; not real people or jobs).

Relevance labels (0-3) are assigned from how each job was *constructed* relative to the profile,
independently of the scoring engine:
  3 = target title, required skills all held, experience/location fit
  2 = related title, about half the required skills held
  1 = few required skills held, or experience requirement far above the profile
  0 = different field, or violates a hard constraint (blocked company / on-site outside preferences)

Run: python evals/matching/generate_dataset.py  (writes dataset.json next to this file)
"""

from __future__ import annotations

import json
import random
from pathlib import Path

SEED = 20261028

PROFILES = [
    {
        "id": "synthetic-profile-ds",
        "label": "SYNTHETIC",
        "skills": ["Python", "SQL", "Pandas", "scikit-learn", "XGBoost", "Statistics", "Tableau", "Airflow"],
        "years_experience": 4,
        "education_level": "master",
        "target_titles": ["Data Scientist"],
        "preferred_locations": ["Bengaluru"],
        "remote_preference": "any",
        "employment_types": ["full_time"],
        "blocked_companies": ["Blocked Analytics"],
        "title": "Data Scientist",
        "related": "Data Analyst",
        "family": ["PyTorch", "Spark", "Snowflake"],
        "other_field": ("Frontend Engineer", ["React", "TypeScript", "CSS", "Figma"]),
    },
    {
        "id": "synthetic-profile-be",
        "label": "SYNTHETIC",
        "skills": ["Java", "Spring", "PostgreSQL", "Kafka", "Docker", "Kubernetes", "AWS", "REST"],
        "years_experience": 6,
        "education_level": "bachelor",
        "target_titles": ["Backend Engineer"],
        "preferred_locations": ["Pune"],
        "remote_preference": "any",
        "employment_types": ["full_time"],
        "blocked_companies": ["Blocked Systems"],
        "title": "Backend Engineer",
        "related": "Platform Engineer",
        "family": ["Go", "Redis", "Terraform"],
        "other_field": ("Data Scientist", ["Python", "scikit-learn", "Statistics", "Tableau"]),
    },
    {
        "id": "synthetic-profile-fe",
        "label": "SYNTHETIC",
        "skills": ["JavaScript", "TypeScript", "React", "CSS", "HTML", "Next.js", "GraphQL", "Figma"],
        "years_experience": 3,
        "education_level": "bachelor",
        "target_titles": ["Frontend Engineer"],
        "preferred_locations": ["Remote", "Hyderabad"],
        "remote_preference": "remote",
        "employment_types": ["full_time"],
        "blocked_companies": ["Blocked UI"],
        "title": "Frontend Engineer",
        "related": "Full Stack Engineer",
        "family": ["Vue", "Angular", "Node.js"],
        "other_field": ("Data Engineer", ["Spark", "Airflow", "Snowflake", "Kafka"]),
    },
]


def make_jobs(p: dict, rng: random.Random) -> list[dict]:  # type: ignore[type-arg]
    skills = p["skills"]
    loc = p["preferred_locations"][0]
    jobs = []
    for i in range(5):  # label 3
        req = rng.sample(skills, 4)
        jobs.append(
            {
                "label": 3,
                "title": p["title"],
                "company": f"SyntheticCo{i}",
                "location": loc,
                "remote_policy": "hybrid",
                "employment_type": "full_time",
                "min_years": max(1, p["years_experience"] - 1),
                "required_skills": req,
                "preferred_skills": rng.sample(skills, 2),
            }
        )
    for i in range(5):  # label 2
        req = rng.sample(skills, 2) + rng.sample(p["family"], 2)
        jobs.append(
            {
                "label": 2,
                "title": p["related"],
                "company": f"SyntheticRel{i}",
                "location": loc,
                "remote_policy": "hybrid",
                "employment_type": "full_time",
                "min_years": p["years_experience"],
                "required_skills": req,
                "preferred_skills": rng.sample(p["family"], 1),
            }
        )
    for i in range(5):  # label 1
        req = rng.sample(skills, 1) + rng.sample(p["family"], 3)
        jobs.append(
            {
                "label": 1,
                "title": f"Senior {p['related']}",
                "company": f"SyntheticStretch{i}",
                "location": loc,
                "remote_policy": "unknown",
                "employment_type": "full_time",
                "min_years": p["years_experience"] + 6,
                "required_skills": req,
                "preferred_skills": [],
            }
        )
    other_title, other_skills = p["other_field"]
    for i in range(3):  # label 0: different field
        jobs.append(
            {
                "label": 0,
                "title": other_title,
                "company": f"SyntheticOther{i}",
                "location": "Chennai",
                "remote_policy": "onsite",
                "employment_type": "full_time",
                "min_years": 2,
                "required_skills": rng.sample(other_skills, 3),
                "preferred_skills": [],
            }
        )
    jobs.append(
        {
            "label": 0,
            "title": p["title"],
            "company": p["blocked_companies"][0],
            "location": loc,
            "remote_policy": "hybrid",
            "employment_type": "full_time",
            "min_years": 2,
            "required_skills": rng.sample(skills, 3),
            "preferred_skills": [],
        }
    )
    jobs.append(
        {
            "label": 0,
            "title": p["title"],
            "company": "SyntheticContract",
            "location": "Kolkata",
            "remote_policy": "onsite",
            "employment_type": "contract",
            "min_years": 2,
            "required_skills": rng.sample(skills, 3),
            "preferred_skills": [],
        }
    )
    return jobs


def main() -> None:
    rng = random.Random(SEED)
    out = {
        "label": "SYNTHETIC - generated by generate_dataset.py; not real people or jobs",
        "seed": SEED,
        "profiles": [],
    }
    for p in PROFILES:
        profile = {k: v for k, v in p.items() if k not in ("title", "related", "family", "other_field")}
        out["profiles"].append({"profile": profile, "jobs": make_jobs(p, rng)})
    path = Path(__file__).with_name("dataset.json")
    path.write_text(json.dumps(out, indent=1))
    print(f"wrote {sum(len(x['jobs']) for x in out['profiles'])} pairs to {path}")


if __name__ == "__main__":
    main()
