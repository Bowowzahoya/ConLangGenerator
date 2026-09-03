"""Deterministic IPA -> Latin transliteration, kept separate from IPA storage.

A ``RomanizationScheme`` never touches the stored IPA; it only renders a
display form. Rules are tried longest-``ipa``-pattern-first so multi-symbol
sequences (e.g. affricates, toned vowels) are matched before their
single-symbol parts.

A rule can optionally be conditioned two different ways, which are *not*
interchangeable:

- ``following``/``preceding`` -- a tuple of *tags* that must intersect the
  immediate neighbor's own computed tag set. A tag is either a literal ipa
  symbol (matches an exact neighboring phoneme, e.g. Mandarin pinyin writes
  /y/ as "u" instead of "ü" specifically after j/q/x/y:
  ``preceding=("j", "q", "x", "y")``) or one of the classes
  ``"vowel"``/``"consonant"``/``"boundary"`` (nothing there) or
  ``"front_vowel"``/``"back_vowel"`` (French/Italian/Spanish spell a
  consonant differently before a front vs. back vowel, e.g. "g" before
  "e"/"i" vs. "ge" before "a"/"o"/"u" to keep it soft). These describe the
  *neighbor*.
- ``syllable`` -- a tuple containing ``"syllable_open"`` and/or
  ``"syllable_closed"``, describing this symbol's *own* structural
  position, not a neighbor's (Dutch marks vowel length by doubling only in
  a closed syllable: "vuur" /vy:r/ vs. "vuren" /'vy:.rən/ -- the vowel's
  own openness, computed by looking at what follows *it*, under the
  maximal-onset principle: open if nothing follows, or if the following
  consonant(s) belong to the *next* syllable's onset rather than this
  one's coda). A vowel can't be conditioned on its own frontness the way
  it can on syllable position -- its identity (which ipa symbol it is)
  already fixes that, so unlike ``syllable`` there's no self-referential
  form of ``front_vowel``/``back_vowel`` to speak of.

All of this comes from plain symbol-set data supplied by whoever builds
the scheme -- ``core/`` itself has no phonological knowledge. When several
of a symbol's rules match a position, the more specific one wins (an
exact-symbol match beats a class match; matching on more conditions beats
matching on fewer).

``OrthographyCategory`` (bottom of this module) names a *typology* --
digraph vs. diacritic vs. monoletter exotic-symbol spelling, a vowel-
length-marking convention, short-vowel-triggered consonant doubling, and
a tone-marking strategy -- that ``generation.romanization_gen`` uses to
build a coherent, nameable ``RomanizationScheme`` (logged onto it via
``category_name``/``tone_strategy``/``tone_markers`` for provenance) and
that a ``ReferenceLanguageProfile`` can optionally point at. Tone-mark
placement is the one category axis ``apply()`` itself has real branching
for -- see its own docstring.
"""

from __future__ import annotations

import unicodedata
from enum import Enum

from pydantic import BaseModel

_CLASS_TAGS = frozenset(
    {
        "vowel", "consonant", "boundary", "front_vowel", "back_vowel",
        "long_vowel", "short_vowel", "syllable_open", "syllable_closed",
    }
)


class RomanizationRule(BaseModel, frozen=True):
    ipa: str
    latin: str
    following: tuple[str, ...] = ()
    preceding: tuple[str, ...] = ()
    syllable: tuple[str, ...] = ()


class ToneMarkingStrategy(str, Enum):
    """How a tone diacritic on a vowel's IPA symbol (see
    ``core.phonology.ToneSystem.mark``) surfaces in the Latin spelling.
    ``RomanizationScheme.apply`` treats a tone mark as an opaque combining
    character -- it never imports ``core.phonology``'s ``ToneLevel``, so
    this stays decoupled from tone semantics; a category just supplies a
    ``(mark character, replacement text)`` table via ``tone_markers``."""

    VOWEL_DIACRITIC = "vowel_diacritic"
    """Today's only behavior: the mark stays inline on the vowel."""
    POSTPOSED_DIGIT = "postposed_digit"
    """Wade-Giles / numbered-Pinyin style: a digit after the syllable."""
    POSTPOSED_LETTER = "postposed_letter"
    """Zhuang-style: a letter after the syllable."""
    UNMARKED = "unmarked"
    """Tone simply isn't written."""


class VowelLengthStrategy(str, Enum):
    """How a phonemically long vowel (``core.phonology.Vowel.long``) is
    distinguished in spelling from its short counterpart."""

    NONE = "none"
    """Length isn't marked in the spelling at all."""
    DOUBLING = "doubling"
    """The letter is doubled, e.g. "a"/"aa" -- Dutch, Finnish, Estonian.
    Only makes visual sense in a closed syllable (see
    ``RomanizationRule.syllable``), unlike the other two strategies."""
    MACRON = "macron"
    """A macron over the letter, e.g. "ā" -- the scholarly convention
    shared by Latin, Hawaiian, and Japanese romaji transliteration."""
    COLON = "colon"
    """An ASCII colon after the letter, e.g. "a:" -- an informal but
    attested transliteration stand-in for IPA's own length mark."""
    SILENT_E = "silent_e"
    """English-style: the vowel keeps its plain short-vowel letter, but a
    mute "e" is appended after the syllable's own coda when that syllable
    would otherwise read as closed/short ("mat" vs. "mate") -- an open
    syllable already reads long with nothing appended, the same as
    ``DOUBLING``'s open-syllable case. Realized in ``apply()`` itself
    (see ``RomanizationScheme``), not as a generated ``RomanizationRule``,
    since the "e" lands *after* the coda consonant(s), not on the vowel's
    own token."""


class SyllableBoundaryMarker(str, Enum):
    """Whether/how two adjacent syllables get a separator when the first
    ends in a vowel and the second begins with one -- without one, the
    two vowel letters read as a single ambiguous sequence (Pinyin's own
    real rule: "Xi'an" vs. "Xian"). A diphthong is its own atomic,
    multi-character symbol (``core.phonology.Vowel.diphthong``), so
    ``RomanizationScheme.apply()``'s greedy longest-match always prefers
    it over decomposing into two adjacent single-character vowel tokens
    when *that scheme* has it registered -- meaning two adjacent vowel
    symbols mean a genuine hiatus specifically when the *language* in
    question doesn't have that sequence as one of its own diphthongs,
    the same way a real listener's own language would parse it. This is
    safe in practice for anything this project's own generation actually
    produces: `generation.word_builder`'s syllable builder always inserts
    an onset consonant between two nuclei whenever `max_onset >= 1` (the
    common case), so two bare vowel nuclei never end up literally
    adjacent to begin with. The member's own value *is* the
    literal marker text, unlike ``tone_markers`` (no per-language lookup
    table needed)."""

    NONE = ""
    APOSTROPHE = "'"
    HYPHEN = "-"


class ExoticSymbolStyle(str, Enum):
    """How a phoneme with no obvious single Latin letter gets spelled,
    absent a more specific rule (reference-language deviation, or one of
    ``OrthographyCategory``'s other generated rules)."""

    MONOLETTER = "monoletter"
    """One ASCII letter per sound, even at the cost of merging some
    distinctions -- a "shallow"/phonemic system in the spirit of Finnish,
    Swahili, or informal Georgian transliteration."""
    DIGRAPH = "digraph"
    """A two-letter ASCII sequence, e.g. "ʃ" -> "sh"."""
    DIACRITIC = "diacritic"
    """A single Latin-Extended letter, e.g. "ʃ" -> "š"."""


class RomanizationScheme(BaseModel, frozen=True):
    rules: tuple[RomanizationRule, ...]
    vowel_symbols: tuple[str, ...] = ()
    """Which of this scheme's ipa symbols are vowels -- needed to compute
    the vowel/consonant, backness, and syllable-openness tags. Empty means
    no rule here uses adjacency conditions (or the builder didn't supply
    this), in which case every symbol just uses its unconditioned rule,
    identical to this scheme's pre-context-sensitivity behavior."""
    legal_onset_clusters: tuple[tuple[str, str], ...] = ()
    """Which 2-consonant sequences are a legal syllable onset in this
    language -- lets a whole cluster shift to the next syllable under the
    maximal-onset principle, not just a single consonant."""
    vowel_backness: tuple[tuple[str, str], ...] = ()
    """``(symbol, "front"|"back"|"central")`` pairs, for the
    ``"front_vowel"``/``"back_vowel"`` tags."""
    vowel_length: tuple[tuple[str, str], ...] = ()
    """``(symbol, "long"|"short")`` pairs, for the ``"long_vowel"``/
    ``"short_vowel"`` tags -- same role as ``vowel_backness`` above."""
    category_name: str = ""
    """A purely cosmetic, human-readable label for whichever
    ``generation.romanization_gen`` ``OrthographyCategory`` built this
    scheme -- a named preset's own name when one exactly matches (an
    explicit force, or a successful reference-profile/prompt bias), a
    synthesized description of the composed axes otherwise (empty for a
    scheme built without one, e.g. directly in a test). Never load-
    bearing: every axis this scheme actually needs (for ``apply()`` or
    for regenerating new rules during evolution) is one of the fields
    below, read directly -- this field is not looked up against a
    registry for anything."""
    tone_strategy: ToneMarkingStrategy = ToneMarkingStrategy.VOWEL_DIACRITIC
    tone_markers: tuple[tuple[str, str], ...] = ()
    """``(combining-mark character, postposed marker text)`` pairs, used
    when ``tone_strategy`` is ``POSTPOSED_DIGIT``/``POSTPOSED_LETTER``."""
    vowel_length_strategy: VowelLengthStrategy = VowelLengthStrategy.NONE
    short_vowel_consonant_doubling: bool = False
    exotic_symbol_style: ExoticSymbolStyle = ExoticSymbolStyle.DIGRAPH
    syllable_boundary_marker: SyllableBoundaryMarker = SyllableBoundaryMarker.NONE
    consonant_gemination_marked: bool = False
    """Whether a phonemically long/geminate consonant (``core.phonology.Consonant.long``,
    e.g. Italian "sono" vs. "sonno") doubles its own letter -- distinct
    from ``short_vowel_consonant_doubling`` above, which *derives*
    doubling from a neighboring short vowel rather than marking a length
    distinction the consonant already has on its own. Unlike vowel
    length there's no real cross-linguistic variety in *how* gemination
    gets spelled (doubling is the near-universal Latin-alphabet
    convention), so this is a bare bool, not a strategy enum.

    This field plus the five above it (``tone_strategy``/``tone_markers``
    included) are the complete, independent set of axes
    ``generation.romanization_gen``'s ``OrthographyCategory`` composes --
    stored directly (not just ``category_name``) so evolution can
    reconstruct the exact category that built this scheme
    (``_category_from_scheme``) instead of inferring an approximation
    from which symbol happens to have which letter."""

    def _known_symbols(self) -> list[str]:
        return sorted({rule.ipa for rule in self.rules}, key=len, reverse=True)

    def _tokenize(self, ipa_text: str) -> list[tuple[str | None, str, str]]:
        """Greedy longest-match against this scheme's own ipa symbols.
        Returns ``(symbol, decoration, raw)`` triples: a matched symbol
        carries its trailing combining-mark decoration in ``decoration``
        (``raw`` empty); an unrecognized character is carried in ``raw``
        verbatim (``symbol`` is ``None``), matching this scheme's long-
        standing "unmapped input passes through unchanged" contract."""
        known = self._known_symbols()
        tokens: list[tuple[str | None, str, str]] = []
        i = 0
        while i < len(ipa_text):
            matched = next((s for s in known if ipa_text.startswith(s, i)), None)
            if matched is None:
                tokens.append((None, "", ipa_text[i]))
                i += 1
                continue
            i += len(matched)
            deco = ""
            while i < len(ipa_text) and unicodedata.combining(ipa_text[i]):
                deco += ipa_text[i]
                i += 1
            tokens.append((matched, deco, ""))
        return tokens

    def _coda_run_length(self, tokens: list[tuple[str | None, str, str]], index: int) -> int | None:
        """How many of this vowel's immediately-following consonant tokens
        belong to *its own* syllable coda, as opposed to the next
        syllable's onset, under the maximal-onset principle (``None`` if
        ``index`` isn't a vowel token). Shared by ``_syllable_openness``
        (open iff this is 0) and ``apply()``'s postposed-tone placement
        (a marker is flushed once this many coda tokens have passed)."""
        symbol = tokens[index][0]
        if symbol is None or symbol not in self.vowel_symbols:
            return None
        rest = tokens[index + 1 :]
        consonant_run: list[str] = []
        j = 0
        while j < len(rest) and rest[j][0] is not None and rest[j][0] not in self.vowel_symbols:
            consonant_run.append(rest[j][0])  # type: ignore[arg-type]
            j += 1
        if j == len(rest):
            return len(consonant_run)  # word-final: all belong to this syllable's coda
        if len(consonant_run) <= 1:
            return 0
        if len(consonant_run) == 2 and tuple(consonant_run) in self.legal_onset_clusters:
            return 0
        return len(consonant_run) - 1

    def _syllable_openness(self, tokens: list[tuple[str | None, str, str]], index: int) -> str | None:
        """This token's *own* syllable-openness tag (``None`` if it isn't
        a vowel) -- a self-referential property, not a neighbor's."""
        coda_len = self._coda_run_length(tokens, index)
        if coda_len is None:
            return None
        return "syllable_open" if coda_len == 0 else "syllable_closed"

    def _neighbor_tags(self, tokens: list[tuple[str | None, str, str]], index: int) -> frozenset[str]:
        """The tag set a ``following``/``preceding`` condition matches
        against: the neighbor's own symbol, plus its vowel/consonant and
        backness class. Out-of-range (word start/end) or an unrecognized
        character both count as ``"boundary"``. Deliberately excludes
        syllable-openness -- that's self-referential, checked via
        ``syllable`` instead, never as something a neighbor "has"."""
        if index < 0 or index >= len(tokens):
            return frozenset({"boundary"})
        symbol = tokens[index][0]
        if symbol is None:
            return frozenset({"boundary"})
        tags = {symbol}
        if symbol in self.vowel_symbols:
            tags.add("vowel")
            backness = dict(self.vowel_backness).get(symbol)
            if backness in ("front", "back"):
                tags.add(f"{backness}_vowel")
            length = dict(self.vowel_length).get(symbol)
            if length in ("long", "short"):
                tags.add(f"{length}_vowel")
        else:
            tags.add("consonant")
        return frozenset(tags)

    @staticmethod
    def _specificity(rule: RomanizationRule) -> int:
        score = 0
        for tags in (rule.preceding, rule.following, rule.syllable):
            if tags:
                score += 1
                if any(tag not in _CLASS_TAGS for tag in tags):
                    score += 1  # an exact-symbol tag is more specific than a class tag
        return score

    def apply(self, ipa_text: str) -> str:
        """Greedily rewrite an IPA string into its Latin romanization.

        The result is normalized to NFC (precomposed accents, e.g. a single
        'é' codepoint) so it matches what a human typing or copy-pasting the
        romanization would produce -- IPA itself is left untouched, since
        combining diacritics are the conventional IPA representation.

        A tone mark riding a vowel's decoration is handled per
        ``tone_strategy``: ``VOWEL_DIACRITIC`` (the default) leaves it
        inline, unchanged from this method's original behavior;
        ``UNMARKED`` drops it; ``POSTPOSED_DIGIT``/``POSTPOSED_LETTER``
        looks it up in ``tone_markers`` and, instead of appending it
        inline, defers it until this vowel's own syllable coda (see
        ``_coda_run_length``) has been emitted -- i.e. right before the
        next syllable's onset, or at the very end of the word.

        Two more axes get narrow, independent handling here.
        ``vowel_length_strategy == SILENT_E``: a vowel tagged ``"long"``
        in ``vowel_length`` that lands in a closed syllable schedules a
        literal "e" into the *same* deferred-marker mechanism the
        postposed-tone case uses, flushed at the same position (English
        "mat" vs. "mate" -- an open syllable already reads long, nothing
        scheduled). ``syllable_boundary_marker``: unlike the other axes,
        this is immediate, not deferred -- when a vowel token's
        immediately preceding token was also a vowel (a hiatus for *this*
        scheme specifically -- see ``SyllableBoundaryMarker``'s own
        docstring for why a registered diphthong never gets mistaken for
        one), the marker is emitted right before that vowel's own letter
        (Pinyin's own real rule: "Xi'an" vs. "Xian").
        """
        tokens = self._tokenize(ipa_text)
        rules_by_ipa: dict[str, list[RomanizationRule]] = {}
        for rule in self.rules:
            rules_by_ipa.setdefault(rule.ipa, []).append(rule)
        tone_marker_map = dict(self.tone_markers)
        postposed = self.tone_strategy in (ToneMarkingStrategy.POSTPOSED_DIGIT, ToneMarkingStrategy.POSTPOSED_LETTER)
        vowel_length_map = dict(self.vowel_length)

        pending_markers: dict[int, list[str]] = {}
        out: list[str] = []
        for index, (symbol, deco, raw) in enumerate(tokens):
            out.extend(pending_markers.pop(index, ()))
            if symbol is None:
                out.append(raw)
                continue
            preceding_tags = self._neighbor_tags(tokens, index - 1)
            following_tags = self._neighbor_tags(tokens, index + 1)
            own_syllable_tag = self._syllable_openness(tokens, index)
            own_tags = {own_syllable_tag} if own_syllable_tag else set()
            best: RomanizationRule | None = None
            best_score = -1
            for rule in rules_by_ipa.get(symbol, []):
                if rule.preceding and not (set(rule.preceding) & preceding_tags):
                    continue
                if rule.following and not (set(rule.following) & following_tags):
                    continue
                if rule.syllable and not (set(rule.syllable) & own_tags):
                    continue
                score = self._specificity(rule)
                if score > best_score:
                    best, best_score = rule, score
            latin = best.latin if best is not None else symbol

            if deco and self.tone_strategy == ToneMarkingStrategy.UNMARKED:
                deco = ""
            elif deco and postposed and any(ch in tone_marker_map for ch in deco):
                marker_text = "".join(tone_marker_map.get(ch, ch) for ch in deco)
                deco = ""
                flush_index = index + 1 + (self._coda_run_length(tokens, index) or 0)
                pending_markers.setdefault(flush_index, []).append(marker_text)

            if (
                self.vowel_length_strategy == VowelLengthStrategy.SILENT_E
                and own_syllable_tag == "syllable_closed"
                and vowel_length_map.get(symbol) == "long"
            ):
                flush_index = index + 1 + (self._coda_run_length(tokens, index) or 0)
                pending_markers.setdefault(flush_index, []).append("e")

            if self.syllable_boundary_marker and symbol in self.vowel_symbols and index > 0 and tokens[index - 1][0] in self.vowel_symbols:
                out.append(self.syllable_boundary_marker.value)
            out.append(latin + deco)
        out.extend(pending_markers.pop(len(tokens), ()))
        return unicodedata.normalize("NFC", "".join(out))


class OrthographyCategory(BaseModel, frozen=True):
    """A reusable orthography *typology* -- not a full per-language rule
    set (that's what ``ReferenceLanguageProfile.orthography`` and its own
    hand-curated ``RomanizationRule``s are for), but the handful of
    higher-level, genuinely independent conventions that make an
    orthography feel like a particular real-world family: how it spells
    an otherwise-exotic sound (``exotic_symbol_style``), whether/how it
    marks vowel length (``vowel_length_strategy``, including English's
    own trailing-silent-e convention), whether a short vowel makes the
    following onset consonant double (``short_vowel_consonant_doubling``),
    how tone (if any) surfaces (``tone_strategy``), and whether/how a
    vowel-initial syllable following a vowel-final one gets a separator
    (``syllable_boundary_marker``, Pinyin's own real "Xi'an" vs. "Xian"
    rule).

    ``generation.romanization_gen._CATEGORIES`` holds a handful of named
    *anchor* instances (e.g. ``"germanic-doubling-style"``,
    ``"wade-giles-style"``) for real, attested combinations -- useful as
    exact, keyword-forceable targets (``OrthographyForce.style``, below)
    and as what a ``ReferenceLanguageProfile`` can point at via its own
    ``orthography_category`` (a coarse "which family does this lean
    toward" signal). But since every field here is independent, nothing
    requires a language to use one of those fixed bundles: the *default*
    unforced case rolls each axis separately (``_roll_independent_axes``),
    so e.g. Dutch/German-style vowel-length doubling and Wade-Giles-style
    postposed-digit tone marking -- two different named anchors' axes --
    can and do co-occur in a freshly generated language."""

    name: str
    description: str
    exotic_style: dict[str, str]
    exotic_symbol_style: ExoticSymbolStyle = ExoticSymbolStyle.DIGRAPH
    """Which of the three conventions ``exotic_style`` itself follows --
    purely descriptive metadata (``apply()`` only ever consults
    ``exotic_style``/``rules`` directly), so a consumer can group or
    display categories by this axis without string-matching ``name``."""
    tone_strategy: ToneMarkingStrategy = ToneMarkingStrategy.VOWEL_DIACRITIC
    tone_markers: tuple[tuple[str, str], ...] = ()
    vowel_length_strategy: VowelLengthStrategy = VowelLengthStrategy.NONE
    short_vowel_consonant_doubling: bool = False
    """The Dutch/German/English-ish convention where an onset consonant
    doubles specifically because the *preceding* vowel is short (Dutch
    "zitten" vs "zaten", German "Bett") -- realized purely as data (a
    ``preceding=("short_vowel",)``-conditioned ``RomanizationRule`` per
    consonant), reusing the existing tag-matching machinery rather than
    any new code path in ``apply()``."""
    syllable_boundary_marker: SyllableBoundaryMarker = SyllableBoundaryMarker.NONE
    consonant_gemination_marked: bool = False
    """Whether a phonemically long/geminate consonant doubles its own
    letter (Italian "sono" vs. "sonno") -- distinct from
    ``short_vowel_consonant_doubling`` above, which derives doubling from
    a neighboring short *vowel* rather than the consonant's own length."""


class OrthographyForce(BaseModel, frozen=True):
    """Explicit, deterministic overrides for ``generation.romanization_gen``'s
    style selection -- the unconditional channel (same spirit as
    ``GenerationSpec``'s ``force_isolated``/``force_high_altitude``/
    ``force_tonal``): a prompt's wording, and a matched reference
    profile's own bias, are inference and can be wrong or absent; this is
    a guarantee, for testing or for when you want a specific style and
    nothing else.

    ``None`` on any field means "not forced, let the normal roll/bias
    decide." ``style`` picks one of ``generation.romanization_gen``'s
    named anchor presets outright (exact, no ``rng`` consumption); any of
    the other fields set *on top* override just that one axis, composing
    with whatever ``style`` (or the roll/bias, if ``style`` is unset)
    produced -- e.g. ``OrthographyForce(style="germanic-doubling-style",
    tone_strategy=POSTPOSED_DIGIT)`` is Dutch/German-style doubling with
    Wade-Giles-style tone digits, forced and reproducible, a combination
    no single named preset has on its own."""

    style: str | None = None
    exotic_symbol_style: ExoticSymbolStyle | None = None
    vowel_length_strategy: VowelLengthStrategy | None = None
    short_vowel_consonant_doubling: bool | None = None
    tone_strategy: ToneMarkingStrategy | None = None
    syllable_boundary_marker: SyllableBoundaryMarker | None = None
    consonant_gemination_marked: bool | None = None
