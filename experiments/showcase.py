"""Local, regenerable HTML report comparing generated languages across a
fixed set of scenarios -- the way to actually *look at* what a generation-
pipeline change did, instead of reading code or one-off ad hoc scripts.

Not part of the CLI (dev/evaluation tooling, not a product feature -- see
AGENTS.md's CLI discipline). Word-level only for now: phonology + full
lexicon per scenario, no grammar/translation (matches the current focus).

Usage:
    uv run python experiments/showcase.py [--llm fake|anthropic]

Output: experiments/output/showcase.html (gitignored, overwritten each run).
Add new scenarios to SCENARIOS below; nothing else needs to change.
"""

from __future__ import annotations

import argparse
import html
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from conlang_generator.core.spec import GenerationSpec, SeedExample
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.lexicon_gen import CORE_MEANINGS
from conlang_generator.llm.factory import build_llm_client

OUTPUT_PATH = Path(__file__).parent / "output" / "showcase.html"
CACHE_DIR = Path(__file__).parent / "output" / ".cache"


@dataclass(frozen=True)
class Scenario:
    title: str
    seed: int
    traits: TraitProfile = TraitProfile()
    seed_examples: tuple[SeedExample, ...] = ()
    note: str = ""


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        "Isolated harsh mountain tongue", 11,
        TraitProfile(isolation=0.9, altitude=0.9, aesthetic_harshness=0.8, tonal_friendliness=0.5, community_scale=0.7),
    ),
    Scenario(
        "Soft coastal trade tongue", 23,
        TraitProfile(isolation=-0.8, altitude=-0.7, aesthetic_harshness=-0.7, contact_intensity=0.8, community_scale=-0.6, tonal_friendliness=-0.3),
    ),
    Scenario("Dutch-biased", 1, TraitProfile(contact_languages=("Dutch",)), note="--contact-language Dutch"),
    Scenario("Japanese-biased", 59, TraitProfile(contact_languages=("Japanese",)), note="--contact-language Japanese"),
    Scenario(
        "Anchored with seed words", 67,
        TraitProfile(isolation=0.3, aesthetic_harshness=-0.2),
        (SeedExample(gloss="water", form="aqua", ipa="akwa"), SeedExample(gloss="mountain", form="yama", ipa="jama")),
        note="--example water=aqua --example mountain=yama|jama",
    ),
)

_STYLE = """
body { font-family: -apple-system, Segoe UI, sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem;
       background: #1c1d21; color: #e4e4e7; }
h1 { font-size: 1.4rem; }
h2 { font-size: 1.15rem; margin-top: 2.5rem; border-bottom: 1px solid #3a3b42; padding-bottom: 0.3rem; }
.meta { color: #9a9ba3; font-size: 0.85rem; margin-bottom: 0.6rem; }
.note { color: #7fb8e0; font-size: 0.85rem; font-family: monospace; margin-bottom: 0.6rem; }
table { border-collapse: collapse; width: 100%; margin-top: 0.5rem; }
th, td { text-align: left; padding: 0.3rem 0.7rem; border-bottom: 1px solid #2c2d33; font-size: 0.95rem; }
th { color: #9a9ba3; font-weight: 600; }
td.ipa, td.roman { font-family: "Cambria", "Doulos SIL", serif; }
td.ipa { color: #c9a0ff; }
footer { color: #6a6b73; font-size: 0.8rem; margin-top: 3rem; }
"""


def _phonology_summary(language) -> str:
    g, inv, st, ts = language.grammar, language.phonology, language.syllable_structure, language.tone_system
    coda = "none" if st.max_coda == 0 else ("sonorant-only" if st.allowed_coda_consonants is not None else f"unrestricted (max {st.max_coda})")
    return (
        f"order={g.word_order.value} &middot; morph={g.morphological_type.value} &middot; align={g.alignment.value} "
        f"&middot; consonants={len(inv.consonants)} &middot; vowels={len(inv.vowels)} &middot; onset&le;{st.max_onset} "
        f"&middot; coda={coda} &middot; harmony={st.vowel_harmony} &middot; tonal={ts.enabled}"
    )


def _lexicon_table(language) -> str:
    rows = []
    for gloss, _ in CORE_MEANINGS:
        entry = language.lexicon.by_gloss(gloss)
        if entry is None:
            continue
        rows.append(
            f"<tr><td>{html.escape(gloss)}</td>"
            f"<td class='roman'>{html.escape(entry.romanization)}</td>"
            f"<td class='ipa'>/{html.escape(entry.ipa)}/</td>"
            f"<td>{entry.pos.value}</td></tr>"
        )
    return "<table><tr><th>gloss</th><th>romanized</th><th>IPA</th><th>POS</th></tr>" + "\n".join(rows) + "</table>"


def render(scenarios: tuple[Scenario, ...], llm_kind: str) -> str:
    client = build_llm_client(kind=llm_kind, cache_dir=CACHE_DIR)
    sections = []
    for scenario in scenarios:
        spec = GenerationSpec(prompt=scenario.title, seed=scenario.seed, traits=scenario.traits, seed_examples=scenario.seed_examples)
        language = generate_language(scenario.title, spec, client)
        note_html = f"<div class='note'>{html.escape(scenario.note)}</div>" if scenario.note else ""
        sections.append(
            f"<h2>{html.escape(scenario.title)}</h2>"
            f"<div class='meta'>seed={scenario.seed} &middot; {_phonology_summary(language)}</div>"
            f"{note_html}"
            f"{_lexicon_table(language)}"
        )

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"<!doctype html><html><head><meta charset='utf-8'><title>Showcase</title><style>{_STYLE}</style></head>"
        f"<body><h1>ConLangGenerator showcase</h1>"
        f"<div class='meta'>llm={llm_kind} &middot; generated {generated_at} -- re-run "
        f"<code>uv run python experiments/showcase.py</code> after any generation-code change</div>"
        + "".join(sections)
        + f"<footer>Word-level only (phonology + lexicon) -- no grammar/translation shown.</footer>"
        + "</body></html>"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llm", default="fake", choices=["fake", "anthropic"])
    args = parser.parse_args()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(render(SCENARIOS, args.llm), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
