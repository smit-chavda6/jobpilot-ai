"""Matching eval runner: precision@5, NDCG@10 and Spearman rank correlation vs labels.

Run from the repo root: apps/api/.venv/Scripts/python evals/matching/runner.py   (or `make eval`)
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api"))

from app.services.matching import JobInput, ProfileInput, score_job  # noqa: E402


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(x: list[float], y: list[float]) -> float:
    rx, ry = _ranks(x), _ranks(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    vx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    vy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return cov / (vx * vy) if vx and vy else 0.0


def ndcg(labels_in_rank_order: list[int], k: int) -> float:
    def dcg(ls: list[int]) -> float:
        return sum((2**rel - 1) / math.log2(i + 2) for i, rel in enumerate(ls[:k]))

    ideal = dcg(sorted(labels_in_rank_order, reverse=True))
    return dcg(labels_in_rank_order) / ideal if ideal else 0.0


def evaluate(dataset_path: Path) -> dict[str, Any]:
    data = json.loads(Path(dataset_path).read_text())
    p_at_5, ndcgs, rhos, pairs = [], [], [], 0
    for block in data["profiles"]:
        pr = block["profile"]
        profile = ProfileInput(
            skills=set(pr["skills"]),
            years_experience=pr["years_experience"],
            education_level=pr["education_level"],
            target_titles=pr["target_titles"],
            preferred_locations=pr["preferred_locations"],
            remote_preference=pr["remote_preference"],
            employment_types=pr["employment_types"],
            blocked_companies=pr["blocked_companies"],
        )
        scored = []
        for j in block["jobs"]:
            job = JobInput(
                title=j["title"],
                company=j["company"],
                location=j["location"],
                remote_policy=j["remote_policy"],
                employment_type=j["employment_type"],
                min_years=j["min_years"],
                required_skills=j["required_skills"],
                preferred_skills=j["preferred_skills"],
            )
            scored.append((score_job(profile, job).score, j["label"]))
            pairs += 1
        ranked = sorted(scored, key=lambda s: -s[0])
        p_at_5.append(sum(1 for _, lab in ranked[:5] if lab >= 2) / 5)
        ndcgs.append(ndcg([lab for _, lab in ranked], 10))
        rhos.append(spearman([s for s, _ in scored], [float(lab) for _, lab in scored]))
    return {
        "pairs": pairs,
        "precision_at_5": round(sum(p_at_5) / len(p_at_5), 4),
        "ndcg_at_10": round(sum(ndcgs) / len(ndcgs), 4),
        "spearman": round(sum(rhos) / len(rhos), 4),
    }


if __name__ == "__main__":
    metrics = evaluate(Path(__file__).with_name("dataset.json"))
    print(json.dumps(metrics, indent=2))
