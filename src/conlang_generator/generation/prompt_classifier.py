"""LLM stage that reads the free-text generation prompt and produces a
graded, bipolar ``TraitProfile`` (see ``core/traits.py``).

A trait's strength feeds ``generation/trait_bias.biased_probability``
directly -- a value near +1.0 means near-certainty for the named pole, near
-1.0 means near-certainty for its *opposite*, not a value nudged short of
either. That makes calibration here the real safety valve, not a
mathematical cap: the system prompt below instructs independent,
evidence-based rating per dimension (in either direction) and gives worked
examples, specifically so a single vivid detail (e.g. "mountains") doesn't
inflate unrelated dimensions, and so values near +-1.0 stay rare, reserved
for text that is genuinely explicit and central. A user who wants a
guarantee *regardless* of what the prompt says should use
``GenerationSpec``'s separate ``force_*`` fields (explicit CLI flags)
instead of relying on wording alone.

Parsing is lenient by design: a malformed or missing field degrades to "no
evidence" rather than raising, since an LLM's JSON is not a reliable typed
API.
"""

from __future__ import annotations

import json
import re

from conlang_generator.core.traits import GRADED_TRAIT_FIELDS, TraitProfile
from conlang_generator.llm.base import LLMClient, LLMRequest
from conlang_generator.llm.pricing import DEFAULT_MODEL

_LIST_FIELDS = ("contact_languages", "salient_vocabulary_domains")

_DIMENSION_POLES = """- isolation: + isolated/cut off from outsiders; - well-connected/cosmopolitan
- altitude: + high-altitude/mountainous; - lowland/coastal
- community_scale: + small, tight-knit community; - large, diffuse population
- contact_intensity: + heavy trade/contact/mixing with other languages; - little outside contact
- social_hierarchy: + strongly hierarchical/status-conscious; - strongly egalitarian
- orality_literacy: + oral tradition, little/no writing; - strongly literate/standardized written tradition
- evidentiality_culture: + culture emphasizes how you know something; - doesn't care how you know something
- spatial_reference: + absolute/geocentric reference (cardinal directions); - relative reference (left/right)
- ritual_register: + a distinct magic/religious/ritual speech register; - no such distinct register
- aesthetic_harshness: + harsh/guttural sound; - soft/melodic sound
- tonal_friendliness: + tonal/pitch-based meaning; - explicitly not tonal (e.g. stress-only)
- taboo_register: + an avoidance/taboo speech register; - no such register
- terrain_communication_distance: + need for loud/long-distance communication; - close-quarters, no such need"""

_SYSTEM_PROMPT = f"""You classify a free-text description of a constructed language \
against a fixed set of dimensions known to shape real languages. For each \
dimension, output a number from -1.0 to 1.0 -- this number is used directly \
as the (signed) probability the generated language ends up with that \
characteristic: positive values are evidence FOR the named pole, negative \
values are evidence FOR its opposite. It must reflect your genuine \
confidence and direction, not just a guess:

- 0.0 means the text gives no evidence at all, in either direction, for \
that dimension. This is the correct answer for most dimensions on most \
prompts -- do not force a guess.
- Values with absolute value at or below ~0.3 are for anything only \
briefly or incidentally mentioned, in whichever direction.
- Values with absolute value above ~0.7 are reserved for descriptions \
where that dimension is explicit and central, not incidental.
- Values with absolute value above ~0.9 mean near-certainty and should be \
rare in either direction -- reserve them for text that leaves virtually no \
doubt (e.g. the request explicitly and repeatedly insists on that \
characteristic, or explicitly and repeatedly rules it out). Most prompts, \
even detailed ones, should not produce any value this extreme.
- Rate each dimension independently, from direct textual evidence for THAT \
dimension only. A detail supporting one dimension (e.g. a mountain setting \
supporting "altitude") says nothing about unrelated dimensions (e.g. \
"isolation", "social_hierarchy") unless the text separately supports them. \
Do not let one vivid detail inflate the whole profile.

Dimensions, with what a positive (+) vs. negative (-) value means for each:
{_DIMENSION_POLES}

Also extract:
- "contact_languages": named real languages/language families the text \
mentions or clearly evokes, as a list of strings (usually empty).
- "salient_vocabulary_domains": short domain words for subsistence/culture \
implied by the text, e.g. "seafaring", "herding" (usually empty).
- "time_depth_years": an integer if the text asks how a language would \
sound after some number of years, otherwise null.
- "salient_context": one short sentence noting anything else distinctive \
about the request not captured above, or "" if nothing is.

Three worked examples:

Prompt: "a language spoken in the mountains"
-> altitude: 0.3, every other dimension: 0.0, all lists empty, \
salient_context: "". (One incidental detail gets a modest positive value \
on the one dimension it actually supports, nothing else.)

Prompt: "an extremely isolated, xenophobic society with no contact with \
outsiders for a thousand years, living at brutal high altitude where the \
air is thin"
-> altitude: 0.9, isolation: 0.95, contact_intensity: 0.0, \
time_depth_years: null, every other dimension: 0.0. (Multiple dimensions \
are high here only because the text separately and explicitly supports \
each one, not because they were inferred from each other.)

Prompt: "a modern trade-hub language, explicitly NOT tonal, spoken by a \
large, well-connected population with no meaningful writing tradition"
-> tonal_friendliness: -0.85 (explicitly ruled out), contact_intensity: \
0.7, community_scale: -0.6 (large/well-connected, the opposite pole), \
orality_literacy: 0.5, every other dimension: 0.0. (Evidence can point at \
the negative pole just as confidently as the positive one.)

Respond with ONLY a single JSON object, no prose, no markdown fences."""


def classify_prompt(prompt: str, fantasy: bool, llm_client: LLMClient) -> TraitProfile:
    context_note = " (Note: this is for a fantasy setting.)" if fantasy else ""
    request = LLMRequest(
        system=_SYSTEM_PROMPT,
        prompt=f"{prompt}{context_note}",
        model=DEFAULT_MODEL,
        max_tokens=600,
        purpose="prompt.classify_traits",
        metadata={
            "fake_strategy": "trait_profile",
            "trait_fields": ",".join(GRADED_TRAIT_FIELDS),
        },
    )
    response = llm_client.complete(request)
    return _parse(response.text)


def _parse(text: str) -> TraitProfile:
    match = re.search(r"\{.*?\}", text, re.DOTALL)
    if match is None:
        return TraitProfile()
    try:
        raw = json.loads(match.group(0))
    except json.JSONDecodeError:
        return TraitProfile()
    if not isinstance(raw, dict):
        return TraitProfile()

    values: dict[str, object] = {field: _coerce_bipolar_float(raw.get(field)) for field in GRADED_TRAIT_FIELDS}
    for field in _LIST_FIELDS:
        values[field] = _coerce_str_tuple(raw.get(field))
    values["time_depth_years"] = _coerce_optional_int(raw.get("time_depth_years"))
    values["salient_context"] = _coerce_str(raw.get("salient_context"))

    return TraitProfile(**values)


def _coerce_bipolar_float(value: object) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return max(-1.0, min(1.0, number))


def _coerce_str_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if isinstance(item, str))


def _coerce_optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _coerce_str(value: object) -> str:
    return value if isinstance(value, str) else ""
