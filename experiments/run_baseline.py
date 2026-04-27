"""
experiments/run_baseline.py
Step 5: Run the 8 key baseline defense configurations (Section 15, Step 5).

Configurations:
  a. Basic + No filters                        (baseline)
  b. Basic + Input RegEx + Output RegEx
  c. Basic + Input Guard + Output Guard
  d. Safe + No filters
  e. Safe + Input Guard + No output
  f. Safe + Input Guard + Output Guard         (paper's best)
  g. Safe + Input RegEx + Output RegEx         (high-FPR case)
  h. Safe + Both input + Output Guard

Outputs: results/tables/baseline_results.csv
"""

import csv
import json
import sys
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ATTACKS_PATH, BENIGN_PATH, RESULTS_DIR, TABLES_DIR
from rag.pipeline import FinancialRAGPipeline, LLMWrapper
from evaluation.asr_judge import ASRJudge
from evaluation.fpr_evaluator import compute_stratified_fpr
from evaluation.latency_tracker import LatencyTracker
from evaluation.de_metric import compute_de_all_profiles


CONFIGURATIONS = {
    "a_basic_no_filters": {
        "prompt_type": "basic", "input_regex": False, "input_prompt_guard": False,
        "output_regex": False, "output_prompt_guard": False,
        "nli_guardrail": False, "retrieval_defense": False, "multiturn": False,
    },
    "b_basic_input_regex_output_regex": {
        "prompt_type": "basic", "input_regex": True, "input_prompt_guard": False,
        "output_regex": True, "output_prompt_guard": False,
        "nli_guardrail": False, "retrieval_defense": False, "multiturn": False,
    },
    "c_basic_input_guard_output_guard": {
        "prompt_type": "basic", "input_regex": False, "input_prompt_guard": True,
        "output_regex": False, "output_prompt_guard": True,
        "nli_guardrail": False, "retrieval_defense": False, "multiturn": False,
    },
    "d_safe_no_filters": {
        "prompt_type": "safe", "input_regex": False, "input_prompt_guard": False,
        "output_regex": False, "output_prompt_guard": False,
        "nli_guardrail": False, "retrieval_defense": False, "multiturn": False,
    },
    "e_safe_input_guard_no_output": {
        "prompt_type": "safe", "input_regex": False, "input_prompt_guard": True,
        "output_regex": False, "output_prompt_guard": False,
        "nli_guardrail": False, "retrieval_defense": False, "multiturn": False,
    },
    "f_safe_input_guard_output_guard": {   # paper's best
        "prompt_type": "safe", "input_regex": False, "input_prompt_guard": True,
        "output_regex": False, "output_prompt_guard": True,
        "nli_guardrail": False, "retrieval_defense": False, "multiturn": False,
    },
    "g_safe_input_regex_output_regex": {   # high-FPR case
        "prompt_type": "safe", "input_regex": True, "input_prompt_guard": False,
        "output_regex": True, "output_prompt_guard": False,
        "nli_guardrail": False, "retrieval_defense": False, "multiturn": False,
    },
    "h_safe_both_input_output_guard": {
        "prompt_type": "safe", "input_regex": True, "input_prompt_guard": True,
        "output_regex": False, "output_prompt_guard": True,
        "nli_guardrail": False, "retrieval_defense": False, "multiturn": False,
    },
}


def load_jsonl(path: Path) -> list:
    with open(path) as f:
        return [json.loads(line) for line in f]


def run_config(config_name: str, cfg: dict, attacks: list, benign: list,
               judge: ASRJudge, baseline_latency: float | None) -> dict:

    llm      = LLMWrapper()
    pipeline = FinancialRAGPipeline(cfg, llm=llm)
    tracker  = LatencyTracker()

    # ---- ASR: run on attack prompts ----------------------------------- #
    n_attacks  = len(attacks)
    n_success  = 0
    for atk in tqdm(attacks, desc=f"  [{config_name}] attacks"):
        resp = pipeline.query(atk["prompt"])
        if not resp.blocked:
            result = judge.evaluate(atk["prompt"], resp.text)
            if result.success:
                n_success += 1

    asr_pct = n_success / max(n_attacks, 1) * 100

    # ---- FPR + Latency: run on benign queries ------------------------ #
    benign_results = []
    for q in tqdm(benign, desc=f"  [{config_name}] benign"):
        resp = pipeline.query(q["query"])
        benign_results.append(resp)
        if not resp.blocked:
            tracker.record(resp.latency_s)

    fpr_stats = compute_stratified_fpr(benign_results, benign)
    lat_stats = tracker.summary()
    mean_lat  = lat_stats["mean_s"]

    # ---- DE metric --------------------------------------------------- #
    if baseline_latency is None:
        baseline_latency = mean_lat   # first config is baseline

    de_scores = compute_de_all_profiles(
        asr_pct=asr_pct,
        fpr_pct=fpr_stats["aggregate_fpr"] * 100,
        latency_s=mean_lat,
        baseline_latency_s=baseline_latency,
    )

    row = {
        "defense_config":              config_name,
        "asr_pct":                     round(asr_pct, 2),
        "asr_reduction_pct":           0.0,   # filled after all configs run
        "latency_s":                   round(mean_lat, 4),
        "latency_overhead_pct":        0.0,   # filled after
        "fpr_pct":                     round(fpr_stats["aggregate_fpr"] * 100, 2),
        "fpr_stratum_a":               round(fpr_stats["stratum_a_fpr"] * 100, 2),
        "fpr_stratum_b":               round(fpr_stats["stratum_b_fpr"] * 100, 2),
        "fpr_stratum_c":               round(fpr_stats["stratum_c_fpr"] * 100, 2),
        **de_scores,
    }
    return row, baseline_latency


def main():
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    attacks = load_jsonl(ATTACKS_PATH)
    benign  = load_jsonl(BENIGN_PATH)
    judge   = ASRJudge()

    all_rows: list[dict] = []
    baseline_asr:     float | None = None
    baseline_latency: float | None = None

    for config_name, cfg in CONFIGURATIONS.items():
        print(f"\n{'='*60}")
        print(f" Config: {config_name}")
        print(f"{'='*60}")
        row, baseline_latency = run_config(
            config_name, cfg, attacks, benign, judge, baseline_latency
        )
        all_rows.append(row)
        if baseline_asr is None:
            baseline_asr = row["asr_pct"]

    # ---- Post-process relative metrics -------------------------------- #
    for row in all_rows:
        row["asr_reduction_pct"] = round(
            ((baseline_asr - row["asr_pct"]) / max(baseline_asr, 1e-6)) * 100, 2
        )
        row["latency_overhead_pct"] = round(
            ((row["latency_s"] - baseline_latency) / max(baseline_latency, 1e-6)) * 100, 2
        )

    # ---- Save CSV ----------------------------------------------------- #
    csv_path = TABLES_DIR / "baseline_results.csv"
    fieldnames = list(all_rows[0].keys())
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\n✅ Baseline results saved → {csv_path}")
    for row in all_rows:
        print(f"  {row['defense_config']}: ASR={row['asr_pct']}%, FPR={row['fpr_pct']}%")


if __name__ == "__main__":
    main()
