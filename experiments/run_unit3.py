"""
experiments/run_unit3.py
Step 8: Adaptive attack evaluation.

Runs all 3 attack strategies × 3 defense configurations = 9 experiment runs.
Produces ASR degradation curves (Figure 3) and Defense Durability scores (Figure 4).

Defense configurations tested (per §9.2):
  1. Baseline (basic, no filters)
  2. Paper's best (safe + input guard + output guard)
  3. Paper's best + Unit 1 + Unit 2 (full proposed framework)

ESTIMATED COST: ~$10 at gpt-4o-mini rates.
Run with --dry-run to test with 5 prompts.
"""

import argparse
import json
import sys
from pathlib import Path

import openai

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ATTACKS_PATH, TABLES_DIR, LOGS_DIR
from rag.pipeline import FinancialRAGPipeline, LLMWrapper
from evaluation.adaptive_attack import AdaptiveAttacker, run_adaptive_attack_experiment
from evaluation.asr_judge import ASRJudge


DEFENSE_CONFIGS = {
    "baseline": {
        "prompt_type": "basic", "input_regex": False, "input_prompt_guard": False,
        "output_regex": False, "output_prompt_guard": False,
        "nli_guardrail": False, "retrieval_defense": False, "multiturn": False,
    },
    "papers_best": {
        "prompt_type": "safe", "input_regex": False, "input_prompt_guard": True,
        "output_regex": False, "output_prompt_guard": True,
        "nli_guardrail": False, "retrieval_defense": False, "multiturn": False,
    },
    "full_framework": {
        "prompt_type": "safe", "input_regex": False, "input_prompt_guard": True,
        "output_regex": False, "output_prompt_guard": True,
        "nli_guardrail": True, "retrieval_defense": True, "multiturn": False,
    },
}

STRATEGIES = ["paraphrase", "roleplay", "indirect"]


def load_jsonl(path):
    with open(path) as f:
        return [json.loads(l) for l in f]


def main(dry_run: bool = False):
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    attacks      = load_jsonl(ATTACKS_PATH)
    judge        = ASRJudge()
    oai_client   = openai.OpenAI()
    sample_size  = 10 if dry_run else 100
    max_iter     = 3  if dry_run else 10

    all_results = {}

    for config_name, cfg in DEFENSE_CONFIGS.items():
        all_results[config_name] = {}
        llm      = LLMWrapper()
        pipeline = FinancialRAGPipeline(cfg, llm=llm)

        for strategy in STRATEGIES:
            print(f"\n{'='*60}")
            print(f" Adaptive Attack | Config: {config_name} | Strategy: {strategy}")
            print(f"{'='*60}")

            attacker = AdaptiveAttacker(oai_client, strategy=strategy)
            checkpoint = LOGS_DIR / f"adaptive_{config_name}_{strategy}.json"

            result = run_adaptive_attack_experiment(
                attack_prompts=attacks,
                pipeline=pipeline,
                attacker=attacker,
                judge=judge,
                max_iterations=max_iter,
                sample_size=sample_size,
                checkpoint_path=checkpoint,
                checkpoint_every=10,
            )

            all_results[config_name][strategy] = {
                "asr_curve":          result["asr_curve"],
                "final_asr":          result["final_asr"],
                "iteration_to_5pct":  result["iteration_to_5pct"],
                "iteration_to_10pct": result["iteration_to_10pct"],
            }

            print(f"  Final ASR ({max_iter} iter): {result['final_asr']:.1f}%")
            if result["iteration_to_10pct"]:
                print(f"  Defense Durability: ASR>10% at iteration {result['iteration_to_10pct']}")
            else:
                print(f"  Defense Durability: ASR never exceeded 10% in {max_iter} iterations")

    # Save
    out_path = TABLES_DIR / "unit3_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\n✅ Unit 3 results saved → {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Run with 10 prompts and 3 iterations for quick testing")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
