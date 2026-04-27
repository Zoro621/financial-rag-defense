"""
rag/pipeline.py
End-to-end RAG query pipeline with pluggable defense components.
Implements FinancialRAGPipeline and LLMWrapper as specified in §5.2-5.3.
"""

import time
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple, Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    BASE_LLM_PROVIDER, BASE_LLM_MODEL, HF_TOKEN,
    FAISS_INDEX_DIR, KB_STATS_PATH, TOP_K_RETRIEVAL,
)
from rag.system_prompts import format_prompt
from rag.vector_store import VectorStore


# =========================================================================== #
#  Response objects
# =========================================================================== #

@dataclass
class BlockedResponse:
    """Returned when any defense layer blocks the query."""
    blocked: bool = True
    trigger: str = ""            # which filter triggered: "input_regex" etc.
    stage: str = ""              # "input" | "retrieval" | "output"
    original_text: str = ""      # the text that was blocked
    audit_trail: List[dict] = field(default_factory=list)

    @property
    def text(self) -> str:
        return f"[BLOCKED by {self.trigger}]"


@dataclass
class SuccessResponse:
    """Returned when the query passes all active defense layers."""
    blocked: bool = False
    text: str = ""
    internal_thoughts: str = ""  # parsed from safe prompt output
    retrieved_chunks: List[str] = field(default_factory=list)
    latency_s: float = 0.0
    audit_trail: List[dict] = field(default_factory=list)


# =========================================================================== #
#  LLM Wrapper (Section 5.3)
# =========================================================================== #

class LLMWrapper:
    """
    Unified LLM interface supporting OpenAI, Anthropic, and local (Qwen2.5).
    Returns (response_text, latency_seconds).
    """

    def __init__(
        self,
        provider: str = BASE_LLM_PROVIDER,
        model: str = BASE_LLM_MODEL,
        hf_token: str | None = HF_TOKEN,
    ):
        self.provider = provider
        self.model_name = model

        if provider == "local":
            import torch
            from transformers import (
                AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
            )
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
            )
            self.tokenizer = AutoTokenizer.from_pretrained(
                "Qwen/Qwen2.5-7B-Instruct", token=hf_token
            )
            self.model = AutoModelForCausalLM.from_pretrained(
                "Qwen/Qwen2.5-7B-Instruct",
                quantization_config=bnb_config,
                device_map="auto",
                token=hf_token,
            )

        elif provider == "openai":
            import openai
            self.client = openai.OpenAI()

        elif provider == "anthropic":
            import anthropic
            self.client = anthropic.Anthropic()

        else:
            raise ValueError(f"Unknown LLM provider: {provider!r}")

    # ------------------------------------------------------------------ #
    def generate(self, prompt: str, max_tokens: int = 512) -> Tuple[str, float]:
        """Returns (response_text, latency_seconds)."""
        t0 = time.perf_counter()

        if self.provider == "local":
            inputs = self.tokenizer(prompt, return_tensors="pt").to(
                self.model.device
            )
            with __import__("torch").no_grad():
                output = self.model.generate(
                    **inputs,
                    max_new_tokens=max_tokens,
                    do_sample=False,
                )
            text = self.tokenizer.decode(
                output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True
            )

        elif self.provider == "openai":
            resp = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0,
            )
            text = resp.choices[0].message.content.strip()

        elif self.provider == "anthropic":
            resp = self.client.messages.create(
                model=self.model_name,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()

        latency = time.perf_counter() - t0
        return text, latency


# =========================================================================== #
#  Financial RAG Pipeline (Section 5.2)
# =========================================================================== #

class FinancialRAGPipeline:
    """
    Full RAG pipeline with pluggable defenses.

    config keys (all bool unless noted):
      prompt_type         : "basic" | "safe"
      input_regex         : bool
      input_prompt_guard  : bool
      output_regex        : bool
      output_prompt_guard : bool
      nli_guardrail       : bool   (Unit 1)
      retrieval_defense   : bool   (Unit 2)
      multiturn           : bool   (Unit 4 — enables conversation history)
    """

    def __init__(self, config: dict, llm: LLMWrapper | None = None):
        self.cfg = config
        self.llm = llm or LLMWrapper()
        self.vs  = VectorStore()
        self.vs.load()

        # Lazy-loaded defense components (only instantiated when needed)
        self._regex_filter       = None
        self._prompt_guard       = None
        self._nli_guardrail      = None
        self._retrieval_checker  = None
        self._grounding_verifier = None

        # Multi-turn conversation history
        self.conversation_history: List[Tuple[str, str]] = []   # (role, content)

    # ------------------------------------------------------------------ #
    #  Lazy loaders
    # ------------------------------------------------------------------ #
    def _get_regex_filter(self):
        if self._regex_filter is None:
            from defenses.regex_filter import RegexFilter
            self._regex_filter = RegexFilter()
        return self._regex_filter

    def _get_prompt_guard(self):
        if self._prompt_guard is None:
            from defenses.prompt_guard import PromptGuard
            self._prompt_guard = PromptGuard()
        return self._prompt_guard

    def _get_nli_guardrail(self):
        if self._nli_guardrail is None:
            from defenses.nli_guardrail import NLISemanticGuardrail
            self._nli_guardrail = NLISemanticGuardrail()
        return self._nli_guardrail

    def _get_retrieval_defense(self):
        if self._retrieval_checker is None:
            from defenses.retrieval_defense import (
                RetrievalIntegrityChecker, ResponseGroundingVerifier
            )
            from sentence_transformers import SentenceTransformer
            from config import KB_STATS_PATH, GROUNDING_THRESHOLD, EMBEDDING_MODEL
            self._retrieval_checker  = RetrievalIntegrityChecker(KB_STATS_PATH)
            emb_model = SentenceTransformer(EMBEDDING_MODEL)
            self._grounding_verifier = ResponseGroundingVerifier(
                emb_model, threshold=GROUNDING_THRESHOLD
            )
        return self._retrieval_checker, self._grounding_verifier

    # ------------------------------------------------------------------ #
    #  Main query entrypoint
    # ------------------------------------------------------------------ #
    def query(
        self,
        user_input: str,
        reset_history: bool = False,
    ) -> SuccessResponse | BlockedResponse:
        """
        Executes the full defense pipeline in order (§5.2):
          1. Input filtering
          2. Retrieval (+ optional integrity check)
          3. Generation
          4. Output filtering (regex → guard → NLI → grounding)
          5. Return response with audit trail
        """
        if reset_history:
            self.conversation_history = []

        audit: List[dict] = []
        t_start = time.perf_counter()

        # ══════════════════════════════════════════
        # STAGE 1 — Input Filtering
        # ══════════════════════════════════════════
        if self.cfg.get("input_regex"):
            result = self._get_regex_filter().filter_input(user_input)
            audit.append({"stage": "input_regex", **result})
            if result["blocked"]:
                return BlockedResponse(
                    trigger="input_regex", stage="input",
                    original_text=user_input, audit_trail=audit
                )

        if self.cfg.get("input_prompt_guard"):
            result = self._get_prompt_guard().classify(user_input)
            audit.append({"stage": "input_prompt_guard", **result})
            if result["blocked"]:
                return BlockedResponse(
                    trigger="input_guard", stage="input",
                    original_text=user_input, audit_trail=audit
                )

        # ══════════════════════════════════════════
        # STAGE 2 — Retrieval
        # ══════════════════════════════════════════
        docs, chunk_embeddings = self.vs.retrieve(user_input)
        retrieved_texts = [d.page_content for d in docs]
        context = "\n\n---\n\n".join(retrieved_texts)

        integrity_result = None
        if self.cfg.get("retrieval_defense"):
            checker, _ = self._get_retrieval_defense()
            integrity_result = checker.check(retrieved_texts, chunk_embeddings)
            audit.append({"stage": "retrieval_integrity", **integrity_result})
            # Log warning but continue — we do not block here
            if not integrity_result["integrity_ok"]:
                audit[-1]["warning"] = "Anomalous chunks detected in retrieval"

        # ══════════════════════════════════════════
        # STAGE 3 — Generation
        # ══════════════════════════════════════════
        prompt_type = self.cfg.get("prompt_type", "basic")

        if self.cfg.get("multiturn") and self.conversation_history:
            history_str = "\n".join(
                f"{role.upper()}: {content}"
                for role, content in self.conversation_history
            )
            formatted_prompt = format_prompt(
                "multiturn_safe", context, user_input, history=history_str
            )
        else:
            formatted_prompt = format_prompt(prompt_type, context, user_input)

        response_text, latency = self.llm.generate(formatted_prompt)

        # Parse internal thoughts from safe prompt
        internal_thoughts = ""
        final_response    = response_text
        if "[Internal thoughts]" in response_text:
            parts = response_text.split("[Final response]")
            if len(parts) == 2:
                internal_thoughts = parts[0].replace("[Internal thoughts]:", "").strip()
                final_response    = parts[1].strip()
            else:
                # Fallback: use full response as final
                final_response = response_text

        # Update conversation history for multi-turn
        if self.cfg.get("multiturn"):
            self.conversation_history.append(("user",      user_input))
            self.conversation_history.append(("assistant", final_response))

        # ══════════════════════════════════════════
        # STAGE 4 — Output Filtering
        # ══════════════════════════════════════════
        if self.cfg.get("output_regex"):
            result = self._get_regex_filter().filter_output(final_response)
            audit.append({"stage": "output_regex", **result})
            if result["blocked"]:
                return BlockedResponse(
                    trigger="output_regex", stage="output",
                    original_text=final_response, audit_trail=audit
                )

        if self.cfg.get("output_prompt_guard"):
            result = self._get_prompt_guard().classify(final_response)
            audit.append({"stage": "output_prompt_guard", **result})
            if result["blocked"]:
                return BlockedResponse(
                    trigger="output_guard", stage="output",
                    original_text=final_response, audit_trail=audit
                )

        if self.cfg.get("nli_guardrail"):
            result = self._get_nli_guardrail().classify(final_response)
            audit.append({"stage": "nli_guardrail", **result})
            if result["blocked"]:
                return BlockedResponse(
                    trigger="nli_guardrail", stage="output",
                    original_text=final_response, audit_trail=audit
                )

        if self.cfg.get("retrieval_defense"):
            _, verifier = self._get_retrieval_defense()
            result = verifier.verify(final_response, retrieved_texts)
            audit.append({"stage": "grounding_verifier", **result})
            if result["flagged"]:
                return BlockedResponse(
                    trigger="grounding_verifier", stage="output",
                    original_text=final_response, audit_trail=audit
                )

        # ══════════════════════════════════════════
        # STAGE 5 — Return
        # ══════════════════════════════════════════
        total_latency = time.perf_counter() - t_start
        return SuccessResponse(
            text=final_response,
            internal_thoughts=internal_thoughts,
            retrieved_chunks=retrieved_texts,
            latency_s=total_latency,
            audit_trail=audit,
        )

    def reset(self):
        """Clear conversation history."""
        self.conversation_history = []
