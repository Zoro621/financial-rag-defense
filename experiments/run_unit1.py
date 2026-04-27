"""
experiments/run_unit1.py
Step 6: NLI guardrail experiments.

Adds the NLI guardrail as:
  1. Replacement for Output Regex in config (g) — high-FPR reduction target
  2. Addition to paper's best config (f)

Also runs stratified FPR measurement for Gap 7.
Outputs: results/tables/unit1_results.csv
"""

import csv
import json
import sys
from pathlib import Path
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ATTACKS_PATH, BENIGN_PATH, TABLES_DIR, RESULTS_DIR
from rag.pipeline import FinancialRAGPipeline, LLMWrapper
from evaluation.asr_judge import ASRJudge
from evaluation.fpr_evaluator import compute_stratified_fpr
from evaluation.latency_tracker import LatencyTracker
from evaluation.de_metric import compute_de_all_profiles


UNIT1_CONFIGS = {
    # Baseline reference (paper's best)
    "f_safe_input_guard_output_guard": {
        "prompt_type": "safe", "input_regex": False, "input_prompt_guard": True,
        "output_regex": False, "output_prompt_guard": True,
        "nli_guardrail": False, "retrieval_defense": False, "multiturn": False,
    },
    # Config (g) with NLI replacing regex output
    "g_safe_input_regex_output_NLI": {
        "prompt_type": "safe", "input_regex": True, "input_prompt_guard": False,
        "output_regex": False, "output_prompt_guard": False,
        "nli_guardrail": True, "retrieval_defense": False, "multiturn": False,
    },
    # Paper's best + NLI
    "f_plus_NLI": {
        "prompt_type": "safe", "input_regex": False, "input_prompt_guard": True,
        "output_regex": False, "output_prompt_guard": True,
        "nli_guardrail": True, "retrieval_defense": False, "multiturn": False,
    },
}


def load_jsonl(path):
    with open(path) as f:
        return [json.loads(l) for l in f]


def run_config(config_name, cfg, attacks, benign, judge, baseline_latency):
    llm      = LLMWrapper()
    pipeline = FinancialRAGPipeline(cfg, llm=llm)
    tracker  = LatencyTracker()

    n_success = 0
    for atk in tqdm(attacks, desc=f"  [{config_name}] attacks"):
        resp = pipeline.query(atk["prompt"])
        if not resp.blocked:
            if judge.evaluate(atk["prompt"], resp.text).success:
                n_success += 1

    asr_pct = n_success / max(len(attacks), 1) * 100

    benign_results = []
    for q in tqdm(benign, desc=f"  [{config_name}] benign"):
        resp = pipeline.query(q["query"])
        benign_results.append(resp)
        if not resp.blocked:
            tracker.record(resp.latency_s)

    fpr_stats = compute_stratified_fpr(benign_results, benign)
    lat_stats = tracker.summary()
    mean_lat  = lat_stats["mean_s"]

    de_scores = compute_de_all_profiles(
        asr_pct=asr_pct,
        fpr_pct=fpr_stats["aggregate_fpr"] * 100,
        latency_s=mean_lat,
        baseline_latency_s=baseline_latency,
    )

    row = {
        "defense_config":   config_name,
        "asr_pct":          round(asr_pct, 2),
        "latency_s":        round(mean_lat, 4),
        "fpr_pct":          round(fpr_stats["aggregate_fpr"] * 100, 2),
        "fpr_stratum_a":    round(fpr_stats["stratum_a_fpr"] * 100, 2),
        "fpr_stratum_b":    round(fpr_stats["stratum_b_fpr"] * 100, 2),
        "fpr_stratum_c":    round(fpr_stats["stratum_c_fpr"] * 100, 2),
        "max_disparity":    round(fpr_stats["max_disparity"] * 100, 2),
        **de_scores,
    }
    return row


def main():
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    attacks = load_jsonl(ATTACKS_PATH)
    benign  = load_jsonl(BENIGN_PATH)
    judge   = ASRJudge()

    # Use config (a) baseline latency from baseline_results.csv if available
    try:
        import pandas as pd
        baseline_df    = pd.read_csv(TABLES_DIR / "baseline_results.csv")
        baseline_row   = baseline_df[baseline_df["defense_config"] == "a_basic_no_filters"]
        baseline_latency = float(baseline_row["latency_s"].values[0])
    except Exception:
        baseline_latency = 1.0   # fallback

    all_rows = []
    for config_name, cfg in UNIT1_CONFIGS.items():
        print(f"\n{'='*60}")
        print(f" Unit 1 Config: {config_name}")
        print(f"{'='*60}")
        row = run_config(config_name, cfg, attacks, benign, judge, baseline_latency)
        all_rows.append(row)

    csv_path = TABLES_DIR / "unit1_results.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\n✅ Unit 1 results saved → {csv_path}")
    for row in all_rows:
        print(f"  {row['defense_config']}: ASR={row['asr_pct']}%, FPR={row['fpr_pct']}%, disparity={row['max_disparity']}%")


if __name__ == "__main__":
    main()
