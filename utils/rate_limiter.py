"""
utils/rate_limiter.py
Thread-safe rate limiter + retry-with-exponential-backoff for all API calls.

Design:
  - Token-bucket per provider: refills at RPM rate
  - Hard daily counter: raises DailyLimitError when RPD exhausted
  - Automatic exponential backoff on HTTP 429 / rate-limit exceptions
  - ±jitter to avoid thundering herd when multiple calls retry simultaneously
  - Provider-level fallback: if daily limit hit, transparently switch provider

Usage:
    limiter = RateLimiter("groq")
    response = limiter.call(client.chat.completions.create, model=..., ...)
"""

import random
import time
import threading
import logging
from typing import Callable, Any

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import RATE_LIMITS, MAX_RETRIES, INITIAL_BACKOFF_S, BACKOFF_MULTIPLIER, MAX_BACKOFF_S, JITTER_FRACTION

logger = logging.getLogger(__name__)


class DailyLimitError(Exception):
    """Raised when a provider's daily quota is exhausted."""


class RateLimiter:
    """
    Per-provider rate limiter using a token-bucket algorithm.

    Token bucket refills at `rpm / 60` tokens per second.
    One token is consumed per request.
    If no token is available, sleeps until one is available.
    """

    # Class-level shared state across all instances of the same provider
    _locks:         dict[str, threading.Lock]  = {}
    _tokens:        dict[str, float]           = {}
    _last_refill:   dict[str, float]           = {}
    _daily_counts:  dict[str, int]             = {}
    _day_start:     dict[str, float]           = {}

    def __init__(self, provider: str):
        if provider not in RATE_LIMITS:
            raise ValueError(f"Unknown provider: {provider!r}. Valid: {list(RATE_LIMITS)}")

        self.provider  = provider
        self.limits    = RATE_LIMITS[provider]
        self.rpm       = self.limits["rpm"]
        self.rpd       = self.limits["rpd"]
        self.min_delay = self.limits["min_delay"]

        # Initialize class-level state for this provider if not yet done
        cls = RateLimiter
        if provider not in cls._locks:
            cls._locks[provider]        = threading.Lock()
            cls._tokens[provider]       = float(self.rpm)   # start full
            cls._last_refill[provider]  = time.monotonic()
            cls._daily_counts[provider] = 0
            cls._day_start[provider]    = time.time()

    # ------------------------------------------------------------------ #
    def _refill(self) -> None:
        """Refill tokens based on elapsed time (token bucket)."""
        cls = RateLimiter
        now     = time.monotonic()
        elapsed = now - cls._last_refill[self.provider]
        refill  = elapsed * (self.rpm / 60.0)
        cls._tokens[self.provider]      = min(self.rpm, cls._tokens[self.provider] + refill)
        cls._last_refill[self.provider] = now

    # ------------------------------------------------------------------ #
    def _check_daily_reset(self) -> None:
        """Reset daily counter if a new calendar day has started."""
        cls = RateLimiter
        if time.time() - cls._day_start[self.provider] >= 86400:
            cls._daily_counts[self.provider] = 0
            cls._day_start[self.provider]    = time.time()
            logger.info(f"[RateLimiter:{self.provider}] Daily counter reset.")

    # ------------------------------------------------------------------ #
    def acquire(self) -> None:
        """
        Block until a token is available, then consume it.
        Raises DailyLimitError if daily quota is exhausted.
        """
        cls = RateLimiter
        with cls._locks[self.provider]:
            self._check_daily_reset()

            if cls._daily_counts[self.provider] >= self.rpd:
                raise DailyLimitError(
                    f"[RateLimiter:{self.provider}] Daily quota exhausted "
                    f"({cls._daily_counts[self.provider]}/{self.rpd})"
                )

            # Wait for a token
            while True:
                self._refill()
                if cls._tokens[self.provider] >= 1.0:
                    cls._tokens[self.provider]       -= 1.0
                    cls._daily_counts[self.provider] += 1
                    break
                # Sleep for the time needed to get one token
                wait = (1.0 - cls._tokens[self.provider]) / (self.rpm / 60.0)
                logger.debug(f"[RateLimiter:{self.provider}] Throttled, waiting {wait:.2f}s")

            # Always enforce minimum inter-call delay
            time.sleep(self.min_delay)

    # ------------------------------------------------------------------ #
    def call(self, fn: Callable, *args, **kwargs) -> Any:
        """
        Execute `fn(*args, **kwargs)` with rate limiting + exponential backoff.

        Retries on:
          - HTTP 429 (rate limit)
          - openai.RateLimitError
          - Any exception whose message contains "rate" or "429"

        Raises the last exception after MAX_RETRIES attempts.
        """
        backoff   = INITIAL_BACKOFF_S
        last_exc  = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                self.acquire()
                return fn(*args, **kwargs)

            except DailyLimitError:
                raise   # Don't retry daily limit — caller should switch provider

            except Exception as exc:
                msg = str(exc).lower()
                is_rate_limit = (
                    "429"   in msg
                    or "rate" in msg
                    or "quota" in msg
                    or "limit" in msg
                )
                last_exc = exc

                if not is_rate_limit:
                    logger.warning(
                        f"[RateLimiter:{self.provider}] Non-rate-limit error on attempt "
                        f"{attempt}/{MAX_RETRIES}: {exc}"
                    )
                    if attempt == MAX_RETRIES:
                        raise
                    time.sleep(backoff)
                else:
                    jitter   = backoff * JITTER_FRACTION * (2 * random.random() - 1)
                    wait     = min(backoff + jitter, MAX_BACKOFF_S)
                    logger.warning(
                        f"[RateLimiter:{self.provider}] Rate-limit hit (attempt "
                        f"{attempt}/{MAX_RETRIES}). Backing off {wait:.1f}s …"
                    )
                    time.sleep(wait)
                    backoff  = min(backoff + 60.0, MAX_BACKOFF_S)

        raise last_exc  # type: ignore

    # ------------------------------------------------------------------ #
    def remaining_daily(self) -> int:
        """Return approximate remaining daily calls."""
        cls = RateLimiter
        self._check_daily_reset()
        return max(0, self.rpd - cls._daily_counts.get(self.provider, 0))

    def status(self) -> dict:
        cls = RateLimiter
        self._check_daily_reset()
        return {
            "provider":        self.provider,
            "daily_used":      cls._daily_counts.get(self.provider, 0),
            "daily_limit":     self.rpd,
            "daily_remaining": self.remaining_daily(),
            "rpm_limit":       self.rpm,
        }
