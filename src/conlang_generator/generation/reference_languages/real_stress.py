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
# Hawaiian's ten diphthongs (a vowel + a second vowel in one syllable): everything else in a row is a hiatus
_HAWAIIAN_DIPHTHONGS = frozenset({"ae", "ai", "ao", "au", "ei", "eu", "iu", "oi", "ou", "ui"})
# Danish coda /r/ is realized as a vocalic offglide and this lexicon writes it as its own vowel
# symbol (mor "mother" /moːɐ/ is one syllable, tokenized as m + oː + ɑ) -- it always fuses with
# whatever vowel precedes it, unlike Hawaiian's fixed pair list or a high-offglide diphthong.
_ALWAYS_FUSES_AFTER_A_VOWEL = {"Danish": frozenset({"ɑ", "ɑː"})}


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


def _pairs(name: str) -> frozenset[str] | None:
    return _HAWAIIAN_DIPHTHONGS if name == "Hawaiian" else None


def _nuclei_for(toks: list[tuple[str, str]], name: str) -> list[int]:
    """``_nuclei`` with this language's own diphthong/offglide/fusion rules applied."""
    return _nuclei(toks, name in _FINAL_GLIDE_LANGUAGES, _pairs(name), _ALWAYS_FUSES_AFTER_A_VOWEL.get(name))


def _nuclei(
    toks: list[tuple[str, str]], final_glide: bool = False, pairs: frozenset[str] | None = None,
    always_fuses: frozenset[str] | None = None,
) -> list[int]:
    """Token index of each syllable's (first) vowel. Two vowels in a row make one
    syllable when the second is a high off-glide after a non-high vowel (``æ`` +
    ``i``, ``a`` + ``u``: a falling diphthong); otherwise they are a hiatus.
    ``always_fuses`` (Danish's vocalized coda /r/, written as its own vowel symbol):
    unlike the other two mechanisms, this symbol fuses into *any* preceding vowel,
    anywhere in the word, not just a fixed pair or a word-final position."""
    nuclei: list[int] = []
    for i, (symbol, _) in enumerate(toks):
        if not _is_vowel(symbol):
            continue
        if always_fuses and nuclei and nuclei[-1] == i - 1 and symbol in always_fuses:
            continue
        if pairs is not None:  # a language with an explicit diphthong list
            if nuclei and nuclei[-1] == i - 1 and toks[i - 1][0] + symbol in pairs:
                continue
            nuclei.append(i)
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
    vowels = _nuclei_for(toks, name)
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
    return len(_nuclei_for(tokens(ipa, name), name))


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


def _hawaiian_stress(toks: list[tuple[str, str]], starts: tuple[int, ...]) -> int:
    """Hawaiian is a right-to-left moraic trochee in which a long vowel or diphthong is a foot
    of its own: a heavy final syllable takes the stress (ʔehaː, inaː); otherwise the last
    foot is headed by the penult (a-LO-ha, KAː-ne, wa-HI-ne)."""
    count = len(starts)
    vowel = next(i for i in range(starts[-1], len(toks)) if _is_vowel(toks[i][0]))
    heavy = "ː" in toks[vowel][0] or (vowel + 1 < len(toks) and _is_vowel(toks[vowel + 1][0]))
    return count - 1 if heavy else count - 2


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
    if name == "Georgian":
        # Aronson's description: initial in words of two or three syllables, the antepenult in longer
        # ones. Whether Georgian stress is phonetically real at all is disputed (see the profile).
        return max(0, count - 3)
    if name == "Hawaiian":
        return _hawaiian_stress(toks, starts)
    if pattern in ("", "lexical"):
        return None
    vowels = _nuclei_for(toks, name)
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
    """The word's H/L pattern as a string (``"LHH"``; ``F`` marks a falling/circumflex
    syllable), or ``None`` if unmarked."""
    high, low = TONE_DIACRITICS_BY_LEVEL()
    from conlang_generator.core.phonology import ToneLevel

    falling = TONE_DIACRITICS[ToneLevel.FALLING]
    pattern = ""
    toks = tokens(ipa, name)
    for i in _nuclei_for(toks, name):
        deco = toks[i][1]
        pattern += "H" if high in deco else "L" if low in deco else "F" if falling in deco else "?"
    return pattern if pattern and "?" not in pattern else None


def TONE_DIACRITICS_BY_LEVEL():
    from conlang_generator.core.phonology import ToneLevel

    return TONE_DIACRITICS[ToneLevel.HIGH], TONE_DIACRITICS[ToneLevel.LOW]


def _greek_long(toks: list[tuple[str, str]], starts: tuple[int, ...], syllable: int) -> bool:
    end = starts[syllable + 1] if syllable + 1 < len(starts) else len(toks)
    vowel = next(i for i in range(starts[syllable], end) if _is_vowel(toks[i][0]))
    diphthong = vowel + 1 < end and _is_vowel(toks[vowel + 1][0])
    return "ː" in toks[vowel][0] or diphthong


def with_greek_accent(ipa: str, kernel: int, circumflex: bool | None = None) -> str:
    """Attic accent as the project encodes it (per-syllable High/Low marks with the
    circumflex as the falling mark on the kernel, ``mark_positional_pitch_accent``).
    ``circumflex=None`` applies the real rule: a circumflex needs a long penult under an
    accent with a short final syllable (final ``-ai``/``-oi`` count as short)."""
    from conlang_generator.generation.word_accent_gen import mark_positional_pitch_accent

    name = "Ancient Greek"
    toks = [(s, "") for s, _ in tokens(ipa, name)]
    starts = syllable_starts(toks, name)
    count = len(starts)
    kernel = max(0, min(kernel, count - 1))
    if circumflex is None:
        final_symbol = toks[next(i for i in range(starts[-1], len(toks)) if _is_vowel(toks[i][0]))][0]
        final_vowel = next(i for i in range(starts[-1], len(toks)) if _is_vowel(toks[i][0]))
        diph = final_vowel + 1 < len(toks) and _is_vowel(toks[final_vowel + 1][0])
        final_short = "ː" not in final_symbol and (not diph or (final_symbol + toks[final_vowel + 1][0]) in ("ai", "oi"))
        circumflex = kernel == count - 2 and _greek_long(toks, starts, kernel) and final_short
    marks = mark_positional_pitch_accent(kernel, count, circumflex)
    vowels = [next(i for i in range(starts[k], starts[k + 1] if k + 1 < count else len(toks)) if _is_vowel(toks[i][0])) for k in range(count)]
    return "".join(s + (marks[vowels.index(i)] if i in vowels else "") for i, (s, _) in enumerate(toks))


def with_sc_accent(ipa: str, syllable: int, long: bool | None = None) -> str:
    """Serbo-Croatian (Neo-Stokavian) accent: the stress mark before ``syllable`` plus, when
    the syllable's length is known, the four-way pitch x length diacritic on its vowel --
    falling on the word's first syllable, rising on any other (a Neo-Stokavian accent never
    falls anywhere else). ``long=None`` marks position only."""
    from conlang_generator.core.phonology import WordAccentCategory
    from conlang_generator.generation.word_accent_gen import _TONE_LENGTH_DIACRITICS

    name = "Serbo-Croatian"
    stressed = with_stress(ipa, name, syllable)
    if long is None:
        return stressed
    toks = tokens(stressed if STRESS_MARK not in stressed else stressed.replace(STRESS_MARK, ""), name)
    starts = syllable_starts(toks, name)
    if len(starts) < 2:
        return "".join(s + d for s, d in toks)
    syllable = max(0, min(syllable, len(starts) - 1))
    end = starts[syllable + 1] if syllable + 1 < len(starts) else len(toks)
    vowel = next(i for i in range(starts[syllable], end) if _is_vowel(toks[i][0]))
    category = WordAccentCategory.ACCENT_1 if syllable == 0 else WordAccentCategory.ACCENT_2
    mark = _TONE_LENGTH_DIACRITICS[(category, long)]
    out = []
    for i, (s, d) in enumerate(toks):
        out.append((STRESS_MARK if i == starts[syllable] else "") + s + (mark if i == vowel else d))
    return "".join(out)


# Danish stød: the consonants after a short vowel that make a syllable "heavy" (with r vocalized
# and ð/v/j/w approximants), and the function words that never take it
_DANISH_SONORANTS = frozenset({"n", "m", "ŋ", "l", "ʁ", "ð", "v", "j", "w"})
_DANISH_NO_STOD = frozenset(
    "jeg du han hun vi de den det og i på til fra med for af om hvis når hvor hvem hvad ved at som".split()
)


# Common Scandinavian accent 1 (Danish stød, Swedish/Norwegian tonem 1) has one reliable
# synchronic marker beyond the shape rules already applied: a word whose unstressed final
# syllable is a bare sonorant with no full vowel of its own (real -el/-en/-er/-el, historically
# a monosyllabic root + an early, tonally-inert suffix: Swedish "vatten", "fågel", "vinter",
# Danish "vinter", Norwegian "vinter") is accent 1 -- unlike a genuine second full syllable
# (Swedish "gata", "flicka"), which stays accent 2. Real -er that *is* a live derivational
# suffix (agentive -are, comparative -are/-ere) does not trigger this and is excluded by
# checking the syllable actually has no vowel of its own.
_REDUCED_SONORANTS = frozenset({"l", "n", "r"})
_REDUCED_VOWELS = frozenset({"ɛ", "ə"})  # this lexicon's own transcription of the reduced vowel these take


def has_reduced_final_syllable(toks: list[tuple[str, str]], starts: tuple[int, ...]) -> bool:
    if len(starts) < 2:
        return False
    rime = toks[next(i for i in range(starts[-1], len(toks)) if _is_vowel(toks[i][0])):]
    return (
        len(rime) == 2
        and rime[0][0] in _REDUCED_VOWELS
        and rime[1][0] in _REDUCED_SONORANTS
    )


def stod_applies(ipa: str, spelling: str, accent_1: bool | None = None) -> bool:
    """Whether a Danish word's stressed syllable takes stød: a heavy syllable (a long vowel or
    diphthong, or a short vowel + a sonorant coda) that is not a function word, on a word that
    is accent-1 lineage. For a monosyllable that lineage is the (usual) case, so ``accent_1``
    defaults to ``True``; a genuine reduced final syllable (*vinter*) also defaults to accent 1.
    A real polysyllable needs ``accent_1`` given explicitly (curated) -- stød is otherwise
    unknown for it, same as accent 1 vs 2 is unknown for an uncurated Swedish/Norwegian word."""
    name = "Danish"
    toks = tokens(ipa, name)
    starts = syllable_starts(toks, name)
    stressed = stressed_syllable(ipa, name)
    monosyllable = len(starts) == 1
    if accent_1 is None:
        accent_1 = True if (monosyllable or has_reduced_final_syllable(toks, starts)) else False
    if not accent_1 or spelling.lower() in _DANISH_NO_STOD:
        return False
    syllable = stressed if stressed is not None else 0
    # Heaviness looks at every consonant up to the *next vowel*, not just the maximal-onset
    # syllable boundary: real Danish stød-basis is the stressed vowel's own historical rhyme
    # (gammel/himmel: the intervocalic sonorant closed it before the modern single-consonant
    # spelling), which a synchronic maximal-onset syllable split would wrongly hand to the
    # following syllable's onset instead.
    end = starts[syllable + 1] if syllable + 1 < len(starts) else len(toks)
    next_vowel = next((i for i in range(end, len(toks)) if _is_vowel(toks[i][0])), len(toks))
    vowel = next(i for i in range(starts[syllable], end) if _is_vowel(toks[i][0]))
    nucleus = toks[vowel][0]
    coda = [s for s, _ in toks[vowel + 1:next_vowel] if not _is_vowel(s)]
    long_vowel = "ː" in nucleus or (vowel + 1 < end and _is_vowel(toks[vowel + 1][0]))
    return long_vowel or (bool(coda) and coda[-1] in _DANISH_SONORANTS)


def with_stod(ipa: str, spelling: str, accent_1: bool | None = None) -> str:
    """``ipa`` with the glottalization mark after the stressed syllable's rime when the word
    takes stød. ``accent_1``: see ``stod_applies``. The word's own stress mark (if any) is kept
    either way."""
    name = "Danish"
    toks = tokens(ipa, name)
    starts = syllable_starts(toks, name)
    stress = stressed_syllable(ipa, name)
    plain = "".join(s + d for s, d in toks)
    takes_stod = stod_applies(plain, spelling, accent_1)
    syllable = stress if stress is not None else 0
    end = starts[syllable + 1] if syllable + 1 < len(starts) else len(toks)
    return "".join(
        (STRESS_MARK if stress is not None and i == starts[stress] else "")
        + s + d + (WORD_ACCENT_MARK if takes_stod and i == end - 1 else "")
        for i, (s, d) in enumerate(toks)
    )


def with_scandinavian_accent(ipa: str, name: str, category: int | None = None) -> str:
    """Swedish/Norwegian word accent as the project encodes it: a High diacritic on the accented
    syllable's vowel for accent 1, a Low one for accent 2. The accented syllable is the stressed
    one (the word's first for a monosyllable). ``category`` (1 or 2), when given, overrides the
    default -- accent 1 for a monosyllable, a word stressed on its last syllable, or a reduced
    final syllable (*vatten*, *fågel*, *vinter*), accent 2 otherwise (the profile's own
    ``underived_monosyllable`` default plus that one reliable exception). Real polysyllables have
    further lexical exceptions this does not know unless ``category`` is given."""
    from conlang_generator.core.phonology import ToneLevel

    stress = stressed_syllable(ipa, name)
    toks = tokens(ipa, name)
    starts = syllable_starts(toks, name)
    accented = stress if stress is not None else 0
    accented = min(accented, len(starts) - 1)
    if category is not None:
        accent_one = category == 1
    else:
        accent_one = len(starts) == 1 or accented == len(starts) - 1 or has_reduced_final_syllable(toks, starts)
    mark = TONE_DIACRITICS[ToneLevel.HIGH if accent_one else ToneLevel.LOW]
    end = starts[accented + 1] if accented + 1 < len(starts) else len(toks)
    vowel = next(i for i in range(starts[accented], end) if _is_vowel(toks[i][0]))
    out = []
    for i, (s, d) in enumerate(toks):
        out.append((STRESS_MARK if stress is not None and i == starts[stress] else "") + s + (mark if i == vowel else d))
    return "".join(out)


def scandinavian_accent(ipa: str, name: str) -> int | None:
    """The word accent (1 or 2) a Swedish/Norwegian word carries, read from its High/Low mark."""
    from conlang_generator.core.phonology import ToneLevel

    marks = "".join(deco for _, deco in tokens(ipa, name))
    if TONE_DIACRITICS[ToneLevel.HIGH] in marks:
        return 1
    if TONE_DIACRITICS[ToneLevel.LOW] in marks:
        return 2
    return None


def coverage(name: str) -> tuple[int, int]:
    """``(marked, polysyllabic)``: how many polysyllabic words carry a stress mark or a
    pitch-accent pattern (Japanese, Ancient Greek)."""
    marked = total = 0
    for _, ipa in real_words(name).values():
        if syllable_count(ipa, name) > 1:
            total += 1
            marked += (
                STRESS_MARK in ipa or pitch_pattern(ipa, name) is not None
                or (name in ("Swedish", "Norwegian") and scandinavian_accent(ipa, name) is not None)
            )
    return marked, total
