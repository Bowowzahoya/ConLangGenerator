"""Asks the LLM for a source language's real word for meanings this project
has no curated vocabulary for (a language beyond the curated set, or a gloss
its file doesn't cover) -- see ``real_words``.

One request per language per ``CHUNK_SIZE`` meanings; the reply is
``NUMBER|spelling|IPA`` lines, parsed leniently (anything that doesn't match,
is out of range, whose spelling isn't Latin-script (a real LLM can
disregard the system prompt's own "romanize it" instruction, e.g. answering
with an actual Chinese character for a gloss in a Chinese-influenced
language), or whose IPA doesn't fully tokenize against the modeled symbol
pool is simply dropped -- that word stays invented). With no usable LLM
(the fake backend's reply never matches) nothing is filled.
"""

from __future__ import annotations

import re
import unicodedata

from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.romanization import STRESS_MARK, WORD_ACCENT_MARK
from conlang_generator.generation import ipa_tokenizer, phoneme_fit
from conlang_generator.llm.base import LLMClient, LLMRequest
from conlang_generator.llm.pricing import DEFAULT_MODEL

CHUNK_SIZE = 100

_SYSTEM_PROMPT = (
    "You give the real, everyday word for each English meaning in a named language, with a simplified IPA "
    "transcription. Use ONLY these IPA symbols (plus the stress mark and nothing else; no length marks or "
    "diacritics beyond those listed as separate symbols): "
    + " ".join(phoneme_fit.ALL_SYMBOLS)
    + ". Approximate any sound the list lacks with the closest listed symbol. Answer with exactly one line per "
    "meaning in the form NUMBER|spelling|IPA (the language's normal spelling in the Latin alphabet, romanized "
    "if it uses another script), no slashes, no other text."
)

_LINE = re.compile(r"^\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*/?([^|/]+?)/?\s*$")
_KNOWN = phoneme_fit.ALL_SYMBOLS + (STRESS_MARK, WORD_ACCENT_MARK)


def _tokenizes_fully(ipa: str) -> bool:
    tokens = ipa_tokenizer.tokenize(ipa, _KNOWN)
    return bool(tokens) and "".join(symbol + decoration for symbol, decoration in tokens) == ipa


def _is_romanized(spelling: str) -> bool:
    """Every letter in ``spelling`` is Latin-script (by Unicode name, e.g.
    "LATIN SMALL LETTER O WITH STROKE" for the real Latin letter "ø",
    still accepted). The system prompt already asks for a Latin/romanized
    spelling; this catches a real LLM disregarding that instruction (e.g.
    answering with an actual Chinese character for a gloss in a language
    it knows has Chinese influence) before it reaches the lexicon as a
    word's own spelling."""
    return all("LATIN" in unicodedata.name(ch, "") for ch in spelling if ch.isalpha())


def fetch_real_words(
    requests: list[tuple[str, str, PartOfSpeech]], llm_client: LLMClient, model: str = DEFAULT_MODEL,
) -> dict[tuple[str, str], tuple[str, str]]:
    """``{(language, gloss): (spelling, ipa)}`` for whatever the LLM
    answered validly, from ``requests`` of ``(language, gloss, pos)``."""
    by_language: dict[str, list[tuple[str, PartOfSpeech]]] = {}
    for language, gloss, pos in requests:
        by_language.setdefault(language, []).append((gloss, pos))

    found: dict[tuple[str, str], tuple[str, str]] = {}
    for language, items in by_language.items():
        for start in range(0, len(items), CHUNK_SIZE):
            chunk = items[start : start + CHUNK_SIZE]
            listing = "\n".join(f"{i}. {gloss} ({pos.value})" for i, (gloss, pos) in enumerate(chunk, start=1))
            request = LLMRequest(
                system=_SYSTEM_PROMPT,
                prompt=f"Language: {language}. Give the real {language} word for each meaning:\n{listing}",
                model=model,
                max_tokens=max(512, 40 * len(chunk)),
                purpose="lexicon.real_words",
                metadata={"fake_strategy": "none"},
            )
            for line in llm_client.complete(request).text.splitlines():
                match = _LINE.match(line)
                if match is None:
                    continue
                number, spelling, ipa = int(match.group(1)), match.group(2).strip(), match.group(3).strip()
                if 1 <= number <= len(chunk) and spelling and _is_romanized(spelling) and _tokenizes_fully(ipa):
                    found[(language, chunk[number - 1][0])] = (spelling, ipa)
    return found
