"""The resolved generation request: a free-text prompt plus typological hints.

``GenerationSpec`` is what ``generation/generator.py`` actually consumes. In v0
the hints are supplied directly (CLI flags or defaults); a future pass can add
an LLM step that reads ``prompt`` and fills in the hints automatically.
"""

from __future__ import annotations

from pydantic import BaseModel


class GenerationSpec(BaseModel, frozen=True):
    prompt: str
    seed: int
    isolated: bool = False
    """Geographically/socially isolated -- nudges toward less common, more
    internally-elaborated typology (small illustrative effect, see
    generation/grammar_gen.py)."""
    high_altitude: bool = False
    """Nudges toward ejective consonants, per Everett (2013)."""
    tonal: bool = False
    contact_languages: tuple[str, ...] = ()
    """Named languages this conlang is meant to evoke or mix; currently only
    recorded as metadata -- not yet used to bias generation (v0 limitation)."""
    time_depth_years: int | None = None
    """"How would this sound in N years" -- accepted but not yet applied;
    diachronic sound change is future work (v0 limitation)."""
    fantasy: bool = False
