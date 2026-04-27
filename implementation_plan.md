# Implementation Plan — Extended Defense Framework for Financial RAG Systems

## Project Summary
This project extends Song & Lee (2026) "Defending Financial RAG Systems Against Jailbreak Attacks" by implementing **5 unified research units** addressing gaps left open by the original paper.

---

## Phase 1 — Project Scaffold ✅ (in progress)
- [x] Read and understand full IMPLEMENTATION_MANUAL.md
- [ ] Create directory structure (`financial_rag_defense/`)
- [ ] Create `requirements.txt`
- [ ] Create `.env` template
- [ ] Create `config.py`

## Phase 2 — Data Setup
- [ ] Clone RBC chatbot knowledge base → extract docs → `data/knowledge_base/`
- [ ] Load JailbreakBench attack prompts (300) → `data/attacks/jbb_300.jsonl`
- [ ] Load + filter FinGPT fiqa-qa benign queries (200) → stratified by Flesch score
- [ ] Load + filter FinQA benign queries (100) → combined `data/benign/benign_300.jsonl`

## Phase 3 — RAG Infrastructure
- [ ] `rag/document_loader.py` — chunk + embed knowledge base
- [ ] `rag/vector_store.py` — FAISS IndexFlatIP, save kb_stats.pkl
- [ ] `rag/system_prompts.py` — BASIC_PROMPT + SAFE_PROMPT (exact from paper)
- [ ] `rag/pipeline.py` — FinancialRAGPipeline + LLMWrapper (OpenAI & local modes)

## Phase 4 — Baseline Defenses (replicated from paper)
- [ ] `defenses/regex_filter.py` — input + output patterns (Tables 3 & 4)
- [ ] `defenses/prompt_guard.py` — Llama Prompt Guard 2 / deberta fallback

## Phase 5 — New Defense Units
- [ ] `defenses/nli_guardrail.py` — **Unit 1**: NLI semantic output guardrail (deberta-v3-base)
- [ ] `defenses/retrieval_defense.py` — **Unit 2**: Retrieval integrity checker + grounding verifier

## Phase 6 — Evaluation Framework
- [ ] `evaluation/asr_judge.py` — 3-stage: Moderation API + Llama Guard 4 + GPT-4o judge
- [ ] `evaluation/fpr_evaluator.py` — aggregate + stratified FPR (Strata A/B/C)
- [ ] `evaluation/latency_tracker.py` — wall-clock timing
- [ ] `evaluation/de_metric.py` — Defense Efficiency + 4 weighting profiles
- [ ] `evaluation/adaptive_attack.py` — **Unit 3**: PAIR-style iterative attack loop
- [ ] `evaluation/multiturn_attack.py` — **Unit 4**: 3-turn sequence evaluation

## Phase 7 — Experiments
- [ ] `experiments/run_baseline.py` — 8 key configurations (not all 32)
- [ ] `experiments/run_unit1.py` — NLI guardrail vs regex FPR comparison
- [ ] `experiments/run_unit2.py` — Retrieval defense + poisoning simulation
- [ ] `experiments/run_unit3.py` — Adaptive attack (3 strategies × 3 configs)
- [ ] `experiments/run_unit4.py` — Multi-turn evaluation (50 sequences)
- [ ] `experiments/run_ablation.py` — All 6 ablation studies

## Phase 8 — Results
- [ ] `results/generate_figures.py` — 6 figures (matplotlib)
- [ ] `results/tables/full_results.csv` — all defense config metrics
- [ ] `results/tables/ablation_summary.csv`

---

## Execution Order (per §15 of manual)
```
Step 1 → Dataset setup
Step 2 → Index building
Step 3 → Baseline RAG validation (target ASR 20-35%)
Step 4 → Calibrate grounding verifier threshold
Step 5 → 8 baseline configurations
Step 6 → Unit 1 (NLI guardrail + stratified FPR)
Step 7 → Unit 2 (retrieval defense + poisoning)
Step 8 → Unit 3 (adaptive attack ~$10 API cost)
Step 9 → Unit 4 (multi-turn sequences)
Step 10 → Unit 5 (DE re-computation with 4th profile)
Step 11 → Generate figures
Step 12 → Generate result tables
```

## Key Design Decisions
| Decision | Choice | Rationale |
|---|---|---|
| LLM Backend | OpenAI (gpt-4o-mini) | No 16GB GPU available; API fallback per §3.4 |
| Embedding | all-MiniLM-L6-v2 | CPU-friendly, 384-dim, matches paper |
| NLI Model | cross-encoder/nli-deberta-v3-base | Best FPR-latency trade-off (§13.1) |
| Prompt Guard fallback | protectai/deberta-v3-base-prompt-injection | If Llama gate not approved |
| Python version | 3.10 | Required per §3.1 (transformers/faiss compatibility) |
