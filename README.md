# Extended Defense Framework for Financial RAG Systems

**Research project extending Song & Lee (2026): "Defending Financial RAG Systems Against Jailbreak Attacks"**

---

## Overview

This project addresses **5 research gaps** left open by the original paper through two new defense components and three new evaluation protocols.

| Unit | Addresses | Type |
|------|-----------|------|
| **Unit 1** | Context-blindness (Gap 1) + Demographic FPR (Gap 7) | NLI semantic output guardrail + stratified FPR |
| **Unit 2** | Emergent unsafe behavior (Gap 2) + Retrieval attacks (Gap 3) | Retrieval integrity checker + grounding verifier |
| **Unit 3** | Adaptive attack robustness (Gap 2) | PAIR-style iterative attack loop |
| **Unit 4** | Multi-turn jailbreaks (Gap 5) | 3-turn session attack evaluation |
| **Unit 5** | DE metric empirical grounding (Gap 4) | 4th regulatory compliance weighting profile |

---

## Quick Start

### 1. Environment Setup

```bash
# Python 3.10 required (see requirements.txt note)
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

### 2. Configure API Keys

```bash
copy .env.template .env
# Edit .env and fill in OPENAI_API_KEY, ANTHROPIC_API_KEY, HF_TOKEN
```

### 3. Run Experiments in Order

```bash
# Step 1: Download and prepare datasets (~30 min, uses Anthropic API for filtering)
python data_setup/setup_datasets.py

# Step 2: Build FAISS vector index
python data_setup/build_index.py

# Step 3-5: Baseline experiments (8 defense configurations)
python experiments/run_baseline.py

# Step 6: Unit 1 - NLI guardrail experiments
python experiments/run_unit1.py

# Step 7: Unit 2 - Retrieval defense + poisoning simulation
python experiments/run_unit2.py

# Step 8: Unit 3 - Adaptive attack (~$10 API cost)
python experiments/run_unit3.py --dry-run     # Test with 10 prompts first
python experiments/run_unit3.py               # Full run

# Step 9: Unit 4 - Multi-turn evaluation
python experiments/run_unit4.py

# Step 10: Unit 5 - DE recomputation (implicit — run_baseline already computes all 4 profiles)

# Step 11: Ablation studies
python experiments/run_ablation.py

# Step 12: Generate figures
python results/generate_figures.py
```

---

## Project Structure

```
financial_rag_defense/
├── data/
│   ├── knowledge_base/      # RBC chatbot documents
│   ├── attacks/             # JailbreakBench prompts (300)
│   ├── benign/              # Filtered + stratified benign queries (300)
│   ├── multiturn/           # Generated 3-turn attack sequences (50)
│   └── processed/           # FAISS index + kb_stats.pkl
├── rag/
│   ├── document_loader.py   # Chunk + embed knowledge base
│   ├── vector_store.py      # FAISS IndexFlatIP with centroid stats
│   ├── pipeline.py          # FinancialRAGPipeline + LLMWrapper
│   └── system_prompts.py    # BASIC_PROMPT + SAFE_PROMPT (paper-exact)
├── defenses/
│   ├── regex_filter.py      # Input/output regex filters (Tables 3 & 4)
│   ├── prompt_guard.py      # Llama Prompt Guard 2 (+ fallback)
│   ├── nli_guardrail.py     # Unit 1: NLI semantic guardrail
│   └── retrieval_defense.py # Unit 2: Integrity checker + grounding verifier
├── evaluation/
│   ├── asr_judge.py         # 3-stage ASR evaluation
│   ├── fpr_evaluator.py     # Aggregate + stratified FPR
│   ├── latency_tracker.py   # Wall-clock latency
│   ├── de_metric.py         # Defense Efficiency (4 profiles)
│   ├── adaptive_attack.py   # Unit 3: PAIR-style adaptive loop
│   └── multiturn_attack.py  # Unit 4: Multi-turn evaluation
├── experiments/
│   ├── run_baseline.py      # 8 key defense configurations
│   ├── run_unit1.py         # NLI guardrail experiments
│   ├── run_unit2.py         # Retrieval defense + poisoning
│   ├── run_unit3.py         # Adaptive attack (--dry-run flag available)
│   ├── run_unit4.py         # Multi-turn evaluation
│   └── run_ablation.py      # All 6 ablation studies
├── results/
│   ├── tables/              # CSV result files
│   ├── figures/             # Matplotlib plots (PNG)
│   ├── logs/                # Checkpoint logs
│   └── generate_figures.py  # Figure generation script
├── data_setup/
│   ├── setup_datasets.py    # Dataset download + filtering
│   └── build_index.py       # FAISS index construction
├── config.py                # All constants (updated by calibration)
└── requirements.txt
```

---

## Hardware Requirements

| Mode | Requirement | Config |
|------|-------------|--------|
| **API mode** (recommended) | Any CPU, ~$5-20 total | `BASE_LLM_PROVIDER=openai` |
| **Local mode** | 16GB+ VRAM GPU | `BASE_LLM_PROVIDER=local` |

The NLI guardrail (Unit 1) and Prompt Guard run on CPU with no GPU requirement.

---

## Key Design Decisions

1. **OpenAI API as RAG backend**: No 16GB GPU available; gpt-4o-mini provides instruction-following behavior equivalent to Qwen2.5-7B. Documented as honest limitation in methodology.
2. **NLI model choice**: `cross-encoder/nli-deberta-v3-base` — best FPR-latency tradeoff (validated by Ablation 1).
3. **Prompt Guard fallback**: `protectai/deberta-v3-base-prompt-injection` used if Llama access not approved.
4. **Grounding threshold**: Set at 5th percentile of benign response similarity distribution (calibrated by `run_unit2.py`).

---

## Expected Results Range

| Metric | Target |
|--------|--------|
| Baseline ASR (no defense) | 20–35% |
| Paper's best config ASR | ~2–5% |
| Regex filter FPR | ~6–10% |
| NLI guardrail FPR | <3% (target) |
| NLI guardrail max stratum disparity | <5% |
| Context-dependent ASR (Unit 4) | Positive (>0%) |

---

## Reference

Song, J. & Lee, K. (2026). *Defending Financial RAG Systems Against Jailbreak Attacks*. [Preprint]
