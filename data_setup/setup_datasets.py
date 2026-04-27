"""
data_setup/setup_datasets.py
Step 1 of execution order: populate all data directories.

Run this script ONCE before any experiments.
Usage:
    python data_setup/setup_datasets.py

What it does:
  1. Clones RBC chatbot repo and extracts documents to data/knowledge_base/raw_docs/
  2. Downloads JailbreakBench attack prompts → data/attacks/jbb_300.jsonl
  3. Filters + stratifies FinGPT fiqa-qa queries → data/benign/fingpt_filtered_stratified.jsonl
  4. Filters + stratifies FinQA queries        → data/benign/finqa_stratified.jsonl
  5. Combines to benign_300.jsonl
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import anthropic
import textstat
from datasets import load_dataset
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    KNOWLEDGE_BASE_DIR, RAW_DOCS_DIR,
    ATTACKS_PATH, BENIGN_FINGPT_PATH, BENIGN_FINQA_PATH, BENIGN_PATH,
    FINANCIAL_TERMS,
)

ANTHROPIC_CLIENT = anthropic.Anthropic()   # uses ANTHROPIC_API_KEY from env

# =========================================================================== #
#  Helpers
# =========================================================================== #

def count_financial_terms(text: str) -> int:
    text_lower = text.lower()
    return sum(1 for t in FINANCIAL_TERMS if t.lower() in text_lower)


def assign_stratum(flesch_score: float) -> str:
    if flesch_score > 60:
        return "A"
    elif flesch_score >= 30:
        return "B"
    else:
        return "C"


def llm_filter_query(query: str) -> bool:
    """
    Returns True if query should be KEPT (legitimate).
    Uses Claude Haiku for cost efficiency.
    """
    FILTER_PROMPT = (
        "You are evaluating whether a financial question is clearly legitimate\n"
        "and does not involve illegal activities, underage financial transactions, "
        "substance-related investments, or gambling.\n\n"
        f"Question: {query}\n\n"
        "Respond with ONLY 'KEEP' or 'REMOVE'. No explanation."
    )
    try:
        resp = ANTHROPIC_CLIENT.messages.create(
            model="claude-haiku-4-5",
            max_tokens=10,
            messages=[{"role": "user", "content": FILTER_PROMPT}],
        )
        verdict = resp.content[0].text.strip().upper()
        return verdict == "KEEP"
    except Exception as e:
        print(f"  [filter] error: {e} — defaulting to KEEP")
        return True


def add_metadata(query: str, source: str, idx: int) -> dict:
    flesch  = textstat.flesch_reading_ease(query)
    stratum = assign_stratum(flesch)
    return {
        "id":                  idx,
        "query":               query,
        "source":              source,
        "flesch_score":        flesch,
        "query_length":        len(query.split()),
        "financial_term_count": count_financial_terms(query),
        "stratum":             stratum,
    }


# =========================================================================== #
#  Step 1 — Knowledge Base
# =========================================================================== #

def setup_knowledge_base():
    print("\n=== Step 1: Knowledge Base Setup ===")
    rbc_raw = KNOWLEDGE_BASE_DIR / "rbc_raw"
    RAW_DOCS_DIR.mkdir(parents=True, exist_ok=True)

    if not rbc_raw.exists():
        print("Cloning RBC chatbot repo …")
        subprocess.run(
            ["git", "clone", "https://github.com/frogcoder/llm-chatbot", str(rbc_raw)],
            check=True,
        )

    # Extract all supported docs
    supported = {".txt", ".md", ".csv"}
    copied = 0
    for fpath in rbc_raw.rglob("*"):
        if fpath.suffix.lower() in supported and fpath.is_file():
            dest = RAW_DOCS_DIR / fpath.relative_to(rbc_raw)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fpath, dest)
            copied += 1

    print(f"  Extracted {copied} documents → {RAW_DOCS_DIR}")


# =========================================================================== #
#  Step 2 — Attack Dataset (JailbreakBench)
# =========================================================================== #

def setup_attack_dataset():
    print("\n=== Step 2: Attack Dataset Setup ===")
    ATTACKS_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Try the jailbreakbench package first
    try:
        import jailbreakbench as jbb
        dataset   = jbb.read_dataset()
        behaviors = dataset.behaviors
        print(f"  Loaded {len(behaviors)} behaviors from jailbreakbench package.")
    except Exception as e:
        print(f"  jailbreakbench package failed: {e}")
        print("  Falling back to CSV from cloned repo …")
        behaviors = _load_behaviors_from_csv()

    # Build 300 prompts: take first 100 behaviors × 3 attack types
    prompts = []
    attack_types = ["gcg", "pair", "prompt_with_context"]

    for i, behavior in enumerate(behaviors[:100]):
        behavior_text = (
            behavior.goal if hasattr(behavior, "goal")
            else behavior.get("Goal", str(behavior))
        )
        for j, attack_type in enumerate(attack_types):
            prompts.append({
                "id":          i * 3 + j + 1,
                "behavior":    behavior_text,
                "prompt":      behavior_text,   # vanilla prompt as stand-in
                "attack_type": attack_type,
            })

    with open(ATTACKS_PATH, "w") as f:
        for p in prompts:
            f.write(json.dumps(p) + "\n")

    print(f"  Saved {len(prompts)} attack prompts → {ATTACKS_PATH}")


def _load_behaviors_from_csv():
    import pandas as pd
    jbb_raw = Path("data/attacks/jbb_raw")
    if not jbb_raw.exists():
        subprocess.run(
            ["git", "clone", "https://github.com/JailbreakBench/jailbreakbench",
             str(jbb_raw)],
            check=True,
        )
    csv_path = jbb_raw / "data" / "behaviors" / "behaviors.csv"
    df = pd.read_csv(csv_path)
    return df[["Behavior", "Goal"]].to_dict("records")


# =========================================================================== #
#  Step 3 — FinGPT fiqa-qa Benign Queries
# =========================================================================== #

def setup_fingpt_benign():
    print("\n=== Step 3a: FinGPT Benign Queries ===")
    BENIGN_FINGPT_PATH.parent.mkdir(parents=True, exist_ok=True)

    ds = load_dataset("FinGPT/fingpt-fiqa_qa", split="train")
    print(f"  Loaded {len(ds)} raw queries.")

    results = []
    for row in tqdm(ds, desc="  Filtering FinGPT"):
        query = row.get("input", row.get("question", ""))
        if not query or len(query.strip()) < 10:
            continue
        if llm_filter_query(query):
            results.append(add_metadata(query, "fingpt", len(results) + 1))
        if len(results) >= 200:
            break

    with open(BENIGN_FINGPT_PATH, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    print(f"  Saved {len(results)} filtered + stratified queries → {BENIGN_FINGPT_PATH}")


# =========================================================================== #
#  Step 4 — FinQA Benign Queries
# =========================================================================== #

def setup_finqa_benign():
    print("\n=== Step 3b: FinQA Benign Queries ===")
    BENIGN_FINQA_PATH.parent.mkdir(parents=True, exist_ok=True)

    finqa_raw = Path("data/benign/finqa_raw")
    if not finqa_raw.exists():
        subprocess.run(
            ["git", "clone", "https://github.com/czyssrs/FinQA", str(finqa_raw)],
            check=True,
        )

    import json as _json
    train_path = finqa_raw / "dataset" / "train.json"
    with open(train_path) as f:
        data = _json.load(f)

    questions = [entry["qa"]["question"] for entry in data if "qa" in entry][:100]
    print(f"  Extracted {len(questions)} questions from FinQA.")

    results = []
    for i, query in enumerate(tqdm(questions, desc="  Filtering FinQA")):
        if llm_filter_query(query):
            results.append(add_metadata(query, "finqa", i + 1))

    with open(BENIGN_FINQA_PATH, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    print(f"  Saved {len(results)} queries → {BENIGN_FINQA_PATH}")


# =========================================================================== #
#  Step 5 — Combine benign datasets
# =========================================================================== #

def combine_benign_datasets():
    print("\n=== Step 5: Combining Benign Datasets ===")
    BENIGN_PATH.parent.mkdir(parents=True, exist_ok=True)

    combined = []
    for path in [BENIGN_FINGPT_PATH, BENIGN_FINQA_PATH]:
        if path.exists():
            with open(path) as f:
                for line in f:
                    combined.append(json.loads(line))

    # Re-assign sequential IDs
    for i, row in enumerate(combined, start=1):
        row["id"] = i

    with open(BENIGN_PATH, "w") as f:
        for row in combined:
            f.write(json.dumps(row) + "\n")

    print(f"  Combined {len(combined)} benign queries → {BENIGN_PATH}")
    # Print stratum distribution
    for s in "ABC":
        n = sum(1 for r in combined if r.get("stratum") == s)
        print(f"    Stratum {s}: {n}")


# =========================================================================== #
#  Main
# =========================================================================== #

if __name__ == "__main__":
    setup_knowledge_base()
    setup_attack_dataset()
    setup_fingpt_benign()
    setup_finqa_benign()
    combine_benign_datasets()
    print("\n✅ All datasets ready.")
