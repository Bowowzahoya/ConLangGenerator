"""The resolved generation request: a free-text prompt, an LLM-classified
graded reading of it (``traits``), and explicit hard overrides.

Two structurally separate channels feed generation, and they must not be
confused:

- ``traits`` comes from ``generation/prompt_classifier.py`` reading
  ``prompt``. Its values scale directly to probability (see ``TraitProfile``
  and ``generation/trait_bias.py``) -- a confident reading behaves close to
  a guarantee, but the classifier is calibrated to rarely be that confident.
  It's inference, not a command.
- ``force_isolated``/``force_high_altitude``/``force_tonal``/
  ``forced_orthography`` come only from explicit CLI flags (default
  ``False``/all-``None``) and guarantee their outcome outright regardless
  of the prompt or the classifier's assessment. This is the unconditional
  channel testing should use.

``seed_examples`` is a third, similarly explicit channel: literal words a
user supplies (not inferred, not probabilistic) that must appear verbatim
in the generated lexicon -- see ``generation/seed_examples.py`` for how
``ipa`` gets filled in when not given directly.
"""

from __future__ import annotations

from pydantic import BaseModel

from conlang_generator.core.romanization import OrthographyForce
from conlang_generator.core.traits import TraitProfile


class SeedExample(BaseModel, frozen=True):
    gloss: str
    form: str
    """The user's own spelling of the word -- orthography, not IPA."""
    ipa: str | None = None
    """Explicit pronunciation if the user gave one; ``None`` means
    ``generation/seed_examples.resolve_seed_examples`` should guess one
    from ``form`` before generation runs."""


class GenerationSpec(BaseModel, frozen=True):
    prompt: str
    seed: int
    traits: TraitProfile = TraitProfile()
    force_isolated: bool = False
    force_high_altitude: bool = False
    force_tonal: bool = False
    forced_orthography: OrthographyForce = OrthographyForce()
    """Same unconditional channel as the ``force_*`` fields above, for the
    romanization layer specifically -- see ``OrthographyForce``'s own
    docstring. All-``None`` (the default) means "not forced, let
    ``traits.contact_languages``/``traits.requested_orthography_style``/
    the normal roll decide" -- see ``generation/romanization_gen.py``."""
    fantasy: bool = False
    """Simple explicit metadata (not a graded trait) -- passed as context to
    the classifier and to word-coinage prompts."""
    seed_examples: tuple[SeedExample, ...] = ()
    """Literal words the user supplied; always fully resolved (``ipa`` set)
    by the time this reaches ``generate_language`` -- see
    ``cli/main.py``'s ``generate`` command."""
    allow_all_caps: bool = False
    """Opt-in gate (default off) for `romanization_gen`'s all-caps POS
    roll -- unlike `force_*` above, this *permits* a possibility rather
    than forcing one: no real language renders whole word classes in full
    caps, so a plain run should never produce one unless the user asks."""
