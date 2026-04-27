"""
evaluation/latency_tracker.py
Wall-clock latency measurement for RAG pipeline responses (Section 12.2).
Tracks individual readings and computes summary statistics.
"""

import time
import statistics
from typing import List


class LatencyTracker:
    """
    Simple accumulator for response latency measurements.

    Usage::
        tracker = LatencyTracker()
        tracker.record(response.latency_s)   # SuccessResponse.latency_s
        stats = tracker.summary()
    """

    def __init__(self):
        self._readings: List[float] = []

    def record(self, latency_s: float) -> None:
        self._readings.append(latency_s)

    def summary(self) -> dict:
        """
        Returns:
            {
                "n":      int,
                "mean_s": float,
                "std_s":  float,
                "min_s":  float,
                "max_s":  float,
                "p50_s":  float,
                "p95_s":  float,
            }
        """
        if not self._readings:
            return {"n": 0, "mean_s": 0.0, "std_s": 0.0,
                    "min_s": 0.0, "max_s": 0.0, "p50_s": 0.0, "p95_s": 0.0}

        sorted_r = sorted(self._readings)
        n        = len(sorted_r)

        def pct(p: float) -> float:
            idx = int(p / 100 * n)
            return sorted_r[min(idx, n - 1)]

        return {
            "n":      n,
            "mean_s": statistics.mean(self._readings),
            "std_s":  statistics.stdev(self._readings) if n > 1 else 0.0,
            "min_s":  sorted_r[0],
            "max_s":  sorted_r[-1],
            "p50_s":  pct(50),
            "p95_s":  pct(95),
        }

    def reset(self) -> None:
        self._readings = []

    def __len__(self) -> int:
        return len(self._readings)
