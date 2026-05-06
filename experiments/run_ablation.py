"""
experiments/run_ablation.py
All 6 ablation studies (Section 13).

Ablation 1: NLI model size   (MiniLM vs deberta-base vs deberta-large)
Ablation 2: NLI threshold    (0.5 / 0.6 / 0.7 / 0.8 / 0.9)
Ablation 3: Grounding threshold (0.25 / 0.30 / 0.35 / 0.40 / 0.45)
Ablation 4: Adaptive attack strategy comparison
Ablation 5: Adaptive attack iteration budget
Ablation 6: Multi-turn depth (2-turn vs 3-turn)

Output: results/tables/ablation_summary.csv
"""

import csv
import json
import sys
import time
from pathlib import Path

import numpy as np
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    ATTACKS_PATH, BENIGN_PATH, TABLES_DIR, LOGS_DIR, RESULTS_DIR,
    NLI_MODEL, EMBEDDING_MODEL,
)
from rag.pipeline import FinancialRAGPipeline, LLMWrapper
from defenses.nli_guardrail import NLISemanticGuardrail
from defenses.retrieval_defense import ResponseGroundingVerifier
from evaluation.fpr_evaluator import compute_aggregate_fpr, compute_stratified_fpr
from evaluation.asr_judge import ASRJudge
from evaluation.latency_tracker import LatencyTracker

ABLATION_ROWS = []


def _load_checkpoint(checkpoint_path):
    """Load completed ablation rows from checkpoint JSONL."""
    if not checkpoint_path.exists():
        return []
    with open(checkpoint_path) as f:
        return [json.loads(l) for l in f]


def _save_row(checkpoint_path, row):
    """Append a single ablation row to the checkpoint JSONL."""
    with open(checkpoint_path, "a") as f:
        f.write(json.dumps(row) + "\n")
        f.flush()


def _is_done(completed, ablation_id, value):
    """Check if a specific ablation_id + value combo is already in checkpoint."""
    return any(c["ablation_id"] == ablation_id and c["value"] == value for c in completed)

BASE_CONFIG = {
    "prompt_type": "safe", "input_regex": False, "input_prompt_guard": True,
    "output_regex": False, "output_prompt_guard": True,
    "nli_guardrail": False, "retrieval_defense": False, "multiturn": False,
}


def load_jsonl(path):
    with open(path) as f:
        return [json.loads(l) for l in f]


def evaluate_nli_guardrail(nli_model_name, threshold, attacks, benign, judge, baseline_latency):
    """Re-instantiate guardrail with a given model and threshold and evaluate."""
    from sentence_transformers import CrossEncoder
    guardrail = NLISemanticGuardrail(threshold=threshold, model_name=nli_model_name)

    # Quick FPR evaluation
    fpr_blocked = 0
    total_lat = []
    for q in benign[:100]:
        t0 = time.perf_counter()
        result = guardrail.classify(q["query"])
        total_lat.append(time.perf_counter() - t0)
        if result["blocked"]:
            fpr_blocked += 1

    fpr_pct = fpr_blocked / 100 * 100
    mean_lat = np.mean(total_lat)

    # Quick ASR estimation using sample of 30 attacks
    n_success = 0
    llm = LLMWrapper()
    pipeline = FinancialRAGPipeline(
        {**BASE_CONFIG, "nli_guardrail": True}, llm=llm
    )
    # Monkey-patch the guardrail onto the pipeline
    pipeline._nli_guardrail = guardrail

    sample = attacks[:30]
    for atk in sample:
        resp = pipeline.query(atk["prompt"])
        if not resp.blocked and judge.evaluate(atk["prompt"], resp.text).success:
            n_success += 1

    asr_pct = n_success / max(len(sample), 1) * 100

    return {"fpr_pct": round(fpr_pct, 2), "asr_pct": round(asr_pct, 2),
            "latency_s": round(mean_lat, 4)}


# =========================================================================== #
#  Ablation 1 — NLI Model Size
# =========================================================================== #
def ablation1_nli_model_size(attacks, benign, judge, baseline_latency, ckpt_path, completed):
    print("\n=== Ablation 1: NLI Model Size ===")
    models = [
        "cross-encoder/nli-MiniLM2-L6-H768",
        "cross-encoder/nli-deberta-v3-base",
        "cross-encoder/nli-deberta-v3-large",
    ]
    for model_name in models:
        short_name = model_name.split("/")[-1]
        if _is_done(completed, "1", short_name):
            print(f"  [Resume] Skipping {model_name} (already done)")
            continue
        print(f"  Testing {model_name} ...")
        try:
            m = evaluate_nli_guardrail(model_name, 0.7, attacks, benign, judge, baseline_latency)
            row = {
                "ablation_id":    "1",
                "component":      "NLI Guardrail",
                "variable":       "model_name",
                "value":          short_name,
                "asr_pct":        m["asr_pct"],
                "fpr_pct":        m["fpr_pct"],
                "latency_s":      m["latency_s"],
                "de_high_security": "",
                "finding":        f"FPR={m['fpr_pct']}%, lat={m['latency_s']:.3f}s",
            }
            ABLATION_ROWS.append(row)
            _save_row(ckpt_path, row)
        except Exception as e:
            print(f"  SKIP {model_name}: {e}")


# =========================================================================== #
#  Ablation 2 — NLI Threshold
# =========================================================================== #
def ablation2_nli_threshold(attacks, benign, judge, baseline_latency, ckpt_path, completed):
    print("\n=== Ablation 2: NLI Threshold ===")
    for threshold in [0.5, 0.6, 0.7, 0.8, 0.9]:
        val = str(threshold)
        if _is_done(completed, "2", val):
            print(f"  [Resume] Skipping threshold={threshold} (already done)")
            continue
        print(f"  threshold={threshold}")
        m = evaluate_nli_guardrail(NLI_MODEL, threshold, attacks, benign, judge, baseline_latency)
        row = {
            "ablation_id":    "2",
            "component":      "NLI Guardrail",
            "variable":       "threshold",
            "value":          val,
            "asr_pct":        m["asr_pct"],
            "fpr_pct":        m["fpr_pct"],
            "latency_s":      m["latency_s"],
            "de_high_security": "",
            "finding":        f"FPR={m['fpr_pct']}%, ASR={m['asr_pct']}%",
        }
        ABLATION_ROWS.append(row)
        _save_row(ckpt_path, row)


# =========================================================================== #
#  Ablation 3 — Grounding Threshold
# =========================================================================== #
def ablation3_grounding_threshold(attacks, benign, judge, baseline_latency, ckpt_path, completed):
    print("\n=== Ablation 3: Grounding Threshold ===")
    from sentence_transformers import SentenceTransformer
    emb_model = SentenceTransformer(EMBEDDING_MODEL)

    for threshold in [0.25, 0.30, 0.35, 0.40, 0.45]:
        val = str(threshold)
        if _is_done(completed, "3", val):
            print(f"  [Resume] Skipping threshold={threshold} (already done)")
            continue
        verifier = ResponseGroundingVerifier(emb_model, threshold=threshold)
        fpr_blocked = 0

        llm = LLMWrapper()
        pipeline = FinancialRAGPipeline({"prompt_type": "basic"}, llm=llm)

        for q in benign[:50]:
            resp = pipeline.query(q["query"])
            if not resp.blocked and resp.retrieved_chunks:
                result = verifier.verify(resp.text, resp.retrieved_chunks)
                if result["flagged"]:
                    fpr_blocked += 1

        fpr_pct = fpr_blocked / 50 * 100
        print(f"  threshold={threshold}: FPR={fpr_pct:.1f}%")

        row = {
            "ablation_id":    "3",
            "component":      "Grounding Verifier",
            "variable":       "threshold",
            "value":          val,
            "asr_pct":        "",
            "fpr_pct":        round(fpr_pct, 2),
            "latency_s":      "",
            "de_high_security": "",
            "finding":        f"FPR on benign={fpr_pct:.1f}%",
        }
        ABLATION_ROWS.append(row)
        _save_row(ckpt_path, row)


# =========================================================================== #
#  Ablations 4-5 — Load from Unit 3 results
# =========================================================================== #
def ablations_4_5_from_unit3():
    print("\n=== Ablations 4 & 5: From Unit 3 Results ===")
    unit3_path = TABLES_DIR / "unit3_results.json"
    if not unit3_path.exists():
        print("  unit3_results.json not found — run run_unit3.py first")
        return

    with open(unit3_path) as f:
        unit3 = json.load(f)

    # Ablation 4: Strategy comparison (papers_best config)
    for strategy in ["paraphrase", "roleplay", "indirect"]:
        try:
            data = unit3["papers_best"][strategy]
            ABLATION_ROWS.append({
                "ablation_id":    "4",
                "component":      "Adaptive Attacker",
                "variable":       "strategy",
                "value":          strategy,
                "asr_pct":        round(data["final_asr"], 2),
                "fpr_pct":        "",
                "latency_s":      "",
                "de_high_security": "",
                "finding":        f"final_asr={data['final_asr']:.1f}%, "
                                  f"iter_to_10pct={data['iteration_to_10pct']}",
            })
        except Exception as e:
            print(f"  [Error] Ablation 4 failed on {strategy}: {e}")

    # Ablation 5: Iteration budget (full_framework, paraphrase)
    try:
        data = unit3["full_framework"]["paraphrase"]
        curve = data["asr_curve"]
        for i in [1, 3, 5, 7, 10]:
            asr_at_i = curve[i - 1] if i - 1 < len(curve) else curve[-1]
            ABLATION_ROWS.append({
                "ablation_id":    "5",
                "component":      "Adaptive Attacker",
                "variable":       "iteration",
                "value":          str(i),
                "asr_pct":        round(asr_at_i, 2),
                "fpr_pct":        "",
                "latency_s":      "",
                "de_high_security": "",
                "finding":        f"Cumulative ASR at iter {i}: {asr_at_i:.1f}%",
            })
    except Exception as e:
            print(f"  [Error] Ablation 5 failed: {e}")


# =========================================================================== #
#  Ablation 6 — Multi-turn depth
# =========================================================================== #
def ablation6_multiturn_depth():
    print("\n=== Ablation 6: Multi-Turn Depth ===")
    unit4_path = TABLES_DIR / "unit4_results.json"
    if not unit4_path.exists():
        print("  unit4_results.json not found — run run_unit4.py first")
        return

    with open(unit4_path) as f:
        unit4 = json.load(f)

    # Compare context_dependent_asr for papers_best (as proxy for depth effect)
    try:
        m = unit4["papers_best"]
        ABLATION_ROWS.append({
            "ablation_id":    "6",
            "component":      "Multi-Turn",
            "variable":       "depth",
            "value":          "3",
            "asr_pct":        round(m["asr_with_history_pct"], 2),
            "fpr_pct":        "",
            "latency_s":      "",
            "de_high_security": "",
            "finding":        f"context_dependent_asr={m['context_dependent_asr']:.1f}%",
        })
    except Exception as e:
        print(f"  [Error] Ablation 6 failed: {e}")


# =========================================================================== #
#  Main
# =========================================================================== #
def main():
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_dir = RESULTS_DIR / "checkpoints" / "run_ablation"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = checkpoint_dir / "ablation_rows.jsonl"

    # Load any previously completed ablation rows
    completed = _load_checkpoint(ckpt_path)
    ABLATION_ROWS.extend(completed)

    attacks = load_jsonl(ATTACKS_PATH)
    benign  = load_jsonl(BENIGN_PATH)
    judge   = ASRJudge()

    # Load baseline latency from results if available
    baseline_latency = 1.0
    try:
        csv_path = TABLES_DIR / "baseline_results.csv"
        if csv_path.exists():
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("defense_config") == "a_basic_no_filters":
                        baseline_latency = float(row.get("latency_s", 1.0))
                        break
    except Exception:
        pass

    ablation1_nli_model_size(attacks, benign, judge, baseline_latency, ckpt_path, completed)
    ablation2_nli_threshold(attacks, benign, judge, baseline_latency, ckpt_path, completed)
    ablation3_grounding_threshold(attacks, benign, judge, baseline_latency, ckpt_path, completed)
    ablations_4_5_from_unit3()
    ablation6_multiturn_depth()

    # Save final CSV
    csv_path = TABLES_DIR / "ablation_summary.csv"
    fieldnames = ["ablation_id", "component", "variable", "value",
                  "asr_pct", "fpr_pct", "latency_s", "de_high_security", "finding"]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(ABLATION_ROWS)

    print(f"\n[OK] Ablation summary saved -> {csv_path}")


if __name__ == "__main__":
    main()
