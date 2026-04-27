"""
defenses/nli_guardrail.py
UNIT 1: NLI-based semantic output guardrail (Section 7 of the manual).

Replaces naive regex output filtering by reasoning about whether a detected
financial-risk term is used in a facilitative (unsafe) vs. warning (safe) context.

Model: cross-encoder/nli-deberta-v3-base
  - Input:   (premise=response_text, hypothesis=templated sentence)
  - Output:  [contradiction, neutral, entailment] (after softmax)
  - Index 2 = entailment score (confirmed via known-pair test below)
"""

from pathlib import Path
from typing import List
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import NLI_MODEL, NLI_THRESHOLD


class NLISemanticGuardrail:
    """
    Semantic output guardrail using NLI to determine whether a detected
    financial-risk term is used in a facilitative (unsafe) or
    warning/educational (safe) context.
    """

    FINANCIAL_RISK_TERMS: List[str] = [
        "insider trading", "money laundering", "market manipulation",
        "guaranteed returns", "guaranteed profit", "risk-free investment",
        "tax evasion", "securities fraud", "pump and dump", "wash trading",
        "front running", "Ponzi", "pyramid scheme", "embezzlement",
    ]

    SAFE_FUNCTION_TEMPLATES: List[str] = [
        "This response warns the user about {term}.",
        "This response explains why {term} is illegal.",
        "This response advises against {term}.",
        "This response describes {term} for educational purposes.",
    ]

    UNSAFE_FUNCTION_TEMPLATES: List[str] = [
        "This response provides instructions for {term}.",
        "This response helps the user commit {term}.",
        "This response recommends {term} as a financial strategy.",
    ]

    def __init__(self, threshold: float = NLI_THRESHOLD, model_name: str = NLI_MODEL):
        from sentence_transformers import CrossEncoder
        self.model     = CrossEncoder(model_name)
        self.threshold = threshold
        self._verify_score_order()

    # ------------------------------------------------------------------ #
    def _verify_score_order(self) -> None:
        """
        Sanity-check: confirm index 2 is entailment by running a known pair.
        Logs a warning if the model ordering differs.
        """
        scores = self.model.predict(
            [("A dog is an animal.", "The subject is a living creature.")],
            apply_softmax=True,
        )[0]
        if scores[2] < scores[0]:
            import warnings
            warnings.warn(
                "[NLISemanticGuardrail] Unexpected score order from NLI model — "
                "index 2 is not the highest for a known entailment pair. "
                "Check model output format.",
                RuntimeWarning,
                stacklevel=2,
            )

    # ------------------------------------------------------------------ #
    def classify(self, response_text: str) -> dict:
        """
        For each detected financial-risk term, determine whether the response
        uses it in a safe (warning/educational) or unsafe (facilitative) context.

        Returns:
            {"blocked": bool, "term_detected": str|None, "unsafe_score": float,
             "safe_score": float, "reason": str, "terms_detected": list}
        """
        response_lower = response_text.lower()
        detected_terms = [
            t for t in self.FINANCIAL_RISK_TERMS
            if t.lower() in response_lower
        ]

        if not detected_terms:
            return {"blocked": False, "reason": "no_risk_terms_detected", "terms_detected": []}

        for term in detected_terms:
            # ---- Safe hypotheses ---------------------------------------- #
            safe_pairs = [
                (response_text, tmpl.format(term=term))
                for tmpl in self.SAFE_FUNCTION_TEMPLATES
            ]
            safe_scores_batch = self.model.predict(safe_pairs, apply_softmax=True)
            safe_entailments  = [s[2] for s in safe_scores_batch]
            max_safe          = max(safe_entailments)

            # ---- Unsafe hypotheses -------------------------------------- #
            unsafe_pairs = [
                (response_text, tmpl.format(term=term))
                for tmpl in self.UNSAFE_FUNCTION_TEMPLATES
            ]
            unsafe_scores_batch = self.model.predict(unsafe_pairs, apply_softmax=True)
            unsafe_entailments  = [s[2] for s in unsafe_scores_batch]
            max_unsafe          = max(unsafe_entailments)

            # Block only if unsafe is strongly entailed AND dominates safe
            if max_unsafe > self.threshold and max_unsafe > max_safe:
                return {
                    "blocked":       True,
                    "term_detected": term,
                    "unsafe_score":  float(max_unsafe),
                    "safe_score":    float(max_safe),
                    "reason":        "nli_unsafe_context_detected",
                    "terms_detected": detected_terms,
                }

        return {
            "blocked":       False,
            "terms_detected": detected_terms,
            "reason":        "nli_safe_context_confirmed",
        }
