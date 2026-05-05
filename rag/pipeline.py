"""
rag/pipeline.py
End-to-end RAG query pipeline with pluggable defense components.
Implements FinancialRAGPipeline and LLMWrapper as specified in §5.2-5.3.

Free-tier LLM providers (all use OpenAI-compatible REST):
  - groq:       https://api.groq.com/openai/v1          (primary — 14400 RPD)
  - gemini:     https://generativelanguage.googleapis.com/v1beta/openai/
  - openrouter: https://openrouter.ai/api/v1             (fallback)
"""

import time
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    BASE_LLM_PROVIDER, BASE_LLM_MODEL,
    FALLBACK_LLM_PROVIDER, FALLBACK_LLM_MODEL,
    GROQ_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY,
    PROVIDER_ENDPOINTS, HF_TOKEN,
    FAISS_INDEX_DIR, KB_STATS_PATH, TOP_K_RETRIEVAL,
)
from rag.system_prompts import format_prompt
from rag.vector_store import VectorStore
from utils.rate_limiter import RateLimiter, DailyLimitError

logger = logging.getLogger(__name__)

_PROVIDER_API_KEYS = {
    "groq":        lambda: GROQ_API_KEY,
    "gemini":      lambda: GEMINI_API_KEY,
    "openrouter":  lambda: OPENROUTER_API_KEY,
    "huggingface": lambda: HF_TOKEN,
}


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
    Unified LLM interface for FREE-TIER providers.

    All three providers (groq, gemini, openrouter) use the OpenAI-compatible
    REST format — only the base_url and api_key differ.

    Automatic provider fallback:
      If the primary provider hits its daily limit, falls back to
      FALLBACK_LLM_PROVIDER (openrouter) transparently.

    Rate limiting:
      Each provider has its own RateLimiter instance enforcing RPM + min_delay.
      All calls go through limiter.call() which handles exponential backoff.
    """

    def __init__(
        self,
        provider: str = BASE_LLM_PROVIDER,
        model: str = BASE_LLM_MODEL,
        hf_token: str | None = HF_TOKEN,
    ):
        self.provider    = provider
        self.model_name  = model
        self._hf_token   = hf_token

        if provider == "local":
            self._init_local(hf_token)
            self._client   = None
            self._limiter  = None
        else:
            self._client, self._limiter = self._build_client(provider)
            # Fallback client (OpenRouter)
            if provider != FALLBACK_LLM_PROVIDER:
                try:
                    self._fallback_client, self._fallback_limiter = \
                        self._build_client(FALLBACK_LLM_PROVIDER)
                    self._fallback_model = FALLBACK_LLM_MODEL
                except Exception:
                    self._fallback_client = None
                    self._fallback_limiter = None
                    self._fallback_model  = None
            else:
                self._fallback_client = None
                self._fallback_limiter = None
                self._fallback_model  = None

    _GLOBAL_LOCAL_MODEL = None
    _GLOBAL_LOCAL_TOKENIZER = None

    def _init_local(self, hf_token):
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch
        import platform

        if LLMWrapper._GLOBAL_LOCAL_MODEL is None:
            is_linux = platform.system() == "Linux"

            # ---- Kaggle / Linux: 3B 4-bit + Flash Attention 2 + dual GPU ----
            bnb_ok = False
            if is_linux:
                try:
                    from transformers import BitsAndBytesConfig
                    import bitsandbytes as _bnb  # noqa: F401
                    if hasattr(_bnb, 'COMPILED_WITH_CUDA') and not _bnb.COMPILED_WITH_CUDA:
                        raise ImportError("bitsandbytes installed without CUDA support")
                    bnb_ok = True
                except (ImportError, ModuleNotFoundError, Exception) as e:
                    print(f"[LLM] bitsandbytes unavailable ({e})")

            if bnb_ok:
                model_name = "Qwen/Qwen2.5-3B-Instruct"
                bnb_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_use_double_quant=True,
                )
                print(f"[LLM] Loading {model_name} 4-bit NF4 on cuda:0")
                LLMWrapper._GLOBAL_LOCAL_TOKENIZER = AutoTokenizer.from_pretrained(
                    model_name, token=hf_token
                )
                LLMWrapper._GLOBAL_LOCAL_MODEL = AutoModelForCausalLM.from_pretrained(
                    model_name,
                    quantization_config=bnb_config,
                    device_map="cuda:0",
                    token=hf_token,
                )
            else:
                # ---- Windows fallback: 1.5B FP16 (no flash attn, no bnb) ----
                model_name = "Qwen/Qwen2.5-1.5B-Instruct"
                print(f"[LLM] Falling back to {model_name} FP16")
                LLMWrapper._GLOBAL_LOCAL_TOKENIZER = AutoTokenizer.from_pretrained(
                    model_name, token=hf_token
                )
                LLMWrapper._GLOBAL_LOCAL_MODEL = AutoModelForCausalLM.from_pretrained(
                    model_name,
                    device_map="auto",
                    torch_dtype=torch.float16,
                    token=hf_token,
                )

        self.tokenizer = LLMWrapper._GLOBAL_LOCAL_TOKENIZER
        self.model = LLMWrapper._GLOBAL_LOCAL_MODEL

    def _build_client(self, provider: str):
        """Build a client pointed at the given provider."""
        import openai
        api_key  = _PROVIDER_API_KEYS[provider]()
        base_url = PROVIDER_ENDPOINTS[provider]
        if not api_key:
            raise ValueError(
                f"API key for {provider!r} not set. "
            )
            
        client = openai.OpenAI(api_key=api_key, base_url=base_url)
            
        limiter = RateLimiter(provider)
        return client, limiter

    # ------------------------------------------------------------------ #
    def generate(self, prompt: str, max_tokens: int = 512) -> Tuple[str, float]:
        """
        Returns (response_text, latency_seconds).
        Automatically falls back to OpenRouter if the primary provider
        hits its daily limit.
        """
        t0 = time.perf_counter()

        if self.provider == "local":
            text = self._generate_local(prompt, max_tokens)
            return text, time.perf_counter() - t0

        # --- Primary provider ------------------------------------------ #
        try:
            text = self._limiter.call(
                self._api_call, self._client, self.model_name, prompt, max_tokens
            )
            return text, time.perf_counter() - t0

        except DailyLimitError as e:
            logger.warning(f"[LLMWrapper] {e} — switching to fallback provider.")

        # --- Fallback provider ----------------------------------------- #
        if self._fallback_client is None:
            raise RuntimeError("Primary provider daily limit hit and no fallback configured.")

        text = self._fallback_limiter.call(
            self._api_call, self._fallback_client,
            self._fallback_model, prompt, max_tokens
        )
        return text, time.perf_counter() - t0

    # ------------------------------------------------------------------ #
    @staticmethod
    def _api_call(client, model: str, prompt: str, max_tokens: int) -> str:
        """Single OpenAI-compatible API call (used by all providers)."""
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0,
        )
        return resp.choices[0].message.content.strip()

    def _generate_local(self, prompt: str, max_tokens: int) -> str:
        messages = [
            {"role": "system", "content": "You are Qwen, created by Alibaba Cloud. You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ]
        text = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )
        model_inputs = self.tokenizer([text], return_tensors="pt").to(self.model.device)

        generated_ids = self.model.generate(
            **model_inputs,
            max_new_tokens=max_tokens
        )
        generated_ids = [
            output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
        ]

        return self.tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]

    def rate_limiter_status(self) -> dict:
        """Return current rate limiter counters for monitoring."""
        return self._limiter.status() if self._limiter else {}


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
        # STAGE 0 — Stratification (Gap 7 / Stage 5 audit spec)
        # ══════════════════════════════════════════
        try:
            import textstat as _textstat
            flesch = _textstat.flesch_reading_ease(user_input)
            if flesch > 60:
                stratum = "A"
            elif flesch >= 30:
                stratum = "B"
            else:
                stratum = "C"
        except Exception:
            flesch, stratum = None, "B"  # default on error
        audit.append({"stage": "stratification", "stratum": stratum, "flesch_score": flesch})

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
            n_anomalous = len(integrity_result["anomalous_chunk_indices"])
            n_total     = len(retrieved_texts)
            if n_anomalous == n_total and n_total > 0:
                # ALL retrieved chunks are anomalous — KB likely fully poisoned
                audit[-1]["warning"] = "ALL chunks anomalous — retrieval blocked"
                return BlockedResponse(
                    trigger="retrieval_integrity", stage="retrieval",
                    original_text=user_input, audit_trail=audit
                )
            elif n_anomalous > 0:
                audit[-1]["warning"] = f"{n_anomalous}/{n_total} anomalous chunks detected — continuing with warning"

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

        # Parse internal thoughts from safe prompt (case-insensitive, colon-tolerant)
        internal_thoughts = ""
        final_response    = response_text
        _resp_lower = response_text.lower()
        if "[internal thoughts" in _resp_lower:
            import re as _re
            # Split on [Final response] or [Final response:] — case-insensitive
            parts = _re.split(r'\[final response\]:?', response_text, maxsplit=1, flags=_re.IGNORECASE)
            if len(parts) == 2:
                # Strip the [Internal thoughts] / [Internal thoughts:] header from part[0]
                thought_raw = _re.sub(
                    r'^\[internal thoughts\]:?\s*', '', parts[0].strip(), flags=_re.IGNORECASE
                )
                internal_thoughts = thought_raw.strip()
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
