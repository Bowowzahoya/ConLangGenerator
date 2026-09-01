"""Local, regenerable HTML report showing a real language's core vocabulary
next to its sound-changed evolution -- the calibration check for
generation/sound_change.py: does "20 years of English contact" stay
recognizable while "1600 years" drifts a lot, without ever being an
unrecognizable jump?

Not part of the CLI (dev/evaluation tooling, not a product feature -- see
AGENTS.md's CLI discipline).

Usage:
    uv run python experiments/evolution.py [--llm fake|anthropic]

Output: experiments/output/evolution.html (gitignored, overwritten each run).
Add more real-language lexicons to experiments/lexicons.py and more
scenarios to SCENARIOS below; nothing else needs to change.
"""

from __future__ import annotations

import argparse
import html
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lexicons import DUTCH  # noqa: E402

from conlang_generator.core.language import Language
from conlang_generator.core.spec import GenerationSpec, SeedExample
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.sound_change import evolve_language
from conlang_generator.llm.factory import build_llm_client

OUTPUT_PATH = Path(__file__).parent / "output" / "evolution.html"
CACHE_DIR = Path(__file__).parent / "output" / ".cache"
BASE_SEED = 1
EVOLVE_SEED = 42


@dataclass(frozen=True)
class Scenario:
    title: str
    years: int
    traits: TraitProfile


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("20 years, English contact", 20, TraitProfile(contact_intensity=0.85, isolation=-0.6)),
    Scenario("100 years, English contact", 100, TraitProfile(contact_intensity=0.85, isolation=-0.6)),
    Scenario("400 years, English contact", 400, TraitProfile(contact_intensity=0.85, isolation=-0.6)),
    Scenario("1600 years, English contact", 1600, TraitProfile(contact_intensity=0.85, isolation=-0.6)),
    Scenario("200 years, isolated highland", 200, TraitProfile(altitude=0.9, isolation=0.85, contact_intensity=-0.6)),
    Scenario("800 years, isolated highland", 800, TraitProfile(altitude=0.9, isolation=0.85, contact_intensity=-0.6)),
    Scenario("3000 years, isolated highland", 3000, TraitProfile(altitude=0.9, isolation=0.85, contact_intensity=-0.6)),
)

_STYLE = """
body { font-family: -apple-system, Segoe UI, sans-serif; max-width: 1000px; margin: 2rem auto; padding: 0 1rem;
       background: #1c1d21; color: #e4e4e7; }
h1 { font-size: 1.4rem; }
h2 { font-size: 1.15rem; margin-top: 2.5rem; border-bottom: 1px solid #3a3b42; padding-bottom: 0.3rem; }
.meta { color: #9a9ba3; font-size: 0.85rem; margin-bottom: 0.6rem; }
table { border-collapse: collapse; width: 100%; margin-top: 0.5rem; }
th, td { text-align: left; padding: 0.25rem 0.7rem; border-bottom: 1px solid #2c2d33; font-size: 0.92rem; }
th { color: #9a9ba3; font-weight: 600; }
td.form, td.roman { font-family: "Cambria", "Doulos SIL", serif; }
td.ipa { font-family: "Cambria", "Doulos SIL", serif; color: #c9a0ff; }
tr.changed td.roman, tr.changed td.ipa.evolved { color: #ffb27a; font-weight: 600; }
footer { color: #6a6b73; font-size: 0.8rem; margin-top: 3rem; }
"""


def _build_dutch_base(llm_kind: str) -> Language:
    client = build_llm_client(kind=llm_kind, cache_dir=CACHE_DIR)
    seed_examples = tuple(SeedExample(gloss=gloss, form=form, ipa=ipa) for gloss, form, ipa in DUTCH)
    spec = GenerationSpec(
        prompt="Dutch",
        seed=BASE_SEED,
        traits=TraitProfile(contact_languages=("Dutch",)),
        seed_examples=seed_examples,
    )
    return generate_language("Dutch", spec, client)


def _scenario_table(base: Language, scenario: Scenario) -> str:
    evolved = evolve_language(f"Dutch+{scenario.years}y", base, scenario.years, scenario.traits, EVOLVE_SEED)
    original_by_gloss = {gloss: (form, ipa) for gloss, form, ipa in DUTCH}

    rows = []
    changed_count = 0
    for entry in evolved.lexicon.entries:
        gloss = entry.glosses[0]
        form, original_ipa = original_by_gloss[gloss]
        changed = original_ipa != entry.ipa
        changed_count += changed
        rows.append(
            f"<tr class='{'changed' if changed else ''}'>"
            f"<td>{html.escape(gloss)}</td>"
            f"<td class='form'>{html.escape(form)}</td>"
            f"<td class='ipa'>/{html.escape(original_ipa)}/</td>"
            f"<td class='roman'>{html.escape(entry.romanization)}</td>"
            f"<td class='ipa evolved'>/{html.escape(entry.ipa)}/</td>"
            f"</tr>"
        )

    return (
        f"<h2>{html.escape(scenario.title)}</h2>"
        f"<div class='meta'>{changed_count}/{len(rows)} words changed</div>"
        "<table><tr><th>gloss</th><th>Dutch</th><th>Dutch IPA</th><th>evolved</th><th>evolved IPA</th></tr>"
        + "\n".join(rows)
        + "</table>"
    )


def render(llm_kind: str) -> str:
    base = _build_dutch_base(llm_kind)
    sections = [_scenario_table(base, scenario) for scenario in SCENARIOS]
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"<!doctype html><html><head><meta charset='utf-8'><title>Evolution</title><style>{_STYLE}</style></head>"
        f"<body><h1>Dutch, evolved</h1>"
        f"<div class='meta'>llm={llm_kind} &middot; generated {generated_at} -- re-run "
        f"<code>uv run python experiments/evolution.py</code> after any sound-change-code change. "
        f"Orange rows changed from the original.</div>"
        + "".join(sections)
        + "<footer>Real Dutch core vocabulary (experiments/lexicons.py) evolved via "
        "generation/sound_change.py. Word-level only -- grammar/word order untouched.</footer>"
        + "</body></html>"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llm", default="fake", choices=["fake", "anthropic"])
    args = parser.parse_args()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(render(args.llm), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
