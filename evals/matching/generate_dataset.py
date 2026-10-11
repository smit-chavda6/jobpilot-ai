"""Generates 50 synthetic labeled pairs for matching evaluation harness."""

import json
import os

ROLES = [
    {
        "title": "Senior Backend Engineer",
        "company": "Stripe",
        "req": ["Python", "FastAPI", "PostgreSQL", "Redis"],
        "pref": ["Docker", "Kubernetes"],
        "sal_min": 170000,
        "sal_max": 210000,
        "remote": "remote",
    },
    {
        "title": "AI Infrastructure Engineer",
        "company": "Anthropic",
        "req": ["Python", "PyTorch", "Kubernetes"],
        "pref": ["AWS", "CUDA"],
        "sal_min": 190000,
        "sal_max": 250000,
        "remote": "remote",
    },
    {
        "title": "Full Stack Engineer",
        "company": "Vercel",
        "req": ["TypeScript", "React", "Next.js", "Node.js"],
        "pref": ["Tailwind", "GraphQL"],
        "sal_min": 160000,
        "sal_max": 200000,
        "remote": "remote",
    },
    {
        "title": "Data Platform Engineer",
        "company": "Snowflake",
        "req": ["Python", "SQL", "Kafka", "PostgreSQL"],
        "pref": ["Docker", "Spark"],
        "sal_min": 175000,
        "sal_max": 220000,
        "remote": "remote",
    },
    {
        "title": "Site Reliability Engineer",
        "company": "Datadog",
        "req": ["Linux", "Kubernetes", "Docker", "Python"],
        "pref": ["AWS", "Terraform"],
        "sal_min": 165000,
        "sal_max": 205000,
        "remote": "remote",
    },
]

CANDIDATES = [
    {
        "name": "Python Distributed Expert",
        "skills": ["Python", "FastAPI", "PostgreSQL", "Redis", "Docker", "Kubernetes"],
        "remote": "remote",
        "min_salary": 160000,
    },
    {
        "name": "AI/ML Systems Specialist",
        "skills": ["Python", "PyTorch", "Kubernetes", "AWS", "CUDA", "Docker"],
        "remote": "remote",
        "min_salary": 180000,
    },
    {
        "name": "Frontend / Full Stack Dev",
        "skills": ["TypeScript", "React", "Next.js", "Tailwind", "Node.js"],
        "remote": "remote",
        "min_salary": 150000,
    },
    {
        "name": "Junior Web Developer",
        "skills": ["JavaScript", "HTML", "CSS", "Git"],
        "remote": "remote",
        "min_salary": 80000,
    },
    {
        "name": "Embedded Systems Engineer",
        "skills": ["C", "C++", "Assembly", "RTOS", "Linux"],
        "remote": "on-site",
        "min_salary": 140000,
    },
]


def generate_pairs():
    pairs = []
    pair_id = 1
    for i, cand in enumerate(CANDIDATES):
        for j, role in enumerate(ROLES):
            for variant in [0, 1]:  # 2 variants per combination -> 5 * 5 * 2 = 50 pairs
                cand_skills_set = set(s.lower() for s in cand["skills"])
                role_req_set = set(s.lower() for s in role["req"])
                overlap = len(cand_skills_set.intersection(role_req_set))

                # Compute ground truth relevance (3 = Excellent, 2 = Good, 1 = Fair, 0 = Ineligible/Poor)
                if cand["remote"] == "remote" and role["remote"] == "on-site":
                    relevance = 0
                elif cand["min_salary"] > role["sal_max"]:
                    relevance = 0
                elif overlap >= 3:
                    relevance = 3
                elif overlap >= 2:
                    relevance = 2
                elif overlap >= 1:
                    relevance = 1
                else:
                    relevance = 0

                pairs.append(
                    {
                        "id": f"eval-pair-{pair_id:03d}",
                        "label": "DEMO_EVAL_PAIR",
                        "ground_truth_relevance": relevance,
                        "candidate_skills": cand["skills"],
                        "candidate_remote": cand["remote"],
                        "candidate_min_salary": cand["min_salary"],
                        "job_title": role["title"] if variant == 0 else f"Lead {role['title']}",
                        "job_company": role["company"],
                        "job_required_skills": role["req"],
                        "job_preferred_skills": role["pref"],
                        "job_remote_type": role["remote"],
                        "job_salary_min": role["sal_min"],
                        "job_salary_max": role["sal_max"],
                    }
                )
                pair_id += 1
    return pairs


if __name__ == "__main__":
    dataset = generate_pairs()
    out_path = os.path.join(os.path.dirname(__file__), "dataset.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2)
    print(f"Generated {len(dataset)} evaluation pairs in {out_path}")
