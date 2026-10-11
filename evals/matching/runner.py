"""Matching engine evaluation runner: Precision@K, NDCG, and Rank Correlation."""

import json
import math
import os
from typing import Dict, List, Tuple

from apps.api.services.matching_service import normalize_skill


def dcg_at_k(scores: List[float], k: int) -> float:
    """Computes Discounted Cumulative Gain at rank k."""
    dcg = 0.0
    for i, s in enumerate(scores[:k]):
        dcg += (2.0**s - 1.0) / math.log2(i + 2.0)
    return dcg


def ndcg_at_k(predicted_scores: List[Tuple[float, float]], k: int = 10) -> float:
    """
    Computes Normalized Discounted Cumulative Gain at rank k.
    predicted_scores: list of (predicted_model_score, ground_truth_relevance)
    """
    # Sort by predicted model score descending
    ranked_by_pred = sorted(predicted_scores, key=lambda x: x[0], reverse=True)
    actual_relevances = [item[1] for item in ranked_by_pred]
    actual_dcg = dcg_at_k(actual_relevances, k)

    # Ideal DCG sorted by ground truth relevance
    ideal_relevances = sorted([item[1] for item in predicted_scores], reverse=True)
    ideal_dcg = dcg_at_k(ideal_relevances, k)

    if ideal_dcg == 0:
        return 1.0
    return actual_dcg / ideal_dcg


def precision_at_k(
    predicted_scores: List[Tuple[float, float]], k: int = 10, threshold: float = 2.0
) -> float:
    """Computes Precision@K where relevant items have ground_truth_relevance >= threshold."""
    ranked = sorted(predicted_scores, key=lambda x: x[0], reverse=True)[:k]
    if not ranked:
        return 0.0
    relevant_count = sum(1 for _, gt in ranked if gt >= threshold)
    return relevant_count / len(ranked)


def spearman_rank_correlation(x: List[float], y: List[float]) -> float:
    """Computes Spearman rank correlation coefficient between model scores and ground truth."""
    n = len(x)
    if n < 2:
        return 1.0

    def get_ranks(arr: List[float]) -> List[float]:
        sorted_indices = sorted(range(n), key=lambda idx: arr[idx])
        ranks = [0.0] * n
        for rank, idx in enumerate(sorted_indices):
            ranks[idx] = float(rank + 1)
        return ranks

    rank_x = get_ranks(x)
    rank_y = get_ranks(y)

    d_squared_sum = sum((rx - ry) ** 2 for rx, ry in zip(rank_x, rank_y))
    rho = 1.0 - (6.0 * d_squared_sum) / (n * (n**2 - 1))
    return round(rho, 4)


def evaluate_matching_engine() -> Dict[str, float]:
    """Runs the evaluation harness on the 50 synthetic labeled pairs."""
    data_path = os.path.join(os.path.dirname(__file__), "dataset.json")
    with open(data_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    results: List[Tuple[float, float]] = []
    preds: List[float] = []
    ground_truths: List[float] = []

    for item in dataset:
        cand_skills = set(normalize_skill(s) for s in item["candidate_skills"])
        req_skills = [normalize_skill(s) for s in item["job_required_skills"]]
        pref_skills = [normalize_skill(s) for s in item["job_preferred_skills"]]

        matched_req = sum(1 for s in req_skills if s in cand_skills)
        matched_pref = sum(1 for s in pref_skills if s in cand_skills)

        # Re-create deterministic score computation
        req_score = (matched_req / (len(req_skills) or 1)) * 100
        pref_score = (matched_pref / (len(pref_skills) or 1)) * 100 if pref_skills else 100
        skills_score = (req_score * 0.7) + (pref_score * 0.3)

        # Hard filters check
        if item["candidate_remote"] == "remote" and item["job_remote_type"] == "on-site":
            predicted_score = 0.0
        elif item["candidate_min_salary"] > item["job_salary_max"]:
            predicted_score = 0.0
        else:
            predicted_score = (skills_score * 0.5) + 40.0

        gt = float(item["ground_truth_relevance"])
        results.append((predicted_score, gt))
        preds.append(predicted_score)
        ground_truths.append(gt)

    ndcg = round(ndcg_at_k(results, k=10), 4)
    prec_10 = round(precision_at_k(results, k=10, threshold=2.0), 4)
    spearman = spearman_rank_correlation(preds, ground_truths)

    metrics = {
        "dataset_size": len(dataset),
        "ndcg_at_10": ndcg,
        "precision_at_10": prec_10,
        "spearman_correlation": spearman,
    }
    return metrics


if __name__ == "__main__":
    report = evaluate_matching_engine()
    print("=== Matching Engine Eval Report ===")
    for k, v in report.items():
        print(f"{k}: {v}")
