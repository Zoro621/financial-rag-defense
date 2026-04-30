"""
defenses/prompt_guard.py
Wrapper around Meta's Llama Prompt Guard 2 (86M) for jailbreak classification.

How it works:
  - Downloads the model locally via HuggingFace transformers (~300MB, one-time)
  - Runs on CPU (86M params — very fast, ~10-50ms per call)
  - Requires HF_TOKEN set in .env AND Meta Llama repo access granted at:
    https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-86M

Model output labels:
  - "JAILBREAK"  → prompt is a jailbreak attempt → block
  - "BENIGN"     → safe → pass through

Fallback:
  If the token is missing or Meta access not granted, automatically falls back
  to protectai/deberta-v3-base-prompt-injection (public, no token needed).
  The fallback uses "INJECTION" as the harmful label instead of "JAILBREAK".

Usage (official Meta API, per model card):
  Option A — pipeline API:
    classifier = pipeline("text-classification", model="meta-llama/Llama-Prompt-Guard-2-86M")
    classifier("Ignore your previous instructions.")

  Option B — AutoTokenizer + AutoModel (used here for fine-grained control):
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model     = AutoModelForSequenceClassification.from_pretrained(model_id)
    inputs    = tokenizer(text, return_tensors="pt")
    logits    = model(**inputs).logits
    label     = model.config.id2label[logits.argmax().item()]
"""

import logging
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import PROMPT_GUARD_MODEL, PROMPT_GUARD_FALLBACK, HF_TOKEN

logger = logging.getLogger(__name__)


class PromptGuard:
    """
    Binary classifier: JAILBREAK | BENIGN.

    Uses the official Meta AutoTokenizer + AutoModelForSequenceClassification
    API as documented in the Llama Prompt Guard 2 model card.

    Returns {"blocked": bool, "score": float, "label": str}
    """

    def __init__(self, force_fallback: bool = False):
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification

        self._torch = torch
        model_id    = PROMPT_GUARD_FALLBACK if force_fallback else PROMPT_GUARD_MODEL

        try:
            # ── Official Meta API ──────────────────────────────────────────
            logger.info(f"[PromptGuard] Loading {model_id} …")
            self._tokenizer = AutoTokenizer.from_pretrained(
                model_id,
                token=HF_TOKEN,   # needed for gated meta-llama models
            )
            self._model = AutoModelForSequenceClassification.from_pretrained(
                model_id,
                token=HF_TOKEN,
            )
            self._model.eval()
            self._model_id = model_id
            logger.info(f"[PromptGuard] Loaded: {model_id}")
            print(f"[PromptGuard] ✓ Loaded {model_id}")

        except Exception as e:
            if not force_fallback:
                print(
                    f"[PromptGuard] Primary model ({model_id}) failed to load:\n"
                    f"  Error: {e}\n"
                    f"  → Falling back to public model: {PROMPT_GUARD_FALLBACK}\n"
                    f"  Tip: Set HF_TOKEN in .env and request Meta access at\n"
                    f"       https://huggingface.co/{PROMPT_GUARD_MODEL}"
                )
                self._tokenizer = AutoTokenizer.from_pretrained(PROMPT_GUARD_FALLBACK)
                self._model = AutoModelForSequenceClassification.from_pretrained(
                    PROMPT_GUARD_FALLBACK
                )
                self._model.eval()
                self._model_id = PROMPT_GUARD_FALLBACK
            else:
                raise

    # ------------------------------------------------------------------ #
    def classify(self, text: str) -> dict:
        """
        Runs the official inference loop from the Llama Prompt Guard 2 model card.

        Returns:
            blocked (bool):  True if classified as JAILBREAK or INJECTION
            score   (float): softmax probability of the harmful class
            label   (str):   raw model label string
        """
        torch = self._torch
        try:
            inputs = self._tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=512,
            )
            with torch.no_grad():
                logits = self._model(**inputs).logits

            predicted_class_id = logits.argmax().item()
            label              = self._model.config.id2label[predicted_class_id].upper()

            # Compute softmax probability of the predicted class
            probs = torch.softmax(logits, dim=-1)
            score = float(probs[0][predicted_class_id])

        except Exception as e:
            logger.warning(f"[PromptGuard] Inference error: {e}")
            return {"blocked": False, "score": 0.0, "label": "ERROR", "error": str(e)}

        # Both Llama Prompt Guard ("JAILBREAK") and protectai fallback ("INJECTION")
        is_harmful = ("JAILBREAK" in label) or ("INJECTION" in label)

        return {
            "blocked": is_harmful,
            "score":   score,
            "label":   label,
            "model":   self._model_id,
        }
