"""The graded reading of a free-text prompt against a broad set of factors
known to shape real languages (terrain, community structure, contact
history, culture, aesthetics -- see ``generation/prompt_classifier.py`` for
where this gets filled in).

Every float field is ``0.0`` by default, meaning "no textual evidence
either way" -- generation consumers treat that as "use the world-typical
base rate," not as a separate randomization step. Fields are bipolar,
``[-1.0, 1.0]``: a positive value is evidence *for* the named pole (scaling
up toward certainty at ``1.0``), a negative value is evidence for its
*opposite* (scaling down toward impossibility at ``-1.0``) -- see
``generation/trait_bias.py`` for the interpolation. The classifier is
calibrated to rarely report values near +-1.0 -- that calibration is the
safety valve, not a mathematical ceiling. A user who wants a guaranteed
outcome regardless of the prompt's wording should use the CLI's separate
``force_*`` fields on ``GenerationSpec`` instead.

Fields are grouped by whether current generation code actually consumes
them yet -- see the module docstring in ``generation/prompt_classifier.py``
and ``architecture/OVERVIEW.md`` for which is which. Unconsumed fields are
still extracted and stored so nothing the classifier notices is thrown away.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

GRADED_TRAIT_FIELDS: tuple[str, ...] = (
    "isolation",
    "altitude",
    "community_scale",
    "contact_intensity",
    "social_hierarchy",
    "orality_literacy",
    "evidentiality_culture",
    "spatial_reference",
    "ritual_register",
    "aesthetic_harshness",
    "tonal_friendliness",
    "taboo_register",
    "terrain_communication_distance",
)


class TraitProfile(BaseModel, frozen=True):
    # -- Consumed by generation today (see phonology_gen.py / grammar_gen.py) --
    isolation: float = Field(default=0.0, ge=-1.0, le=1.0)
    """Positive: geographic/social isolation -- nudges uvular presence,
    ergative alignment, and morphology toward polysynthetic/agglutinative.
    Negative: well-connected/cosmopolitan -- suppresses the same."""
    altitude: float = Field(default=0.0, ge=-1.0, le=1.0)
    """Positive: high-altitude terrain -- nudges ejective consonants
    (Everett 2013). Negative: lowland/coastal -- suppresses them."""
    community_scale: float = Field(default=0.0, ge=-1.0, le=1.0)
    """Positive: small, tight-knit community -- nudges morphology toward
    polysynthetic/agglutinative (Trudgill). Negative: large, diffuse
    community -- suppresses that nudge."""
    contact_intensity: float = Field(default=0.0, ge=-1.0, le=1.0)
    """Positive: heavy contact/trade/creolization history -- nudges
    morphology toward isolating/analytic, opposing ``isolation``/
    ``community_scale``. Negative: little outside contact."""
    aesthetic_harshness: float = Field(default=0.0, ge=-1.0, le=1.0)
    """Positive: harsh/guttural. Negative: soft/melodic. Re-weights
    consonant pool selection either way."""
    tonal_friendliness: float = Field(default=0.0, ge=-1.0, le=1.0)
    """Positive: cultural/practical affinity for lexical tone -- nudges the
    tone system on. Negative: evidence the language explicitly is not
    tonal -- suppresses it below the world-typical base rate."""

    # -- Extracted and stored, not yet consumed by generation --
    social_hierarchy: float = Field(default=0.0, ge=-1.0, le=1.0)
    orality_literacy: float = Field(default=0.0, ge=-1.0, le=1.0)
    evidentiality_culture: float = Field(default=0.0, ge=-1.0, le=1.0)
    spatial_reference: float = Field(default=0.0, ge=-1.0, le=1.0)
    ritual_register: float = Field(default=0.0, ge=-1.0, le=1.0)
    taboo_register: float = Field(default=0.0, ge=-1.0, le=1.0)
    terrain_communication_distance: float = Field(default=0.0, ge=-1.0, le=1.0)

    contact_languages: tuple[str, ...] = ()
    """Named languages this conlang is meant to evoke or mix; recorded only,
    not yet used to bias generation."""
    salient_vocabulary_domains: tuple[str, ...] = ()
    """Subsistence/culture-driven vocabulary domains (e.g. "seafaring",
    "herding"); recorded only, not yet used to expand the core lexicon."""
    time_depth_years: int | None = None
    """"How would this sound in N years" -- recorded only; diachronic sound
    change is future work."""

    salient_context: str = ""
    """Free-text catch-all for anything notable that doesn't map to a field
    above -- the "unknown unknowns" channel. Consumed as extra flavor
    context in word-coinage LLM prompts; never parsed further."""
