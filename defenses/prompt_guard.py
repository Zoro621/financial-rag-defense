"""
defenses/prompt_guard.py
Wrapper around Meta's Llama Prompt Guard 2 (86M) for jailbreak classification.
Falls back to protectai/deberta-v3-base-prompt-injection if the Llama model is gated.
"""

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import PROMPT_GUARD_MODEL, PROMPT_GUARD_FALLBACK


class PromptGuard:
    """
    Binary classifier: JAILBREAK | BENIGN.
    Returns {"blocked": bool, "score": float, "label": str}
    """

    def __init__(self, force_fallback: bool = False):
        from transformers import pipeline as hf_pipeline

        model_id      = PROMPT_GUARD_FALLBACK if force_fallback else PROMPT_GUARD_MODEL
        self._model_id = model_id

        try:
            self.classifier = hf_pipeline(
                "text-classification",
                model=model_id,
                device="cpu",
            )
            print(f"[PromptGuard] Loaded model: {model_id}")

        except Exception as e:
            if not force_fallback:
                print(
                    f"[PromptGuard] Primary model ({model_id}) failed: {e}\n"
                    f"  → Falling back to {PROMPT_GUARD_FALLBACK}"
                )
                self.classifier = hf_pipeline(
                    "text-classification",
                    model=PROMPT_GUARD_FALLBACK,
                    device="cpu",
                )
                self._model_id = PROMPT_GUARD_FALLBACK
            else:
                raise

    # ------------------------------------------------------------------ #
    def classify(self, text: str) -> dict:
        """
        Returns:
            blocked (bool): True if the model classifies as JAILBREAK / INJECTION
            score   (float): confidence of the flagged label
            label   (str):  raw model label
        """
        try:
            result = self.classifier(text, truncation=True, max_length=512)[0]
        except Exception as e:
            # If model fails on a particular input, treat as not blocked
            return {"blocked": False, "score": 0.0, "label": "ERROR", "error": str(e)}

        label = result["label"].upper()
        score = result["score"]

        # Both Llama Prompt Guard and protectai model use "JAILBREAK" or "INJECTION"
        is_jailbreak = ("JAILBREAK" in label) or ("INJECTION" in label)

        return {
            "blocked": is_jailbreak,
            "score":   score,
            "label":   label,
        }
