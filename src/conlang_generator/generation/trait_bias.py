"""Turns a graded, bipolar trait strength directly into a probability of
the matching outcome.

``strength=0.0`` (no textual evidence either way) leaves the world-typical
base rate untouched -- that pure chance draw *is* the "randomly pick when
unspecified" behavior, no separate mechanism needed. ``strength=1.0``
(strongest positive evidence) means certainty; ``strength=-1.0`` (strongest
evidence for the *opposite*) means the outcome is impossible. The trait
strength *is* the intended likelihood in either direction, not a nudge
capped short of it.

The interpolation is asymmetric in absolute terms by construction: a rare
event (small ``base_rate``) has little room to get rarer and a lot of room
to get more common, so the negative-going slope is shallower than the
positive-going one. That's the mathematically correct way to bound a
bipolar interpolation into ``[0, 1]``, not an inconsistency.

The safety valve against an inferred trait behaving like an accidental hard
guarantee (in either direction) is the classifier's calibration (see
``generation/prompt_classifier.py``), which is deliberately written to
rarely output values near +-1.0 -- not a mathematical cap here. A user who
wants a guarantee regardless of what the prompt says should use the
separate ``force_*`` fields on ``core.spec.GenerationSpec`` instead.
"""

from __future__ import annotations


def biased_probability(base_rate: float, strength: float) -> float:
    strength = max(-1.0, min(1.0, strength))
    if strength >= 0:
        return base_rate + strength * (1.0 - base_rate)
    return base_rate + strength * base_rate
