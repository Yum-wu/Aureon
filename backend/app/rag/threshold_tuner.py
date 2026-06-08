"""CRAG threshold auto-tuning via grid search.

Optimizes high/low confidence thresholds for retrieval confidence gating
using existing negative QA pairs from the benchmark dataset.

Reference: docs/RAG_OPTIMIZATION_PROMPT.md §2.4
"""

from dataclasses import dataclass
from typing import List, Dict


@dataclass
class ThresholdConfig:
    high: float = 0.05
    low: float = 0.01


def evaluate_thresholds(
    config: ThresholdConfig,
    positive_scores: List[float],
    negative_scores: List[float],
) -> Dict[str, float]:
    """Evaluate classification metrics for given thresholds.

    Args:
        config: Threshold values
        positive_scores: RRF scores from answerable queries
        negative_scores: RRF scores from unanswerable queries
    Returns:
        Dict with precision, recall, f1 keys
    """
    # Three-way CRAG gating using both thresholds:
    # - positive_scores >= config.high  -> true positive (correctly classified as "correct")
    # - config.low <= positive_scores < config.high -> ambiguous (correctly classified, kept in pipeline)
    # - positive_scores < config.low    -> false negative (missed by retrieval)
    # - negative_scores < config.low    -> true negative (correctly rejected)
    # - negative_scores >= config.low   -> false positive (incorrectly passed threshold)
    tp = sum(1 for s in positive_scores if s >= config.high)
    ambiguous = sum(1 for s in positive_scores if config.low <= s < config.high)
    fn = sum(1 for s in positive_scores if s < config.low)
    tn = sum(1 for s in negative_scores if s < config.low)
    fp = sum(1 for s in negative_scores if s >= config.low)

    # Ambiguous scores are "at least ambiguous" — not false negatives.
    # For precision/recall we treat them as correctly retrieved (not missed).
    effective_tp = tp + ambiguous

    precision = effective_tp / (effective_tp + fp) if (effective_tp + fp) > 0 else 0.0
    recall = effective_tp / (effective_tp + fn) if (effective_tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {"precision": precision, "recall": recall, "f1": f1}


def grid_search_thresholds(
    positive_scores: List[float],
    negative_scores: List[float],
) -> ThresholdConfig:
    """Grid search over threshold combinations to maximize F1.

    Args:
        positive_scores: Scores from answerable queries
        negative_scores: Scores from unanswerable queries
    Returns:
        ThresholdConfig with best F1 score
    """
    best_config = ThresholdConfig()
    best_f1 = -1.0

    for high in [0.03, 0.05, 0.07, 0.10]:
        for low in [0.005, 0.01, 0.02]:
            if low >= high:
                continue
            cfg = ThresholdConfig(high=high, low=low)
            metrics = evaluate_thresholds(cfg, positive_scores, negative_scores)
            if metrics["f1"] > best_f1:
                best_f1 = metrics["f1"]
                best_config = cfg

    return best_config
