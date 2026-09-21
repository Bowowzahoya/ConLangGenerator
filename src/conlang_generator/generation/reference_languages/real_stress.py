"""Word stress in the curated real lexicons.

A lexicon IPA string carries its stress as the standard mark ``ˈ`` (U+02C8)
in front of the stressed syllable's onset -- the same convention
``word_builder.build_word`` gives generated words -- and none at all for a
monosyllable. This module reads and writes that mark:

* ``syllable_starts`` / ``syllable_count`` / ``stressed_syllable`` read it;
* ``with_stress`` puts it on a chosen syllable;
* ``default_stress_index`` is what a language's own ``stress_pattern`` predicts
  (the fixed-stress languages, Spanish/Portuguese by rule, Latin by weight);
* ``coverage`` reports how many polysyllabic words of a lexicon carry a mark.

Syllables are split with the profile's own phonotactics (maximal onset: the
longest legal onset of the consonants between two vowels), so the mark lands
where a speaker would put a syllable break (``ɪkˈspɹɛs``, not ``ɪksˈpɹɛs``).
"""

from __future__ import annotations

from conlang_generator.core.phonology import TONE_DIACRITICS
from conlang_generator.core.romanization import STRESS_MARK, WORD_ACCENT_MARK, predict_default_stress
from conlang_generator.generation import ipa_tokenizer
from conlang_generator.generation.reference_languages import REFERENCE_LANGUAGES, ReferenceLanguageProfile
from conlang_generator.generation.reference_languages import lexicon_audit
from conlang_generator.generation.reference_languages.real_lexicon import real_words

_PITCH_MARKS = frozenset(TONE_DIACRITICS.values())
_DIPHTHONGS = frozenset({"ai", "au", "ei", "ɔi", "œy", "ou", "oi", "eu"})
_HIGH_OFFGLIDES = frozenset({"i", "u", "ɪ", "ʊ", "y"})
_FINAL_GLIDE_LANGUAGES = frozenset({"Portuguese"})


def _profile(name: str) -> ReferenceLanguageProfile:
    return next(p for p in REFERENCE_LANGUAGES if p.name == name)


def tokens(ipa: str, name: str) -> list[tuple[str, str]]:
    """``(symbol, decorations)`` pairs of ``ipa`` with the stress mark removed."""
    return [
        (symbol, deco)
        for symbol, deco in ipa_tokenizer.tokenize(ipa, lexicon_audit._known_symbols(name))
        if symbol not in (STRESS_MARK, WORD_ACCENT_MARK)
    ]


def _is_vowel(symbol: str) -> bool:
    return symbol in lexicon_audit._VOWEL_SYMBOLS


def _nuclei(toks: list[tuple[str, str]], final_glide: bool = False) -> list[int]:
    """Token index of each syllable's (first) vowel. Two vowels in a row make one
    syllable when the second is a high off-glide after a non-high vowel (``æ`` +
    ``i``, ``a`` + ``u``: a falling diphthong); otherwise they are a hiatus."""
    nuclei: list[int] = []
    for i, (symbol, _) in enumerate(toks):
        if not _is_vowel(symbol):
            continue
        if nuclei and nuclei[-1] == i - 1 and symbol in _HIGH_OFFGLIDES and toks[i - 1][0] not in _HIGH_OFFGLIDES:
            continue
        if final_glide and nuclei and nuclei[-1] == i - 1 and i == len(toks) - 1 and symbol in _HIGH_OFFGLIDES:
            continue  # a word-final -io/-iu is one syllable (Portuguese sábio)
        nuclei.append(i)
    return nuclei


def syllable_starts(toks: list[tuple[str, str]], name: str) -> tuple[int, ...]:
    """Token index where each syllable's onset begins (first entry 0)."""
    structure = lexicon_audit.profile_structure(name)
    vowels = _nuclei(toks, name in _FINAL_GLIDE_LANGUAGES)
    starts = [0]
    for prev, nxt in zip(vowels, vowels[1:]):
        run = tuple(s for s, _ in toks[prev + 1:nxt])
        # maximal onset: the longest tail of the run that is a legal onset
        onset_len = 0
        for length in range(min(len(run), 4), 0, -1):
            if structure.is_valid_syllable(run[len(run) - length:], toks[nxt][0], ()):
                onset_len = length
                break
        starts.append(nxt - onset_len)
    return tuple(starts)


def syllable_count(ipa: str, name: str) -> int:
    return len(_nuclei(tokens(ipa, name), name in _FINAL_GLIDE_LANGUAGES))


def stressed_syllable(ipa: str, name: str) -> int | None:
    """0-based index of the syllable the ``ˈ`` mark precedes, or ``None``."""
    if STRESS_MARK not in ipa:
        return None
    before = ipa[: ipa.index(STRESS_MARK)]
    return syllable_count(before, name)


def with_stress(ipa: str, name: str, syllable: int | None) -> str:
    """``ipa`` with its stress mark moved to ``syllable`` (removed for ``None``
    or a monosyllable). Pitch/tone decorations stay on their vowels."""
    toks = tokens(ipa, name)
    starts = syllable_starts(toks, name)
    if syllable is None or len(starts) < 2:
        return "".join(s + d for s, d in toks)
    at = starts[max(0, min(syllable, len(starts) - 1))]
    return "".join((STRESS_MARK if i == at else "") + s + d for i, (s, d) in enumerate(toks))


def _is_heavy(toks: list[tuple[str, str]], starts: tuple[int, ...], syllable: int) -> bool:
    """Latin-style weight: a long vowel, a diphthong, or a coda consonant."""
    end = starts[syllable + 1] if syllable + 1 < len(starts) else len(toks)
    vowel = next(i for i in range(starts[syllable], end) if _is_vowel(toks[i][0]))
    nucleus = toks[vowel][0]
    off_glide = vowel + 1 < end and _is_vowel(toks[vowel + 1][0])
    return "ː" in nucleus or nucleus in _DIPHTHONGS or off_glide or vowel + 1 < end


_NASAL_VOWELS = frozenset("ãẽĩõũ") | {"ɛ̃", "ɔ̃"}


def _syllable_weights(toks: list[tuple[str, str]], starts: tuple[int, ...]) -> list[int]:
    """Syllable weights: 1 light (short vowel, open), 2 medium/heavy (long vowel, or a
    short vowel + one coda consonant), 3 heavy/superheavy (long vowel + coda, or two coda
    consonants). A nasal vowel or a diphthong counts as long and a geminate closes the
    syllable before it. Shared by Hindi and Arabic."""
    weights = []
    for k, start in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(toks)
        vowel = next(i for i in range(start, end) if _is_vowel(toks[i][0]))
        symbol = toks[vowel][0]
        long_vowel = (
            "ː" in symbol or symbol in _NASAL_VOWELS or symbol in _DIPHTHONGS or toks[vowel][1].count("̃") > 0
        )
        coda = sum(1 for s, _ in toks[vowel + 1:end] if not _is_vowel(s))
        if k + 1 < len(starts) and toks[starts[k + 1]][0].endswith("ː") and not _is_vowel(toks[starts[k + 1]][0]):
            coda += 1  # a geminate's first half closes this syllable
        weights.append(1 + (1 if long_vowel else 0) + min(coda, 2))
    return weights


def _hindi_stress(toks: list[tuple[str, str]], starts: tuple[int, ...]) -> int:
    """The heaviest syllable of the last three (the profile's own description of
    Hindi); on a tie the rightmost *non-final* one, so an all-equal word is penultimate;
    the final syllable wins only if strictly heavier than the others in the window."""
    weights = _syllable_weights(toks, starts)
    count = len(weights)
    window = list(range(max(0, count - 3), count))
    best = max(weights[i] for i in window)
    candidates = [i for i in window if weights[i] == best]
    non_final = [i for i in candidates if i != count - 1]
    return non_final[-1] if non_final else count - 1


def _arabic_stress(toks: list[tuple[str, str]], starts: tuple[int, ...]) -> int:
    """The Cairene / Modern Standard rule: a superheavy final syllable (long vowel + coda,
    or two codas) is stressed; otherwise the penult if it is heavy (a long vowel or a
    closed syllable); otherwise the antepenult (a disyllable with a light penult: its first).
    Classical and other colloquial dialects differ, which is why the profile calls Arabic
    stress dialect-dependent; this is the one rule taught for the standard language."""
    weights = _syllable_weights(toks, starts)
    count = len(weights)
    if weights[-1] >= 3:
        return count - 1
    if weights[-2] >= 2 or count == 2:
        return count - 2
    return count - 3


def default_stress_index(ipa: str, name: str) -> int | None:
    """The syllable ``name``'s own ``stress_pattern`` predicts, or ``None`` for a
    monosyllable or a pattern that cannot be derived from the sounds alone."""
    profile = _profile(name)
    toks = tokens(ipa, name)
    starts = syllable_starts(toks, name)
    count = len(starts)
    if count < 2:
        return None
    pattern = profile.stress_pattern
    if name == "Latin":
        # the classical rule: penult if heavy, else antepenult (a disyllable: the first)
        return count - 2 if _is_heavy(toks, starts, count - 2) or count == 2 else count - 3
    if name == "Basque":
        # Central/Gipuzkoan-style Batua: the second syllable of a word of three or more; a disyllable
        # keeps its first (etxe, ura). The profile calls Basque accentuation a live dialect dispute --
        # this is the commonly taught Central norm, not the only one.
        return 1 if count >= 3 else 0
    if name == "Hindi":
        return _hindi_stress(toks, starts)
    if name == "Arabic":
        return _arabic_stress(toks, starts)
    if pattern in ("", "lexical"):
        return None
    vowels = _nuclei(toks, name in _FINAL_GLIDE_LANGUAGES)
    final_coda = tuple(s for s, _ in toks[vowels[-1] + 1:] if not _is_vowel(s))
    first_long = next((k for k, i in enumerate(vowels) if "ː" in toks[i][0]), None)
    index = predict_default_stress(count, pattern, final_coda, toks[vowels[-1]][0], first_long)
    if name == "French" and toks[vowels[-1]][0] == "ə":
        index = max(0, count - 2)  # a final schwa is never stressed
    return index


def with_pitch_accent(ipa: str, name: str, accent: int) -> str:
    """Tokyo-dialect pitch accent as per-syllable High/Low marks, the same
    encoding generated Japanese words carry (``word_accent_gen.mark_positional_
    pitch_accent``). ``accent`` is the dictionary accent number in *morae*: 0 for
    a flat (heiban) word, otherwise the mora after which the pitch drops. Every
    vowel token is a syllable; a long vowel and a coda consonant (moraic ``n``,
    the first half of a geminate) each add a mora to their syllable."""
    from conlang_generator.generation.word_accent_gen import mark_positional_pitch_accent

    toks = [(s, "") for s, _ in tokens(ipa, name)]  # plain: drop any earlier marks
    vowels = [i for i, (s, _) in enumerate(toks) if _is_vowel(s)]
    if len(vowels) < 2:
        return "".join(s for s, _ in toks)
    moras_per_syllable = []
    for k, v in enumerate(vowels):
        end = vowels[k + 1] if k + 1 < len(vowels) else len(toks)
        run = end - v - 1  # consonant tokens after this vowel
        coda = 1 if (k + 1 == len(vowels) and run >= 1) or run >= 2 else 0
        moras_per_syllable.append(1 + ("ː" in toks[v][0]) + coda)
    kernel: int | None = None
    if accent > 0:
        seen = 0
        for k, moras in enumerate(moras_per_syllable):
            seen += moras
            if seen >= accent:
                kernel = k
                break
    marks = mark_positional_pitch_accent(kernel, len(vowels))
    out = []
    for i, (s, _) in enumerate(toks):
        out.append(s + (marks[vowels.index(i)] if i in vowels else ""))
    return "".join(out)


def pitch_pattern(ipa: str, name: str) -> str | None:
    """The word's H/L pattern as a string (``"LHH"``), or ``None`` if unmarked."""
    high, low = TONE_DIACRITICS_BY_LEVEL()
    pattern = ""
    for symbol, deco in tokens(ipa, name):
        if _is_vowel(symbol):
            pattern += "H" if high in deco else "L" if low in deco else "?"
    return pattern if pattern and "?" not in pattern else None


def TONE_DIACRITICS_BY_LEVEL():
    from conlang_generator.core.phonology import ToneLevel

    return TONE_DIACRITICS[ToneLevel.HIGH], TONE_DIACRITICS[ToneLevel.LOW]


def coverage(name: str) -> tuple[int, int]:
    """``(marked, polysyllabic)``: how many polysyllabic words carry a stress mark."""
    marked = total = 0
    for _, ipa in real_words(name).values():
        if syllable_count(ipa, name) > 1:
            total += 1
            marked += STRESS_MARK in ipa
    return marked, total
