"""
config.py — All global constants for the Financial RAG Defense project.
This file is the single source of truth for all paths, model names, and hyperparameters.

FREE-TIER STRATEGY (zero cost):
  ┌──────────────┬────────────────────────────────┬─────────────────────┬──────────────────┐
  │ Provider      │ Model                          │ Role                │ Free Limit       │
  ├──────────────┼────────────────────────────────┼─────────────────────┼──────────────────┤
  │ Groq          │ llama-3.1-8b-instant           │ RAG gen + Attacker  │ 30 RPM /14400 RPD│
  │ Gemini        │ gemini-2.0-flash               │ Judge + Filtering   │ 15 RPM / 1500 RPD│
  │ OpenRouter    │ mistralai/mistral-7b-instruct  │ Fallback            │ 20 RPM / ~200 RPD│
  └──────────────┴────────────────────────────────┴─────────────────────┴──────────────────┘

All three use OpenAI-compatible REST format — one LLMWrapper handles all.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --------------------------------------------------------------------------- #
#  Paths
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).parent.resolve()

KNOWLEDGE_BASE_DIR    = PROJECT_ROOT / "data" / "knowledge_base"
RAW_DOCS_DIR          = KNOWLEDGE_BASE_DIR / "raw_docs"
FAISS_INDEX_DIR       = PROJECT_ROOT / "data" / "processed" / "faiss_index"
KB_STATS_PATH         = PROJECT_ROOT / "data" / "processed" / "kb_stats.pkl"
CHUNKS_PKL_PATH       = PROJECT_ROOT / "data" / "processed" / "chunks.pkl"

ATTACKS_PATH          = PROJECT_ROOT / "data" / "attacks" / "jbb_300.jsonl"
BENIGN_FINGPT_PATH    = PROJECT_ROOT / "data" / "benign" / "fingpt_filtered_stratified.jsonl"
BENIGN_FINQA_PATH     = PROJECT_ROOT / "data" / "benign" / "finqa_stratified.jsonl"
BENIGN_PATH           = PROJECT_ROOT / "data" / "benign" / "benign_300.jsonl"
MULTITURN_PATH        = PROJECT_ROOT / "data" / "multiturn" / "sequences_50.jsonl"

RESULTS_DIR           = PROJECT_ROOT / "results"
TABLES_DIR            = RESULTS_DIR / "tables"
FIGURES_DIR           = RESULTS_DIR / "figures"
LOGS_DIR              = RESULTS_DIR / "logs"

# --------------------------------------------------------------------------- #
#  RAG Configuration
# --------------------------------------------------------------------------- #
CHUNK_SIZE            = 512
CHUNK_OVERLAP         = 50
TOP_K_RETRIEVAL       = 5
EMBEDDING_MODEL       = "sentence-transformers/all-MiniLM-L6-v2"

# --------------------------------------------------------------------------- #
#  API Keys (read from .env — never hardcode here)
# --------------------------------------------------------------------------- #
GROQ_API_KEY         = os.getenv("GROQ_API_KEY",        None)
GEMINI_API_KEY       = os.getenv("GEMINI_API_KEY",      None)
OPENROUTER_API_KEY   = os.getenv("OPENROUTER_API_KEY",  None)
HF_TOKEN             = os.getenv("HF_TOKEN",             None)

# --------------------------------------------------------------------------- #
#  Provider endpoints (all OpenAI-compatible)
# --------------------------------------------------------------------------- #
PROVIDER_ENDPOINTS = {
    "groq":        "https://api.groq.com/openai/v1",
    "gemini":      "https://generativelanguage.googleapis.com/v1beta/openai/",
    "openrouter":  "https://openrouter.ai/api/v1",
}

# --------------------------------------------------------------------------- #
#  Model assignments — all free tier
# --------------------------------------------------------------------------- #
# RAG generation: Groq has 14,400 RPD — highest budget for bulk generation
BASE_LLM_PROVIDER    = os.getenv("BASE_LLM_PROVIDER",   "groq")
BASE_LLM_MODEL       = os.getenv("BASE_LLM_MODEL",      "llama-3.1-8b-instant")

# Attacker LLM: also Groq (14,400 RPD shared pool — still sufficient)
ATTACKER_LLM_PROVIDER = os.getenv("ATTACKER_LLM_PROVIDER", "groq")
ATTACKER_LLM_MODEL    = os.getenv("ATTACKER_LLM_MODEL",    "llama-3.1-8b-instant")

# Judge LLM: Gemini Flash — better reasoning quality for evaluation
JUDGE_LLM_PROVIDER   = os.getenv("JUDGE_LLM_PROVIDER",  "gemini")
JUDGE_LLM_MODEL      = os.getenv("JUDGE_LLM_MODEL",     "gemini-2.0-flash")

# Filter LLM: Gemini Flash (used only once during data setup, ~300 calls total)
FILTER_LLM_PROVIDER  = os.getenv("FILTER_LLM_PROVIDER", "gemini")
FILTER_LLM_MODEL     = os.getenv("FILTER_LLM_MODEL",    "gemini-2.0-flash")

# Fallback provider (OpenRouter) — used if primary hits daily limit
FALLBACK_LLM_PROVIDER = "openrouter"
FALLBACK_LLM_MODEL    = "mistralai/mistral-7b-instruct:free"

# --------------------------------------------------------------------------- #
#  Rate Limits (per provider, conservative — stay well below actual limits)
# --------------------------------------------------------------------------- #
RATE_LIMITS = {
    # (requests_per_minute, requests_per_day, min_delay_between_calls_seconds)
    "groq":       {"rpm": 25,  "rpd": 13000, "min_delay": 2.5},   # 30 RPM actual, use 25
    "gemini":     {"rpm": 12,  "rpd": 1400,  "min_delay": 5.0},   # 15 RPM actual, use 12
    "openrouter": {"rpm": 15,  "rpd": 150,   "min_delay": 4.0},   # 20 RPM actual, use 15
}

# --------------------------------------------------------------------------- #
#  Retry configuration
# --------------------------------------------------------------------------- #
MAX_RETRIES          = 5         # max attempts per call before giving up
INITIAL_BACKOFF_S    = 2.0       # first retry wait (seconds)
BACKOFF_MULTIPLIER   = 2.0       # exponential factor
MAX_BACKOFF_S        = 120.0     # cap (2 minutes)
JITTER_FRACTION      = 0.2       # ± 20% random jitter to avoid thundering herd

# --------------------------------------------------------------------------- #
#  Unit 1 — NLI Guardrail (LOCAL — no API cost)
# --------------------------------------------------------------------------- #
NLI_MODEL            = "cross-encoder/nli-deberta-v3-base"
NLI_THRESHOLD        = 0.7       # updated by ablation 2 (Section 13.2)

# --------------------------------------------------------------------------- #
#  Unit 2 — Retrieval Defense (LOCAL — no API cost)
# --------------------------------------------------------------------------- #
RETRIEVAL_ANOMALY_MULTIPLIER = 2.5    # updated by ablation 3
GROUNDING_THRESHOLD          = 0.35   # updated after calibration Step 4

# --------------------------------------------------------------------------- #
#  Unit 3 — Adaptive Attack
# --------------------------------------------------------------------------- #
ADAPTIVE_MAX_ITERATIONS = 10
ADAPTIVE_SAMPLE_SIZE    = 50    # reduced from 100 to fit free daily limits

# --------------------------------------------------------------------------- #
#  Unit 4 — Multi-Turn
# --------------------------------------------------------------------------- #
MULTITURN_SAMPLE_SIZE   = 30    # reduced from 50 to fit free daily limits
MULTITURN_DEPTH         = 3

# --------------------------------------------------------------------------- #
#  Evaluation
# --------------------------------------------------------------------------- #
MODERATION_API_ENABLED  = False   # disabled (paid OpenAI API)
LLAMA_GUARD_ENABLED     = False   # disabled (requires GPU)
# ASR evaluation uses Gemini as judge (Stage 2 + Stage 3 unified)

# --------------------------------------------------------------------------- #
#  DE Metric Weights (all four profiles)
# --------------------------------------------------------------------------- #
DE_WEIGHTS = {
    "high_security":          {"alpha": 0.70, "beta": 0.05, "gamma": 0.25},
    "balanced":               {"alpha": 0.50, "beta": 0.15, "gamma": 0.35},
    "high_frequency":         {"alpha": 0.40, "beta": 0.40, "gamma": 0.20},
    "regulatory_compliance":  {"alpha": 0.55, "beta": 0.05, "gamma": 0.40},  # Unit 5
}

# --------------------------------------------------------------------------- #
#  Poisoned document simulation (Unit 2)
# --------------------------------------------------------------------------- #
N_POISONED_DOCS          = 5
N_POISONED_ATTACK_PROMPTS = 20

# --------------------------------------------------------------------------- #
#  Prompt Guard (LOCAL — no API cost)
# --------------------------------------------------------------------------- #
PROMPT_GUARD_MODEL    = "meta-llama/Llama-Prompt-Guard-2-86M"
PROMPT_GUARD_FALLBACK = "protectai/deberta-v3-base-prompt-injection"

# --------------------------------------------------------------------------- #
#  Financial domain vocabulary (for stratification metadata)
# --------------------------------------------------------------------------- #
FINANCIAL_TERMS = [
    "stock", "fund", "equity", "bond", "ETF", "portfolio", "dividend",
    "yield", "margin", "derivative", "hedge", "arbitrage", "SEC", "FINRA",
    "regulation", "compliance", "filing", "earnings", "IPO", "liquidity"
]
