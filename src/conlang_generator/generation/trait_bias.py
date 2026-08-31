"""Turns a graded trait strength directly into a probability of the matching
outcome.

``strength=0.0`` (no textual evidence) leaves the world-typical base rate
untouched -- that pure chance draw *is* the "randomly pick when unspecified"
behavior, no separate mechanism needed. ``strength=1.0`` (strongest textual
evidence) means certainty: the trait strength *is* the intended likelihood of
implementing that characteristic, not a nudge capped short of it.

The safety valve against an inferred trait behaving like an accidental hard
guarantee is the classifier's calibration (see
``generation/prompt_classifier.py``), which is deliberately written to rarely
output values near 1.0 -- not a mathematical ceiling here. A user who wants a
guarantee regardless of what the prompt says should use the separate
``force_*`` fields on ``core.spec.GenerationSpec`` instead.
"""

from __future__ import annotations


def biased_probability(base_rate: float, strength: float) -> float:
    strength = max(0.0, min(1.0, strength))
    return base_rate + strength * (1.0 - base_rate)
