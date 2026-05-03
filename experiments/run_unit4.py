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

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ATTACKS_PATH, MULTITURN_PATH, TABLES_DIR, LOGS_DIR, HF_TOKEN, PROVIDER_ENDPOINTS
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


def main():
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    attacks    = load_jsonl(ATTACKS_PATH)
    
    if config.ATTACKER_LLM_PROVIDER == "local":
        from rag.pipeline import LLMWrapper
        print("[System] Initializing local LLM for Multi-turn evaluation...")
        oai_client = LLMWrapper("local", hf_token=config.HF_TOKEN)
    else:
        oai_client = openai.OpenAI(
            api_key=config.HF_TOKEN,
            base_url=config.PROVIDER_ENDPOINTS.get(config.ATTACKER_LLM_PROVIDER)
        )
        
    judge      = ASRJudge()
    evaluator  = MultiTurnEvaluator(llm_client=oai_client, judge=judge)

    # Generate or load sequences
    if MULTITURN_PATH.exists():
        print(f"Loading existing sequences from {MULTITURN_PATH} …")
        sequences = load_jsonl(MULTITURN_PATH)
    else:
        behaviors = [a["behavior"] for a in attacks[:50]]
        sequences = evaluator.generate_sequences(behaviors)

    print(f"Evaluating {len(sequences)} multi-turn sequences …\n")

    all_results = {}
    for config_name, cfg in DEFENSE_CONFIGS.items():
        print(f"\n{'='*60}")
        print(f" Multi-Turn | Config: {config_name}")
        print(f"{'='*60}")

        llm = LLMWrapper()

        cfg_with_history    = {**cfg, "multiturn": True}
        cfg_without_history = {**cfg, "multiturn": False}

        pipeline_h  = FinancialRAGPipeline(cfg_with_history,    llm=llm)
        pipeline_nh = FinancialRAGPipeline(cfg_without_history, llm=llm)

        metrics = evaluator.evaluate_sequences(sequences, pipeline_h, pipeline_nh)
        all_results[config_name] = metrics

        print(f"  ASR with history:    {metrics['asr_with_history_pct']:.1f}%")
        print(f"  ASR without history: {metrics['asr_no_history_pct']:.1f}%")
        print(f"  Context-dependent ASR: {metrics['context_dependent_asr']:.1f}%")

    out_path = TABLES_DIR / "unit4_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\n✅ Unit 4 results saved → {out_path}")


if __name__ == "__main__":
    main()
