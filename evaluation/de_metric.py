"""
evaluation/de_metric.py
Defense Efficiency (DE) metric — replicates the paper's formula and extends
it with a 4th regulatory-compliance weighting profile (Unit 5 / Gap 4).

DE = α × (1 - ASR/100) + β × (1 - FPR/100) + γ × (1 - norm_latency)

Where:
  α = weight for ASR reduction (security)
  β = weight for FPR reduction (usability)
  γ = weight for latency (efficiency)
  norm_latency = latency_s / baseline_latency_s   (capped at 1.0 for extreme cases)
"""

from pathlib import Path
from typing import Dict
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DE_WEIGHTS


def compute_de(
    asr_pct: float,
    fpr_pct: float,
    latency_s: float,
    baseline_latency_s: float,
    weights: Dict[str, float],
) -> float:
    """
    Compute Defense Efficiency for a single weighting profile.

    Args:
        asr_pct:            Attack Success Rate (0–100)
        fpr_pct:            False Positive Rate (0–100)
        latency_s:          Mean response latency (seconds)
        baseline_latency_s: No-defense baseline latency (seconds)
        weights:            {"alpha": float, "beta": float, "gamma": float}

    Returns:
        DE score in range [0, 1]. Higher = more efficient.
    """
    alpha = weights["alpha"]
    beta  = weights["beta"]
    gamma = weights["gamma"]

    norm_latency = min(latency_s / max(baseline_latency_s, 1e-6), 1.0)

    de = (
        alpha * (1 - asr_pct / 100)
        + beta  * (1 - fpr_pct / 100)
        + gamma * (1 - norm_latency)
    )
    return round(float(de), 6)


def compute_de_all_profiles(
    asr_pct: float,
    fpr_pct: float,
    latency_s: float,
    baseline_latency_s: float,
    profiles: Dict[str, Dict] | None = None,
) -> Dict[str, float]:
    """
    Compute DE for all four weighting profiles.

    Returns:
        {
            "de_high_security":         float,
            "de_balanced":              float,
            "de_high_frequency":        float,
            "de_regulatory_compliance": float,
        }
    """
    profiles = profiles or DE_WEIGHTS
    return {
        f"de_{name}": compute_de(
            asr_pct, fpr_pct, latency_s, baseline_latency_s, w
        )
        for name, w in profiles.items()
    }


def sensitivity_analysis(
    results_rows: list[dict],
    baseline_latency_s: float,
) -> Dict[str, list]:
    """
    Run all four DE profiles over all result rows.
    Returns a dict mapping profile_name → list of (config_name, de_score) tuples,
    sorted descending by DE score.

    Also flags configs whose rankings change across profiles (key finding for Gap 4).

    Args:
        results_rows: list of result dicts with keys:
            "defense_config", "asr_pct", "fpr_pct", "latency_s"
        baseline_latency_s: float

    Returns:
        {
            "rankings_by_profile": {profile: [(config_name, de_score), ...], ...},
            "ranking_changes":     [(config_name, {profile: rank}), ...],
        }
    """
    profile_names = list(DE_WEIGHTS.keys())
    rankings: Dict[str, list] = {p: [] for p in profile_names}

    for row in results_rows:
        de_scores = compute_de_all_profiles(
            asr_pct=row["asr_pct"],
            fpr_pct=row["fpr_pct"],
            latency_s=row["latency_s"],
            baseline_latency_s=baseline_latency_s,
        )
        for name in profile_names:
            rankings[name].append((row["defense_config"], de_scores[f"de_{name}"]))

    # Sort each profile's ranking
    sorted_rankings = {
        name: sorted(pairs, key=lambda x: x[1], reverse=True)
        for name, pairs in rankings.items()
    }

    # Identify configs where top-3 rank differs across profiles
    config_ranks: Dict[str, Dict[str, int]] = {}
    for name, ranking in sorted_rankings.items():
        for rank, (config, _) in enumerate(ranking, start=1):
            config_ranks.setdefault(config, {})[name] = rank

    ranking_changes = [
        (config, ranks)
        for config, ranks in config_ranks.items()
        if max(ranks.values()) - min(ranks.values()) > 2
    ]

    return {
        "rankings_by_profile": sorted_rankings,
        "ranking_changes":     ranking_changes,
    }
