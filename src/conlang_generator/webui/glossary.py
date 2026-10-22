"""Plain-language explanations for the Generate tab's own grammar/trait
badges and Advanced options -- shown in a click-to-open popover in the
web UI (requested directly: "what does altitude do, what is overt
copula... include a description for the key and the value, where a
numerical value can be described according to a range"; then "little i
info buttons... to describe what the entry does and what all the
options mean").

Paraphrased from the real source of truth for each field -- ``core.
traits.TraitProfile``'s own per-field docstrings for the numeric trait
dials, ``core.grammar``'s own enums for the grammar fields, ``core.spec.
GenerationSpec``'s own docstrings for the Advanced options, and
``generation.romanization_gen.ORTHOGRAPHY_STYLE_DESCRIPTIONS`` (read
directly, not copied, so it can never drift) for the 12 named
orthography presets -- rather than a second, independently-maintained
description that could silently drift from what a field actually does.
Static reference data, served once via ``GET /api/options``'s own
``glossary`` key, the same way ``orthography_styles``/
``tts_capabilities`` already are.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from conlang_generator.generation.romanization_gen import ORTHOGRAPHY_STYLE_DESCRIPTIONS


class BipolarTraitGloss(TypedDict):
    kind: Literal["bipolar"]
    summary: str
    positive: str
    negative: str


class UnipolarDialGloss(TypedDict):
    kind: Literal["unipolar"]
    summary: str
    low: str
    high: str


# --- the 15 GRADED_TRAIT_FIELDS (core.traits.TraitProfile), bipolar
# [-1.0, 1.0]: a positive value is evidence *for* the named pole, a
# negative value is evidence for its opposite -- see that module's own
# docstring. ---
TRAIT_GLOSSARY: dict[str, BipolarTraitGloss] = {
    "isolation": {
        "kind": "bipolar",
        "summary": "How geographically or socially isolated the speech community is.",
        "positive": "Geographically or socially isolated -- nudges toward uvular consonants, ergative alignment, and more polysynthetic/agglutinative morphology.",
        "negative": "Well-connected or cosmopolitan -- suppresses those same nudges.",
    },
    "altitude": {
        "kind": "bipolar",
        "summary": "How high up the language's homeland terrain is.",
        "positive": "High-altitude terrain -- nudges toward ejective consonants (a real cross-linguistic pattern, Everett 2013).",
        "negative": "Lowland or coastal terrain -- suppresses ejectives.",
    },
    "community_scale": {
        "kind": "bipolar",
        "summary": "How small and tight-knit the speech community is.",
        "positive": "A small, tight-knit community -- nudges morphology toward polysynthetic/agglutinative.",
        "negative": "A large, diffuse community -- suppresses that nudge.",
    },
    "contact_intensity": {
        "kind": "bipolar",
        "summary": "How much contact, trade, or creolization history the language has had with others.",
        "positive": "Heavy contact/trade/creolization history -- nudges morphology toward isolating/analytic, the opposite pull from isolation/community_scale.",
        "negative": "Little outside contact -- no nudge of its own toward isolating/analytic morphology (isolation/community_scale may still independently nudge the other way).",
    },
    "social_hierarchy": {
        "kind": "bipolar",
        "summary": "How hierarchical the speaking culture is.",
        "positive": "A hierarchical culture -- raises the chance the language has honorific pronouns or verb forms at all.",
        "negative": "A flat, egalitarian culture. This trait is one-directional: only a positive reading changes the odds of honorifics; a negative reading has no suppressing effect of its own and behaves exactly like 0.",
    },
    "orality_literacy": {
        "kind": "bipolar",
        "summary": "How much the culture relies on writing versus a purely spoken tradition. Only affects evolution's orthography-reform rate so far.",
        "positive": "A literate culture with an established writing tradition -- a written norm anchors both spelling and pronunciation against drift when the language evolves.",
        "negative": "A purely, or mostly, oral culture -- spelling and pronunciation drift more freely over time.",
    },
    "evidentiality_culture": {
        "kind": "bipolar",
        "summary": "How much the culture grammatically marks *how* a speaker knows something (hearsay vs. direct witness, and so on).",
        "positive": "A culture that marks evidentiality richly -- lowers the chance the language ends up with no evidentiality system at all.",
        "negative": "A culture that doesn't grammatically mark evidence sources. This trait is one-directional: only a positive reading changes the odds of an evidentiality system; a negative reading has no suppressing effect of its own and behaves exactly like 0.",
    },
    "spatial_reference": {
        "kind": "bipolar",
        "summary": "How much precise spatial or locational reference matters to the culture.",
        "positive": "Precise spatial reference matters -- raises the chance the language has dedicated locative/ablative/allative cases.",
        "negative": "Precise spatial reference doesn't especially matter. This trait is one-directional: only a positive reading changes the odds of dedicated spatial cases; a negative reading has no suppressing effect of its own and behaves exactly like 0.",
    },
    "ritual_register": {
        "kind": "bipolar",
        "summary": "How much the culture uses a distinct, formal register for ritual or religious speech. Recorded but not yet consumed by generation.",
        "positive": "A culture with a strong ritual/formal speech register. Recorded for future use -- neither pole affects the generated language yet.",
        "negative": "No particular ritual register. Recorded for future use -- neither pole affects the generated language yet.",
    },
    "aesthetic_harshness": {
        "kind": "bipolar",
        "summary": "How harsh and guttural, versus soft and melodic, the language is meant to sound.",
        "positive": "Harsh, guttural-sounding -- re-weights consonant selection toward harsher sounds.",
        "negative": "Soft, melodic-sounding -- re-weights consonant selection toward softer sounds.",
    },
    "tonal_friendliness": {
        "kind": "bipolar",
        "summary": "How much the culture favors lexical tone -- pitch that changes a word's meaning.",
        "positive": "A cultural or practical affinity for tone -- nudges the language toward being tonal.",
        "negative": "Evidence the language explicitly is not tonal -- suppresses it below the usual base rate.",
    },
    "taboo_register": {
        "kind": "bipolar",
        "summary": "How much the culture avoids or replaces taboo vocabulary with euphemisms. Recorded but not yet consumed by generation.",
        "positive": "A culture with strong taboo-avoidance vocabulary. Recorded for future use -- neither pole affects the generated language yet.",
        "negative": "No particular taboo avoidance. Recorded for future use -- neither pole affects the generated language yet.",
    },
    "terrain_communication_distance": {
        "kind": "bipolar",
        "summary": "How far speakers typically need their voices to carry -- open terrain or mountains versus close quarters.",
        "positive": "Long-distance communication matters -- resists vowel reduction when the language evolves, since loud, long-distance speech needs distinct vowel quality.",
        "negative": "Close-range communication is typical. This trait is one-directional: only a positive reading resists vowel reduction over time; a negative reading has no extra effect of its own and behaves exactly like 0 (ordinary vowel reduction still applies as the language evolves).",
    },
    "phonotactic_restrictiveness": {
        "kind": "bipolar",
        "summary": "How tight and rigid the allowed syllable shapes are. Only matters when no source language is active.",
        "positive": "A tight, rigid syllable shape (Japanese/Mandarin-like) -- only a small, fixed set of sound combinations actually occur.",
        "negative": "Loose, permissive syllable shapes (like most Indo-European languages) -- only a handful of combinations are disallowed.",
    },
    "tone_sandhi": {
        "kind": "bipolar",
        "summary": "How much neighboring tones change each other in connected speech. Only matters for tonal languages.",
        "positive": "Pervasive tone sandhi, like Mandarin's third-tone rule -- raises the chance the language keeps or invents sandhi rules.",
        "negative": "Evidence the language has no tone sandhi.",
    },
    "fricative_density": {
        "kind": "bipolar",
        "summary": "How many hissing/fricative sounds (s, f, sh, and similar) the language's consonant inventory tends to have.",
        "positive": "Many fricatives/sibilants -- a hissy-sounding consonant inventory.",
        "negative": "Very few fricatives, or none at all -- several real Australian Aboriginal languages genuinely have no fricatives.",
    },
    "nasality": {
        "kind": "bipolar",
        "summary": "How much the language favors nasalized vowels (a vowel pronounced partly through the nose).",
        "positive": "Heavy vowel nasalization, French/Portuguese-like.",
        "negative": "No nasalized vowels at all.",
    },
    "vowel_richness": {
        "kind": "bipolar",
        "summary": "How large and elaborate the vowel inventory tends to be.",
        "positive": "A large, elaborate vowel inventory, Danish/English-like.",
        "negative": "A small, minimal vowel inventory, Arabic/Quechua-like.",
    },
    "consonant_richness": {
        "kind": "bipolar",
        "summary": "How large and elaborate the consonant inventory tends to be.",
        "positive": "A large, elaborate consonant inventory.",
        "negative": "A small, minimal consonant inventory.",
    },
    "vowel_length_affinity": {
        "kind": "bipolar",
        "summary": "How likely the language is to distinguish short and long vowels as separate sounds.",
        "positive": "Phonemic vowel-length contrasts -- a short and long version of a vowel count as different sounds.",
        "negative": "No length distinction at all.",
    },
    "word_length_preference": {
        "kind": "bipolar",
        "summary": "Whether this culture's words tend to be long and elaborate, or short and economical, independent of a source language's own real average.",
        "positive": "Long, elaborate words.",
        "negative": "Short, economical words.",
    },
    "vowel_reduction_affinity": {
        "kind": "bipolar",
        "summary": "Whether an unstressed vowel keeps its full quality or weakens toward a central sound -- the real difference behind a \"flowing\"/\"musical\" vs. \"clipped\"/\"staccato\" speech impression. Only matters when no source language already settles this.",
        "positive": "Stress-timed rhythm -- unstressed vowels reduce toward a central quality, English/German/Portuguese-like.",
        "negative": "Syllable-timed rhythm -- every vowel keeps its full quality regardless of stress, French/Spanish/Turkish/Finnish-like.",
    },
    "compound_likelihood": {
        "kind": "bipolar",
        "summary": "Whether a new word tends to be built from existing words (compounding/derivation) or coined as a fresh, unrelated root -- composed with a part-of-speech bias (nouns compound far more than verbs) and a hard suppression for basic/frequent vocabulary.",
        "positive": "Favors building new words from existing ones -- Mandarin's own heavy compounding (电脑 \"electric-brain\" = computer).",
        "negative": "Favors a fresh, unrelated root even where words could be recomposed -- English-style (Monday, understand rarely get re-analyzed).",
    },
    # --- the two strictness dials: unipolar [0.0, 1.0], not bipolar --
    # 0.0 is today's existing soft, non-exclusive influence, 1.0 hard-
    # restricts to only the named source language(s)' own real values. ---
    "source_language_strictness": {
        "kind": "unipolar",
        "summary": "How closely this language's sounds, spelling, and grammar stick to its named source language(s), versus just being loosely inspired by them.",
        "low": "Soft, non-exclusive influence -- the source language(s) bias generation without restricting it.",
        "high": "Hard-restricted -- every sound, spelling, and grammar choice is drawn only from the named source language(s)' own real values.",
    },
    "source_word_strictness": {
        "kind": "unipolar",
        "summary": "How many of this language's words are real words (or close variants) from its source language(s), rather than entirely invented.",
        "low": "No words are based on the real source language -- fully invented vocabulary.",
        "high": "Every word is an exact copy of the real source-language word.",
    },
}


# --- the Evolve tab's own 6 trait-override rows (core.traits.
# EVOLUTION_TRAIT_FIELDS) -- unlike TRAIT_GLOSSARY above, every
# description here is written purely in terms of the effect during
# *evolution*, not fresh generation (several of these traits also affect
# generation, described above instead; a couple only ever affect
# evolution, so the two descriptions happen to read similarly). Direct
# user request, after noticing the Evolve tab showed the same 15 rows as
# Generate and asking whether all of them really apply to both -- they
# don't (see EVOLUTION_TRAIT_FIELDS's own docstring for the investigation). ---
EVOLUTION_TRAIT_GLOSSARY: dict[str, BipolarTraitGloss] = {
    "altitude": {
        "kind": "bipolar",
        "summary": "How high up the language's homeland terrain is.",
        "positive": "High-altitude terrain -- strengthens the drift toward ejective consonants as the language evolves, the same real high-altitude/ejective link (Everett 2013) generation itself already leans on, now acting gradually over time instead of as a one-time roll.",
        "negative": "Lowland or coastal terrain -- weakens that same ejective drift as the language evolves.",
    },
    "aesthetic_harshness": {
        "kind": "bipolar",
        "summary": "How harsh and guttural, versus soft and melodic, the language is meant to sound.",
        "positive": "A harsh, guttural aesthetic -- strengthens ejective-consonant drift as the language evolves, the same direction a high `altitude` reading pushes.",
        "negative": "A soft, melodic aesthetic -- weakens that same ejective drift as the language evolves.",
    },
    "contact_intensity": {
        "kind": "bipolar",
        "summary": "How much contact, trade, or creolization history the language has had with others.",
        "positive": "Heavy contact/trade history -- speeds up consonant-cluster simplification, the rate words get replaced wholesale, and orthography drift/reform, and raises the chance a tonal language loses its tone system under sustained contact (the real, documented path Swahili took).",
        "negative": "Little outside contact -- none of those changes are sped up; the language drifts at whatever its own internal rate already is.",
    },
    "orality_literacy": {
        "kind": "bipolar",
        "summary": "How much the culture relies on writing versus a purely spoken tradition.",
        "positive": "A literate culture with an established writing tradition -- anchors both pronunciation and spelling against drift as the language evolves, and lowers the rate of deliberate orthography reform.",
        "negative": "A purely, or mostly, oral culture -- pronunciation and spelling drift more freely as the language evolves, with no literate anchor holding either in place.",
    },
    "tonal_friendliness": {
        "kind": "bipolar",
        "summary": "How much the culture favors lexical tone -- pitch that changes a word's meaning.",
        "positive": "A cultural affinity for tone -- resists vowel reduction as the language evolves, since a tonal language needs distinct vowel quality to keep its pitch contrasts legible. Doesn't on its own make a non-tonal language gain tone, or a tonal one lose it -- that's `contact_intensity` (loss) and a purely structural, coda-driven mechanism (gain); see `generation.sound_change._evolve_tone_system`.",
        "negative": "Evidence against a tonal affinity -- no extra resistance to vowel reduction of its own.",
    },
    "terrain_communication_distance": {
        "kind": "bipolar",
        "summary": "How far speakers typically need their voices to carry -- open terrain or mountains versus close quarters.",
        "positive": "Long-distance communication matters -- resists vowel reduction as the language evolves, since loud, long-distance speech needs distinct vowel quality.",
        "negative": "Close-range communication is typical -- no extra resistance of its own; ordinary vowel reduction still applies as the language evolves.",
    },
}


# --- the 17 ScriptTraits dials (core.script.ScriptTraits), bipolar
# [-1.0, 1.0] -- same shape as TRAIT_GLOSSARY, paraphrased directly from
# that module's own per-field docstrings. Governs an invented script's
# visual style, not any worldbuilding/generation choice -- shown next to
# the Generate tab's own "+ script trait override" rows (and wherever
# else a script-trait value needs explaining), direct user request
# ("Script, grammar traits in Generate should have a description of
# what it means when selecting"). ---
SCRIPT_TRAIT_GLOSSARY: dict[str, BipolarTraitGloss | UnipolarDialGloss] = {
    "angularity": {
        "kind": "bipolar",
        "summary": "Not yet active. Reserved for a future corner-smoothing pass (rounding the joint between two connected strokes); every glyph is drawn from straight lines only today, so this dial currently has no visible effect.",
        "positive": "Sharp -- straight lines and pointed corners (today's default, regardless of this dial's value).",
        "negative": "Smooth -- would round the corners between strokes once this is implemented.",
    },
    "stroke_contrast": {
        "kind": "unipolar",
        "summary": "Whether a stroke's own width varies along its length. No meaningful opposite pole below 0, so this dial only runs 0..1.",
        "low": "Monoline -- every stroke keeps a uniform width throughout.",
        "high": "Calligraphic -- thick/thin width variation within a single stroke.",
    },
    "weight": {
        "kind": "bipolar",
        "summary": "How heavy the strokes themselves look.",
        "positive": "Bold -- heavy, thick strokes.",
        "negative": "Thin -- light, fine strokes.",
    },
    "complexity": {
        "kind": "bipolar",
        "summary": "How many strokes make up a typical glyph.",
        "positive": "Ornate -- many strokes per glyph.",
        "negative": "Minimal -- just 1-2 strokes per glyph.",
    },
    "proportion": {
        "kind": "bipolar",
        "summary": "A glyph's own width-to-height ratio.",
        "positive": "Wide, squat glyphs.",
        "negative": "Tall, narrow glyphs.",
    },
    "slant": {
        "kind": "bipolar",
        "summary": "Whether glyphs lean, italic-style.",
        "positive": "Slanted -- an italic-like shear.",
        "negative": "Upright, no shear.",
    },
    "regularity": {
        "kind": "unipolar",
        "summary": "How much organic jitter is added to each stroke's own endpoints. No meaningful opposite pole below 0, so this dial only runs 0..1.",
        "low": "Geometric -- ruler-and-compass precision, no jitter.",
        "high": "Organic -- a rustic, hand-drawn feel, maximum jitter.",
    },
    "diacritic_density": {
        "kind": "bipolar",
        "summary": "How many small diacritic marks attach to a letter (0-4), not how dotty the letter itself looks (see dot_prevalence for that) or where each one sits (see ornateness for that).",
        "positive": "Many attached diacritic marks -- up to 4 at once.",
        "negative": "Few or no attached diacritic marks.",
    },
    "serif": {
        "kind": "unipolar",
        "summary": "How often, and how pronounced, a script-wide serif treatment is applied to stroke ends -- a single consistent rule (which stroke directions, which end(s), a shape, a thickness) rolled once for the whole script, like a real typeface's own serif style. No meaningful opposite pole below 0 (0 = no serifs at all), so this dial only runs 0..1. Distinct from terminal_style below: this is pervasive and visually consistent everywhere it applies, not an occasional per-letter flourish.",
        "low": "No serifs, or very few, very plain ones.",
        "high": "A strong, consistent serif treatment across the whole script.",
    },
    "terminal_style": {
        "kind": "bipolar",
        "summary": "How often a letter gets its own occasional terminal ornament -- a hook, swirl, foot, or extended stroke at one stroke-end, usually just one letter at a time, not a pervasive style the way serif above is.",
        "positive": "Many letters get a terminal ornament, occasionally two.",
        "negative": "Terminal ornaments are rare or absent.",
    },
    "stroke_continuity": {
        "kind": "bipolar",
        "summary": "Whether one stroke starts where the last one ended, or lifts and restarts elsewhere.",
        "positive": "Strokes chain continuously, start-to-end, rarely lifting.",
        "negative": "Strokes often lift and restart fresh, as in multi-component letters like F or H.",
    },
    "dot_prevalence": {
        "kind": "bipolar",
        "summary": "Whether a stroke is often replaced by a bare dot instead of a line. A diacritic's own strokes get a further boost on top of this same scale, so a diacritic is more likely to include a dot than the main letter is.",
        "positive": "Dots are common (up to about a third of strokes, more within a diacritic).",
        "negative": "Dots are rare -- almost every stroke is a real line.",
    },
    "ornateness": {
        "kind": "unipolar",
        "summary": "How elaborate a script's own decorative details are, across three things at once: a dot's own render style, a diacritic's own richness and placement variety, and which of terminal_style's own ornament shapes gets favored. No meaningful opposite pole below 0, so this dial only runs 0..1.",
        "low": "One plain dot style reused everywhere, diacritics sit in one fixed spot with fewer strokes, and any terminal ornament is a plain foot.",
        "high": "Dot style varies letter to letter (and leans slightly more circular), diacritics get richer and nest in more varied spots (including inside the letter itself), and terminal ornaments lean toward the fancier presets -- twirls, double hooks.",
    },
}

# --- grammar badges: categorical, not graded -- a general description of
# the field plus a specific explanation of each value it can actually
# take. Booleans are keyed by the lowercase string JS's own template
# literal produces ("true"/"false"), matching the badge text as rendered. ---
GRAMMAR_GLOSSARY: dict[str, dict] = {
    "word_order": {
        "summary": "The basic order of subject, object, and verb in a simple sentence.",
        "values": {
            "SOV": "Subject-Object-Verb, e.g. \"I him see.\" The most common word order cross-linguistically (Japanese, Turkish, Hindi, Latin).",
            "SVO": "Subject-Verb-Object, e.g. \"I see him.\" (English, Mandarin, French.)",
            "VSO": "Verb-Subject-Object, e.g. \"See I him.\" (Welsh, Irish, Classical Arabic.)",
            "VOS": "Verb-Object-Subject, e.g. \"See him I.\" (Malagasy, some Mayan languages.)",
            "OVS": "Object-Verb-Subject, e.g. \"Him see I.\" Rare (Hixkaryana).",
            "OSV": "Object-Subject-Verb, e.g. \"Him I see.\" The rarest order, found in a handful of Amazonian languages.",
        },
    },
    "alignment": {
        "summary": "How the grammar groups the subject of an intransitive verb with either the subject or the object of a transitive one.",
        "values": {
            "nominative_accusative": "The subject of \"she sleeps\" is treated the same as the subject of \"she sees him\" -- the more common pattern worldwide (most of Europe and Asia).",
            "ergative_absolutive": "The subject of \"she sleeps\" is treated the same as the *object* of \"she sees him\", not its subject -- found in Basque and many Mayan and Australian Aboriginal languages.",
        },
    },
    "morphological_type": {
        "summary": "How the language builds words out of smaller meaningful pieces.",
        "values": {
            "isolating": "Few or no affixes -- each word is usually one unchanging piece, and grammatical meaning comes from word order and separate particles (Mandarin, Vietnamese).",
            "agglutinative": "Words are built by stringing together affixes, each with one clear meaning, glued on in a predictable order (Turkish, Finnish, Swahili).",
            "fusional": "Affixes often pack several grammatical meanings into one piece (e.g. a single ending marking both case and number), and sound change can blur the boundaries between them (Latin, Russian, German).",
            "polysynthetic": "A single word can pack in what would be a whole sentence in English -- verb, subject, object and more all fused together (Mohawk, Inuktitut).",
        },
    },
    "has_articles": {
        "summary": "Whether the language has dedicated words for \"a/an\" and \"the\".",
        "values": {
            "true": "Has articles.",
            "false": "No articles -- definiteness, if marked at all, is shown some other way (word order, a demonstrative, or just left to context, like Russian or Japanese).",
        },
    },
    "has_overt_copula": {
        "summary": "Whether a sentence like \"she is tall\" needs an explicit \"to be\" word, or whether the adjective alone can stand as the whole predicate.",
        "values": {
            "true": "Needs an explicit \"to be\" word, the same as English \"she IS tall\".",
            "false": "No explicit \"to be\" needed for this kind of sentence -- \"she tall\" is a complete sentence on its own (Russian in the present tense, Arabic, many other languages).",
        },
    },
    "adjective_after_noun": {
        "summary": "Whether a descriptive adjective comes before or after the noun it modifies.",
        "values": {
            "true": "After the noun, like French \"maison bleue\" (house blue).",
            "false": "Before the noun, like English \"blue house\".",
        },
    },
    "tonal": {
        "summary": "Whether pitch (rising, falling, and so on) on a syllable changes a word's meaning, the way it does in Mandarin or Vietnamese.",
        "values": {
            "true": "Tonal -- pitch distinguishes words.",
            "false": "Not tonal -- pitch doesn't change word meaning (like English or Spanish, though it can still carry sentence-level emphasis).",
        },
    },
    "word_selection": {
        "summary": "How this language's core vocabulary was chosen during generation.",
        "values": {
            "algorithmic": "Chosen by a free, deterministic algorithm -- no LLM call involved.",
            "llm": "Chosen with help from one batched LLM call, picking among algorithmically-generated candidates.",
        },
    },
    "word_formation": {
        "summary": "How a word flagged to be built from existing words (compound/derivation/ablaut) decides what it's built from.",
        "values": {
            "algorithmic": "Looked up in a curated list of known compounds/derivations -- no LLM call involved.",
            "llm": "Asked of the configured LLM, reaching any gloss, not just a pre-tabulated one.",
        },
    },
    "foreign_names": {
        "summary": "How the language handles foreign or borrowed proper names.",
        "values": {
            "keep": "Kept as written in the original language, unchanged (Dutch-style).",
            "adapt": "Re-fit to the language's own sounds and spelling conventions (Chinese-style).",
        },
    },
}

# --- the handful of remaining badges that are either a free-form list
# (cases/tenses -- the member names are already standard linguistic
# terms, not a fixed enum this module could usefully expand on) or just
# don't need more than one sentence. One plain string each, no per-value
# breakdown. ---
SIMPLE_GLOSSARY: dict[str, str] = {
    "evolved_years": "How many years of sound change have been applied to this language since it was first generated.",
    "real_words": "How many of this language's words are based on (not necessarily identical to) a real word from one of its source languages, rather than being entirely invented.",
    "cases": "The grammatical cases this language's nouns and pronouns mark (such as accusative, genitive, or ablative) to show their role in a sentence.",
    "tenses": "The grammatical tenses this language's verbs mark to show when an action happened.",
    "orthography_category": "The general style of this language's writing system -- how its sounds map to letters.",
    "own_script": "This language also has its own invented writing system -- a procedurally generated glyph for each sound, downloadable as a real font. Click \"Show lexicon in its own script\" below to see it, or download the font to use it elsewhere.",
    "source_languages": "Real language(s) this conlang is meant to evoke or mix, and (see source_language_strictness) how strictly generation sticks to their actual sounds, spelling, and grammar.",
}

# --- the Generate tab's own "Advanced options" panel (requested
# directly, a follow-up to the badge tooltips above: "little i info
# buttons... to describe what the entry does and what all the options
# mean"). Most advanced fields already carry their own explanation
# inline in the form's own <label> text (word/sound strictness, trait
# overrides, seed examples, years of evolution) and don't need a second
# one here -- this covers only the fields that don't: the five
# checkboxes, the foreign-names default, and the seven orthography-style
# selects. Keyed by core.spec.GenerationSpec's own field name where one
# exists (the checkboxes), or a short descriptive name otherwise (the
# selects) -- a separate top-level section from GRAMMAR_GLOSSARY, not
# merged into it, since e.g. "foreign_names" means something different
# here (a three-way forward-looking choice including "auto") than it
# does as a grammar badge (the two-way resolved outcome). Unlike the
# grammar glossary, an advanced-option select's own "values" are meant
# to all be shown at once as a legend -- the user hasn't chosen yet, so
# there's no one "current reading" to single out the way a grammar
# badge already has. ---
ADVANCED_OPTIONS_GLOSSARY: dict[str, dict] = {
    "force_tonal": {
        "summary": "Guarantees the language is tonal outright, regardless of what the prompt says or how likely the classifier judges it to be.",
    },
    "source_languages": {
        "summary": "Real language(s) this conlang is meant to evoke or mix -- biases phoneme inventory, syllable structure, and (see word_strictness/strictness below) how many of its words toward their actual, real-world sounds and spelling. An optional per-language weight controls each one's share when more than one is given; omitted weights split evenly.",
    },
    "evolve_years": {
        "summary": "How many years of sound change to apply after the language is first generated -- a separate step layered on top of generation, not a generation-time setting itself. Independent of word_strictness/strictness: a real-word-sourced language can be evolved forward in time just like an entirely invented one; the two aren't alternatives to each other.",
        "values": {
            "0": "No evolution applied -- the language stays exactly as first generated.",
            "(blank)": "Inferred from the prompt's own wording (e.g. \"evolved forward 200 years\"); if the prompt implies nothing, defaults to 0.",
        },
    },
    "word_strictness": {
        "summary": "How many of this language's words are drawn from a source language's own real words, and how closely they're kept to the original, versus coined fresh. Only has an effect when at least one source language is set.",
        "values": {
            "0.0": "No real words at all -- every word is coined fresh, only the sound palette is biased by the source language.",
            "1.0": "Exact copies of real source-language words wherever one exists for a given gloss.",
            "(blank)": "Inferred from the prompt's own wording.",
        },
    },
    "strictness": {
        "summary": "How tightly the allowed sound inventory and syllable shapes follow a source language's own real phonology, versus drifting from it. Only has an effect when at least one source language is set -- separate from word_strictness, which is about *words*, not the sound system itself.",
        "values": {
            "0.0": "The source language only loosely inspires the palette; most of its own real constraints are ignored.",
            "1.0": "Sticks closely to the source language's own real phoneme inventory and syllable structure.",
            "(blank)": "Inferred from the prompt's own wording.",
        },
    },
    "allow_all_caps": {
        "summary": "Opt-in permission for a whole word class (e.g. every noun) to be rendered in full capitals in this language's own spelling convention. Off by default, since no real language actually does this -- checking this only makes it *possible*, not guaranteed.",
    },
    "own_script": {
        "summary": "Whether this language gets its own invented writing system -- a set of generated glyphs, downloadable as a real font. A heavier, optional artifact, off by default.",
        "values": {
            "auto": "Inferred: \"yes\" only if the prompt explicitly asks for an invented script/alphabet/runes; otherwise \"no\" -- unlike most other \"auto\" options here, an absence of any signal means off, not a 50/50 guess.",
            "yes": "Always generate one.",
            "no": "Never generate one, even if the prompt asks for it.",
        },
    },
    "foreign_names": {
        "summary": "How this language should handle foreign or borrowed proper names.",
        "values": {
            "auto": "Inferred: an explicit request in the prompt wins if there is one; otherwise the weighted vote of any matched source language(s)' own real convention; otherwise \"keep as written\".",
            "keep": "Kept as written in the original language, unchanged (Dutch-style).",
            "adapt": "Re-fit to the language's own sounds and spelling conventions (Chinese-style).",
        },
    },
    "orthography_style": {
        "summary": "Forces one of 12 named, real-world-inspired orthography presets outright, instead of letting the normal roll/bias (prompt wording, a matched source language's own convention) decide. Each preset is a bundle of several independent spelling conventions (how an exotic sound is spelled, whether/how vowel length and tone are marked, ...) chosen together because real orthographies of that broad family tend to combine them.",
        "values": dict(ORTHOGRAPHY_STYLE_DESCRIPTIONS),
    },
    "exotic_symbol_style": {
        "summary": "Forces how a phoneme with no obvious single Latin letter gets spelled, absent a more specific rule.",
        "values": {
            "monoletter": "One ASCII letter per sound, even at the cost of merging some distinctions -- a \"shallow\"/phonemic system in the spirit of Finnish, Swahili, or informal Georgian transliteration.",
            "digraph": "A two-letter ASCII sequence, e.g. \"ʃ\" -> \"sh\".",
            "diacritic": "A single Latin-Extended letter, e.g. \"ʃ\" -> \"š\".",
        },
    },
    "vowel_length_style": {
        "summary": "Forces how a phonemically long vowel is distinguished in spelling from its short counterpart.",
        "values": {
            "none": "Length isn't marked in the spelling at all.",
            "doubling": "The letter is doubled, e.g. \"a\"/\"aa\" -- Dutch, Finnish, Estonian.",
            "macron": "A macron over the letter, e.g. \"ā\" -- the scholarly convention shared by Latin, Hawaiian, and Japanese romaji transliteration.",
            "colon": "An ASCII colon after the letter, e.g. \"a:\" -- an informal but attested transliteration stand-in for IPA's own length mark.",
            "silent_e": "A mute \"e\" appended after the syllable's own coda, the way English spelling distinguishes \"mat\" from \"mate\".",
        },
    },
    "tone_style": {
        "summary": "Forces how a tone mark on a vowel surfaces in the Latin spelling.",
        "values": {
            "vowel_diacritic": "The mark stays inline on the vowel -- the default.",
            "postposed_digit": "Wade-Giles/numbered-Pinyin style: a digit after the syllable.",
            "postposed_letter": "Zhuang-style: a letter after the syllable.",
            "unmarked": "Tone simply isn't written.",
        },
    },
    "syllable_boundary_marker": {
        "summary": "Forces whether/how two adjacent syllables get a separator when the first ends in a vowel and the second begins with one -- without one, the two vowel letters can read as a single ambiguous sequence (Pinyin's own real rule: \"Xi'an\" vs. \"Xian\").",
        "values": {
            "none": "No separator is ever inserted.",
            "apostrophe": "An apostrophe, Pinyin-style (\"Xi'an\").",
            "hyphen": "A hyphen.",
            "diaeresis": "A diaeresis/tréma on the second vowel's own letter instead of an inserted character, French-style (Noël, naïve).",
        },
    },
    "short_vowel_doubling": {
        "summary": "Whether a short vowel makes the following onset consonant double in spelling, Dutch-style (\"zitten\" vs. \"zaten\") -- independent of how long vowels themselves are marked.",
    },
    "consonant_gemination": {
        "summary": "Whether a phonemically long/geminate consonant doubles its own letter in spelling (Finnish \"kukka\" vs. \"kuka\"), independent of any neighboring vowel.",
    },
}


def as_dict() -> dict:
    return {
        "traits": TRAIT_GLOSSARY,
        "evolution_traits": EVOLUTION_TRAIT_GLOSSARY,
        "script_traits": SCRIPT_TRAIT_GLOSSARY,
        "grammar": GRAMMAR_GLOSSARY,
        "simple": SIMPLE_GLOSSARY,
        "advanced_options": ADVANCED_OPTIONS_GLOSSARY,
    }
