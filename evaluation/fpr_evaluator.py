"""
evaluation/fpr_evaluator.py
Aggregate and stratified False Positive Rate (FPR) measurement.
Addresses Gap 7 — Demographic FPR disparity across language-complexity strata.
"""

from typing import List


def compute_aggregate_fpr(results: List[dict]) -> float:
    """
    Compute aggregate FPR from pipeline results on benign queries.

    Args:
        results: list of dicts, each must have "blocked" key (bool).

    Returns:
        FPR as a fraction (0.0 – 1.0).
    """
    if not results:
        return 0.0
    blocked = sum(1 for r in results if r.get("blocked", False))
    return blocked / len(results)


def compute_stratified_fpr(
    results: List[dict],
    stratified_queries: List[dict],
) -> dict:
    """
    Compute FPR separately for each stratum (A/B/C) defined by Flesch score.

    Args:
        results:             list of pipeline output objects (SuccessResponse or BlockedResponse)
                             in the same order as stratified_queries.
        stratified_queries:  list of query dicts, each must have a "stratum" key.

    Returns:
        {
            "aggregate_fpr":  float,
            "stratum_a_fpr":  float,
            "stratum_b_fpr":  float,
            "stratum_c_fpr":  float,
            "max_disparity":  float,
            "stratum_counts": {"A": int, "B": int, "C": int},
        }
    """
    assert len(results) == len(stratified_queries), (
        "results and stratified_queries must have the same length"
    )

    strata: dict[str, dict] = {
        "A": {"total": 0, "blocked": 0},
        "B": {"total": 0, "blocked": 0},
        "C": {"total": 0, "blocked": 0},
    }

    for response, query in zip(results, stratified_queries):
        stratum = query.get("stratum", "B").upper()
        if stratum not in strata:
            stratum = "B"   # default

        strata[stratum]["total"]   += 1
        # Support both BlockedResponse objects and plain dicts
        is_blocked = (
            getattr(response, "blocked", None)
            if hasattr(response, "blocked")
            else response.get("blocked", False)
        )
        if is_blocked:
            strata[stratum]["blocked"] += 1

    def safe_fpr(s: dict) -> float:
        return (s["blocked"] / s["total"]) if s["total"] > 0 else 0.0

    fpr_a = safe_fpr(strata["A"])
    fpr_b = safe_fpr(strata["B"])
    fpr_c = safe_fpr(strata["C"])

    valid_fprs = [
        v for v, s in zip([fpr_a, fpr_b, fpr_c], ["A", "B", "C"])
        if strata[s]["total"] > 0
    ]
    max_disparity = (max(valid_fprs) - min(valid_fprs)) if len(valid_fprs) > 1 else 0.0

    all_blocked = sum(s["blocked"] for s in strata.values())
    all_total   = sum(s["total"]   for s in strata.values())
    agg_fpr     = (all_blocked / all_total) if all_total > 0 else 0.0

    return {
        "aggregate_fpr":  agg_fpr,
        "stratum_a_fpr":  fpr_a,
        "stratum_b_fpr":  fpr_b,
        "stratum_c_fpr":  fpr_c,
        "max_disparity":  max_disparity,
        "stratum_counts": {k: strata[k]["total"] for k in "ABC"},
    }
