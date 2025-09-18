"""Utility helpers for randomness, weighting, and backoff."""

from __future__ import annotations

import random
from typing import Sequence, TypeVar

T = TypeVar("T")


def weighted_choice(items: Sequence[T], weights: Sequence[float], *, random_fn=random.random) -> T:
    """Choose a single item based on weights."""

    if not items:
        raise ValueError("items must be non-empty")
    if len(weights) != len(items):
        raise ValueError("weights length must match items")
    total = sum(weights)
    if total <= 0:
        return random.choice(items)
    threshold = random_fn() * total
    cumulative = 0.0
    for item, weight in zip(items, weights):
        cumulative += weight
        if cumulative >= threshold:
            return item
    return items[-1]


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(min(value, maximum), minimum)


__all__ = ["weighted_choice", "clamp"]
