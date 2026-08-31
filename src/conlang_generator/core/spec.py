"""The resolved generation request: a free-text prompt, an LLM-classified
graded reading of it (``traits``), and explicit hard overrides.

Two structurally separate channels feed generation, and they must not be
confused:

- ``traits`` comes from ``generation/prompt_classifier.py`` reading
  ``prompt``. Its values scale directly to probability (see ``TraitProfile``
  and ``generation/trait_bias.py``) -- a confident reading behaves close to
  a guarantee, but the classifier is calibrated to rarely be that confident.
  It's inference, not a command.
- ``force_isolated``/``force_high_altitude``/``force_tonal`` come only from
  explicit CLI flags (default ``False``) and guarantee their outcome
  outright regardless of the prompt or the classifier's assessment. This is
  the unconditional channel testing should use.
"""

from __future__ import annotations

from pydantic import BaseModel

from conlang_generator.core.traits import TraitProfile


class GenerationSpec(BaseModel, frozen=True):
    prompt: str
    seed: int
    traits: TraitProfile = TraitProfile()
    force_isolated: bool = False
    force_high_altitude: bool = False
    force_tonal: bool = False
    fantasy: bool = False
    """Simple explicit metadata (not a graded trait) -- passed as context to
    the classifier and to word-coinage prompts."""
