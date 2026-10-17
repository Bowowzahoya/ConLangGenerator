"""Plain-language explanations for the Generate result's own grammar and
trait badges -- shown as hover tooltips in the web UI (requested
directly: "what does altitude do, what is overt copula... include a
description for the key and the value, where a numerical value can be
described according to a range").

Paraphrased from the real source of truth for each field -- ``core.
traits.TraitProfile``'s own per-field docstrings for the numeric trait
dials, ``core.grammar``'s own enums for the grammar fields -- rather than
a second, independently-maintained description that could silently drift
from what a field actually does. Static reference data, served once via
``GET /api/options``'s own ``glossary`` key, the same way
``orthography_styles``/``tts_capabilities`` already are.
"""

from __future__ import annotations

from typing import Literal, TypedDict


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
        "negative": "Little outside contact.",
    },
    "social_hierarchy": {
        "kind": "bipolar",
        "summary": "How hierarchical the speaking culture is.",
        "positive": "A hierarchical culture -- raises the chance the language has honorific pronouns or verb forms at all.",
        "negative": "Today's flat rate, same as 0 -- no extra push toward honorifics.",
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
        "negative": "Today's flat rate, same as 0.",
    },
    "spatial_reference": {
        "kind": "bipolar",
        "summary": "How much precise spatial or locational reference matters to the culture.",
        "positive": "Precise spatial reference matters -- raises the chance the language has dedicated locative/ablative/allative cases.",
        "negative": "Today's flat rate, same as 0.",
    },
    "ritual_register": {
        "kind": "bipolar",
        "summary": "How much the culture uses a distinct, formal register for ritual or religious speech. Recorded but not yet consumed by generation.",
        "positive": "A culture with a strong ritual/formal speech register.",
        "negative": "No particular ritual register.",
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
        "positive": "A culture with strong taboo-avoidance vocabulary.",
        "negative": "No particular taboo avoidance.",
    },
    "terrain_communication_distance": {
        "kind": "bipolar",
        "summary": "How far speakers typically need their voices to carry -- open terrain or mountains versus close quarters.",
        "positive": "Long-distance communication matters -- resists vowel reduction when the language evolves, since loud, long-distance speech needs distinct vowel quality.",
        "negative": "Today's flat rate, same as 0 -- close-range communication is typical.",
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
    "source_languages": "Real language(s) this conlang is meant to evoke or mix, and (see source_language_strictness) how strictly generation sticks to their actual sounds, spelling, and grammar.",
}


def as_dict() -> dict:
    return {"traits": TRAIT_GLOSSARY, "grammar": GRAMMAR_GLOSSARY, "simple": SIMPLE_GLOSSARY}
