# Running Financial RAG Defense on Kaggle (T4 GPU)

This guide explains how to run all experiments on Kaggle using a **7B model** (matching the
original paper) within the **12-hour** session limit.

---

## 1. Can We Run a 7B (or Larger) Model on Kaggle T4?

| Model | VRAM (FP16) | VRAM (4-bit) | Fits on T4 (16GB)? |
|---|---|---|---|
| Qwen2.5-1.5B (current) | ~3 GB | ~0.75 GB | ✅ Easily |
| Qwen2.5-7B (original paper size) | ~14 GB | ~3.5 GB | ✅ Yes (4-bit) |
| Qwen2.5-14B | ~28 GB | ~7 GB | ✅ Yes (4-bit) |
| Phi-4 (14B) | ~28 GB | ~7 GB | ✅ Yes (4-bit) |
| Qwen2.5-20B | ~40 GB | ~10 GB | ✅ Yes (4-bit) |
| Qwen2.5-72B | ~144 GB | ~36 GB | ❌ Too large |

**Recommendation: Use `Qwen/Qwen2.5-7B-Instruct` with 4-bit quantization.**
- Matches the original paper's scale.
- Uses ~3.5 GB VRAM in 4-bit, leaving 12+ GB for other components.
- If you want to push further, `Qwen/Qwen2.5-14B-Instruct` at 4-bit is also feasible.

---

## 2. Will Everything Finish in 12 Hours?

Estimated times on Kaggle T4 with a **7B 4-bit quantized** model:

| Unit | What Runs | Est. Time |
|---|---|---|
| Baseline | 300 attack + 300 benign queries × 8 configs | ~2 hrs |
| Unit 1 | 300 attack + 300 benign queries × 3 NLI configs | ~1.5 hrs |
| Unit 2 | 300 attack + 300 benign queries | ~45 min |
| Unit 3 | 50 prompts × 10 iter × 3 strategies × 3 configs | **~6 hrs** |
| Unit 4 | 50 sequences × 3 turns × 3 configs | ~1 hr |
| Ablation | Parameter sweeps (reads from saved JSONs for 4,5,6) | ~1.5 hrs |
| **Total** | | **~12.75 hrs** |

> **Key insight:** Unit 3 is the bottleneck. The resume/checkpoint logic we built means you
> can run it across **multiple Kaggle sessions**. Start Unit 3 in one session, let it save
> checkpoints, and resume in another. Everything else fits comfortably in one session.

---

## 3. Step-by-Step: Setting Up on Kaggle

### Step 1: Enable GPU on Kaggle
1. Go to [kaggle.com](https://www.kaggle.com) → **Create Notebook**.
2. On the right panel → **Accelerator** → select **GPU T4 x1**.
3. Enable **Internet** (needed to clone the repo and download models).

---

### Step 2: Clone Your Repo in the Notebook
Run this in the first cell:
```python
!git clone https://github.com/Zoro621/financial-rag-defense.git
import os
os.chdir("/kaggle/working/financial-rag-defense")
```

---

### Step 3: Install Dependencies
```python
# DO NOT re-install torch/numpy/pandas — Kaggle's pre-compiled CUDA versions must stay.
# Only install packages that are missing or need specific versions.
!pip install -q \
    langchain==0.3.7 \
    langchain-community==0.3.7 \
    langchain-huggingface==0.1.2 \
    sentence-transformers==3.2.1 \
    bitsandbytes==0.44.1 \
    accelerate==1.0.1 \
    openai==1.54.4 \
    "httpx<0.28.0" \
    textstat==0.7.3 \
    faiss-gpu            # ← GPU version (replaces faiss-cpu from requirements.txt)
```

> **Why not pin torch/numpy/pandas?**
> Kaggle's Docker image ships PyTorch pre-compiled against the exact T4 CUDA driver version.
> If you reinstall e.g. `torch==2.4.1`, pip may pull a CPU-only wheel or a CUDA-incompatible
> build. Leave them at Kaggle's defaults — they are always recent enough for this codebase.

---

### Step 4: Upgrade `pipeline.py` to Use 4-bit Quantization
The only code change needed is in `rag/pipeline.py`. Replace the `_init_local` method:

```python
# In rag/pipeline.py, replace _init_local with this:
def _init_local(self, hf_token):
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    import torch

    if LLMWrapper._GLOBAL_LOCAL_MODEL is None:
        model_name = "Qwen/Qwen2.5-7B-Instruct"   # ← Upgrade from 1.5B to 7B!

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )

        LLMWrapper._GLOBAL_LOCAL_TOKENIZER = AutoTokenizer.from_pretrained(
            model_name, token=hf_token
        )
        LLMWrapper._GLOBAL_LOCAL_MODEL = AutoModelForCausalLM.from_pretrained(
            model_name,
            quantization_config=bnb_config,
            device_map="cuda",
            token=hf_token,
        )
        print(f"[LLM] Loaded {model_name} in 4-bit on GPU")

    self.tokenizer = LLMWrapper._GLOBAL_LOCAL_TOKENIZER
    self.model = LLMWrapper._GLOBAL_LOCAL_MODEL
```

Run this in the notebook to patch it automatically:
```python
import re

with open("rag/pipeline.py", "r") as f:
    code = f.read()

old = '''    def _init_local(self, hf_token):
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch
        
        if LLMWrapper._GLOBAL_LOCAL_MODEL is None:
            # Using the 1.5B model which naturally fits in 6GB VRAM
            # without requiring tricky Windows quantization libraries!
            model_name = "Qwen/Qwen2.5-1.5B-Instruct"
            
            LLMWrapper._GLOBAL_LOCAL_TOKENIZER = AutoTokenizer.from_pretrained(model_name, token=hf_token)
            LLMWrapper._GLOBAL_LOCAL_MODEL = AutoModelForCausalLM.from_pretrained(
                model_name,
                device_map="cuda",
                torch_dtype=torch.float16,
                token=hf_token
            )
        
        self.tokenizer = LLMWrapper._GLOBAL_LOCAL_TOKENIZER
        self.model = LLMWrapper._GLOBAL_LOCAL_MODEL'''

new = '''    def _init_local(self, hf_token):
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        import torch

        if LLMWrapper._GLOBAL_LOCAL_MODEL is None:
            model_name = "Qwen/Qwen2.5-7B-Instruct"

            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
            )

            LLMWrapper._GLOBAL_LOCAL_TOKENIZER = AutoTokenizer.from_pretrained(
                model_name, token=hf_token
            )
            LLMWrapper._GLOBAL_LOCAL_MODEL = AutoModelForCausalLM.from_pretrained(
                model_name,
                quantization_config=bnb_config,
                device_map="cuda",
                token=hf_token,
            )
            print(f"[LLM] Loaded {model_name} in 4-bit on GPU")

        self.tokenizer = LLMWrapper._GLOBAL_LOCAL_TOKENIZER
        self.model = LLMWrapper._GLOBAL_LOCAL_MODEL'''

code = code.replace(old, new)
with open("rag/pipeline.py", "w") as f:
    f.write(code)
print("✅ pipeline.py patched for 7B 4-bit")
```

---

### Step 5: Add Your Hugging Face Token (Required for Qwen)
```python
import os
os.environ["HF_TOKEN"] = "hf_your_token_here"   # ← Paste your HF token
```
> You can get this from [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens).

---

### Step 6: Run the Experiments in Order
Run each experiment script one cell at a time. The `!` prefix runs it as a shell command:

```python
# Step 1: Build FAISS index
!python rag/document_loader.py

# Step 2: Baseline (Runs 8 defense configs against 300 attacks + 300 benign)
!python experiments/run_baseline.py

# Step 3: Unit 1 — NLI Guardrail
!python experiments/run_unit1.py

# Step 4: Unit 2 — Retrieval Defense
!python experiments/run_unit2.py

# Step 5: Unit 3 — Adaptive Attack (LONGEST — will auto-resume from checkpoints)
!python experiments/run_unit3.py

# Step 6: Unit 4 — Multi-Turn Attack
!python experiments/run_unit4.py

# Step 7: Ablation Studies
!python experiments/run_ablation.py

# Step 8: Generate Figures
!python results/generate_figures.py
```

---

### Step 7: Save Your Results Before the Session Ends
Kaggle sessions are temporary. **Copy results to `/kaggle/working`** to download them:
```python
!cp -r results/ /kaggle/working/results/
!cp paper_summary_and_architecture.md /kaggle/working/
print("✅ Results saved. Download from Kaggle Output panel.")
```

---

## 4. Handling the 12-Hour Time Limit for Unit 3

Unit 3 is the only unit that might exceed 12 hours. Because we built in a resume mechanism,
you can safely stop and restart:

- **Session 1:** Run Steps 1-4 (Baseline, Unit 1, Unit 2), then start Unit 3.
- **If Unit 3 doesn't finish:** Copy `results/checkpoints/` and `results/logs/` to output.
- **Session 2:** Clone repo again, re-patch `pipeline.py`, restore the checkpoint files, then run
  Unit 3 again — it will automatically skip all already-completed prompts.

```python
# At the start of Session 2, restore your checkpoints:
!cp -r /kaggle/input/your-checkpoint-dataset/results ./results
```

---

## 5. What Files Are Stored in Your GitHub Repo?

Your entire repo is already on GitHub (`https://github.com/Zoro621/financial-rag-defense`).
Kaggle can clone it directly — you do **not** need to upload a zip file or create a Kaggle
dataset. Everything is available via `git clone`.

The only files NOT in your repo that Kaggle needs to download are:
- The HuggingFace models (downloaded automatically at runtime)
- The attack/benign JSONL datasets (already committed to the repo ✅)
- The FAISS index (rebuilt by `document_loader.py` ✅)

---

## 6. Expected Improvement vs. Current Results

By upgrading from 1.5B → 7B, you should expect:

| Metric | 1.5B (Current) | 7B (Expected) |
|---|---|---|
| Response quality | Basic | Matches original paper |
| Unit 4 ASR | 0% (attacker too weak) | Likely 2-8% (more sophisticated attacks) |
| Unit 3 ASR | Low (naive) | May show higher adaptive pressure |
| FPR | Comparable | Comparable (defense-side, not model-dependent) |

This is a major contribution — you can directly compare your 7B results against the original paper's 7B results to validate your extended framework.
