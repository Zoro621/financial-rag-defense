"""
experiments/run_unit4.py
Step 9: Multi-turn attack evaluation (Section 10).

Generates 50 multi-turn sequences then evaluates them through:
  - pipeline with history enabled (multiturn=True)
  - pipeline with history disabled (turn 3 in isolation)

Key output: context_dependent_asr
"""

import json
import sys
from pathlib import Path

import openai
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ATTACKS_PATH, MULTITURN_PATH, TABLES_DIR, RESULTS_DIR, HF_TOKEN, PROVIDER_ENDPOINTS
import config
from rag.pipeline import FinancialRAGPipeline, LLMWrapper
from evaluation.multiturn_attack import MultiTurnEvaluator
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


def load_jsonl(path):
    if not Path(path).exists():
        return []
    with open(path) as f:
        return [json.loads(l) for l in f]


def _ensure_string(data) -> str:
    if isinstance(data, str):
        return data
    elif isinstance(data, dict):
        return " ".join(str(v) for v in data.values())
    return str(data)


def evaluate_config(config_name, cfg, sequences, judge, checkpoint_dir):
    llm = LLMWrapper()

    cfg_with_history    = {**cfg, "multiturn": True}
    cfg_without_history = {**cfg, "multiturn": False}

    pipeline_h  = FinancialRAGPipeline(cfg_with_history,    llm=llm)
    pipeline_nh = FinancialRAGPipeline(cfg_without_history, llm=llm)

    ckpt_path = checkpoint_dir / f"{config_name}.jsonl"
    completed = load_jsonl(ckpt_path) if ckpt_path.exists() else []
    remaining = sequences[len(completed):]

    with open(ckpt_path, "a") as f:
        for seq in tqdm(remaining, desc=f"  [{config_name}]"):
            t1 = _ensure_string(seq.get("turn_1", ""))
            t2 = _ensure_string(seq.get("turn_2", ""))
            t3 = _ensure_string(seq.get("turn_3", ""))

            pipeline_h.reset()

            # With history
            r1 = pipeline_h.query(t1)
            r2 = pipeline_h.query(t2)
            r3_with = pipeline_h.query(t3)

            success_with = False
            if not r3_with.blocked:
                success_with = judge.evaluate(t3, r3_with.text).success

            # Without history (turn 3 in isolation)
            r3_no = pipeline_nh.query(t3)
            success_no = False
            if not r3_no.blocked:
                success_no = judge.evaluate(t3, r3_no.text).success

            result = {
                "seq_id": seq.get("id", 0),
                "turn1_blocked": r1.blocked,
                "turn2_blocked": r2.blocked,
                "turn3_blocked_history": r3_with.blocked,
                "turn3_blocked_no_history": r3_no.blocked,
                "turn3_success_history": success_with,
                "turn3_success_no_history": success_no,
            }
            completed.append(result)
            f.write(json.dumps(result) + "\n")
            f.flush()

    # Compute metrics from all completed results
    n = len(sequences)
    metrics = {
        "turn1_blocked":           sum(1 for c in completed if c["turn1_blocked"]),
        "turn2_blocked":           sum(1 for c in completed if c["turn2_blocked"]),
        "turn3_blocked_history":   sum(1 for c in completed if c["turn3_blocked_history"]),
        "turn3_blocked_no_history": sum(1 for c in completed if c["turn3_blocked_no_history"]),
        "turn3_success_history":   sum(1 for c in completed if c["turn3_success_history"]),
        "turn3_success_no_history": sum(1 for c in completed if c["turn3_success_no_history"]),
        "n_sequences":             n,
    }

    asr_history    = metrics["turn3_success_history"]    / max(n, 1) * 100
    asr_no_history = metrics["turn3_success_no_history"] / max(n, 1) * 100

    metrics.update({
        "asr_with_history_pct":    asr_history,
        "asr_no_history_pct":      asr_no_history,
        "context_dependent_asr":   asr_history - asr_no_history,
        "turn1_block_rate_pct":    metrics["turn1_blocked"] / max(n, 1) * 100,
        "turn2_block_rate_pct":    metrics["turn2_blocked"] / max(n, 1) * 100,
        "turn3_block_rate_with_history_pct":    metrics["turn3_blocked_history"]    / max(n, 1) * 100,
        "turn3_block_rate_no_history_pct":      metrics["turn3_blocked_no_history"] / max(n, 1) * 100,
    })

    return metrics


def main():
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_dir = RESULTS_DIR / "checkpoints" / "run_unit4"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    attacks = load_jsonl(ATTACKS_PATH)

    if config.ATTACKER_LLM_PROVIDER == "local":
        from rag.pipeline import LLMWrapper
        oai_client = LLMWrapper("local", hf_token=config.HF_TOKEN)
    else:
        oai_client = openai.OpenAI(
            api_key=config.HF_TOKEN,
            base_url=config.PROVIDER_ENDPOINTS.get(config.ATTACKER_LLM_PROVIDER)
        )

    judge     = ASRJudge()
    evaluator = MultiTurnEvaluator(llm_client=oai_client, judge=judge)

    # Generate or load sequences
    if MULTITURN_PATH.exists():
        sequences = load_jsonl(MULTITURN_PATH)
    else:
        behaviors = [a["behavior"] for a in attacks[:50]]
        sequences = evaluator.generate_sequences(behaviors)

    print(f"Evaluating {len(sequences)} multi-turn sequences ...\n")

    all_results = {}
    for config_name, cfg in DEFENSE_CONFIGS.items():
        print(f"\n{'='*60}")
        print(f" Multi-Turn | Config: {config_name}")
        print(f"{'='*60}")

        metrics = evaluate_config(config_name, cfg, sequences, judge, checkpoint_dir)
        all_results[config_name] = metrics

        print(f"  ASR with history:    {metrics['asr_with_history_pct']:.1f}%")
        print(f"  ASR without history: {metrics['asr_no_history_pct']:.1f}%")
        print(f"  Context-dependent ASR: {metrics['context_dependent_asr']:.1f}%")

    out_path = TABLES_DIR / "unit4_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\n[OK] Unit 4 results saved -> {out_path}")


if __name__ == "__main__":
    main()
