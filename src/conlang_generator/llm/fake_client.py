"""Deterministic, zero-cost stand-in for a real LLM.

Used as the default everywhere (dry runs, tests) per the project's
fake-LLM-first rule. It doesn't try to understand a prompt's meaning; callers
that need specific fake behavior say so explicitly via ``request.metadata``:

- ``fake_strategy=\"choose_index\"`` + ``num_options=\"N\"``: returns a stable
  ``\"1\"``..``\"N\"`` derived from a hash of the prompt (used by
  ``generation/lexicon_gen.py`` to pick among pre-built candidate words).
- ``fake_strategy=\"batch_choose_index\"`` + ``candidate_counts=\"5,5,4,...\"``
  (comma-joined per-word candidate counts): the batched counterpart of
  ``choose_index`` (used by ``lexicon_gen.choose_best_candidates_batch``) --
  returns one ``WORD_NUMBER:CANDIDATE_NUMBER`` line per word, each index a
  stable hash of ``prompt`` plus that word's own position.
- ``fake_strategy=\"passthrough\"`` + ``fallback_text=\"...\"``: echoes that
  text back verbatim (used where a real model would polish a deterministic
  draft -- in fake mode the draft is the answer).
- ``fake_strategy=\"trait_profile\"`` + ``trait_fields=\"a,b,c\"``: returns a
  JSON object with each named field set to a hash-derived float in
  ``[-1.0, 1.0]`` (used by ``generation/prompt_classifier.py``). List/free-text
  fields are intentionally left empty -- the fake doesn't understand prompt
  semantics, it just needs to vary deterministically by prompt (spanning both
  positive and negative) so tests can exercise "different prompts ->
  different generated languages" in both directions.
- ``fake_strategy=\"guess_ipa\"``: returns a crude, deterministic letter-by-
  letter respelling of ``request.prompt`` (the word's spelling) into
  IPA-shaped output -- common digraphs (sh/ch/th/ng/ph/qu) map to their
  usual IPA symbol, most Latin letters map straight through. This is
  explicitly not real phonetic analysis, just enough to be IPA-shaped for
  tests and dry runs (used by ``generation/seed_examples.py``).
- ``fake_strategy=\"sentence_plan\"`` + the grammar-shape keys
  ``translation/sentence_planner.py`` sets (``word_order``, ``alignment``,
  ``cases``, ``tenses``, ``has_articles``, ``has_overt_copula``,
  ``adjective_after_noun``): returns a JSON array of plan-slot objects
  reproducing, deterministically and without real language understanding,
  the same two-pattern (predicate-adjective / subject-verb-object)
  structure ``translate_to_conlang`` used before the LLM-drafted planner
  existed, plus a one-slot-per-word fallback for anything else -- see
  ``_fake_sentence_plan``'s own docstring for the exact heuristic.
- anything else: an opaque deterministic placeholder string.
"""

from __future__ import annotations

import hashlib
import json
import re

from conlang_generator.llm.base import LLMRequest, LLMResponse

FAKE_MODEL_NAME = "fake-llm"

_GUESS_IPA_DIGRAPHS = (("sh", "ʃ"), ("ch", "tʃ"), ("th", "θ"), ("ng", "ŋ"), ("ph", "f"), ("qu", "kw"))
_GUESS_IPA_LETTERS = {
    "a": "a", "e": "e", "i": "i", "o": "o", "u": "u", "y": "j",
    "p": "p", "t": "t", "k": "k", "b": "b", "d": "d", "g": "g",
    "m": "m", "n": "n", "s": "s", "f": "f", "l": "l", "r": "ɾ",
    "w": "w", "h": "h", "v": "v", "z": "z", "c": "k", "j": "dʒ", "x": "ks", "q": "k",
}


def stable_hash(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16)


def _fake_trait_profile(prompt: str, field_names: list[str]) -> str:
    values = {name: round((stable_hash(prompt + name) % 201 - 100) / 100.0, 2) for name in field_names}
    return json.dumps(values)


_FAKE_ARTICLES = {"a", "an", "the"}
_FAKE_COPULAS = {"is", "are", "am", "was", "were", "be", "been", "being"}
_FAKE_PAST_COPULAS = {"was", "were"}
_FAKE_PRONOUN_TOKENS = {
    "i", "you", "he", "we", "this", "that", "she", "it", "they", "me", "him", "us", "them",
    "myself", "yourself", "himself", "herself", "itself", "ourselves", "yourselves", "themselves", "oneself",
    "eachother",
}
_FAKE_REFLEXIVES = {
    "myself": "i", "yourself": "you", "himself": "he", "herself": "she", "itself": "it", "ourselves": "we",
    "yourselves": "you", "themselves": "they", "oneself": "he",
}
_FAKE_RECIPROCAL = "eachother"
_FAKE_POLITE_CUES = {"sir", "madam", "lord", "lady", "mister", "mr", "mrs", "majesty"}
_FAKE_REFERENT_TITLES = {"professor", "doctor", "teacher", "elder", "king", "queen", "president", "master"}
_FAKE_AGREEMENT_BY_PRONOUN = {"i": "I", "you": "you", "he": "he", "we": "we", "she": "he", "it": "he", "they": "he"}
_FAKE_IRREGULAR_PAST_LEMMA = {
    "went": "go", "saw": "see", "came": "come", "ate": "eat", "drank": "drink",
    "said": "say", "knew": "know", "slept": "sleep", "gave": "give", "told": "tell",
}
"""Small, deliberately duplicated subset of ``translation/translator.py``'s
own irregular-past table -- this module can't import from ``translation``
(``translator.py`` already imports from ``llm``, so the reverse would be
circular), and this fake only needs enough to keep its own deterministic
heuristic self-consistent, not a shared source of truth."""
_FAKE_WH = {"what", "who", "where", "why", "how", "when", "which"}
_FAKE_AUX = {"do", "does", "did"}
_FAKE_PLURAL_EXCLUDED = {"this", "does", "always", "perhaps", "thanks", "news", "yes"}
_FAKE_ADJECTIVES = {
    "big", "small", "old", "new", "young", "red", "blue", "green", "white", "black", "good", "bad", "long", "tall",
    "beautiful", "ugly", "large", "little", "yellow", "brown",
}
_FAKE_ADVERBS = {"very", "extremely", "quite", "really", "too", "so", "always", "never", "often"}


_FAKE_EVIDENTIAL_WORDS = {
    "reportedly": "reported", "allegedly": "reported", "apparently": "inferred", "evidently": "inferred",
    "visibly": "witnessed",
}
_FAKE_PERFECT_AUX = {"have", "has", "had"}
_FAKE_MODALS = {
    "would": "conditional", "may": "potential", "might": "potential", "can": "potential", "could": "potential",
    "must": "obligative", "should": "obligative",
}
_FAKE_PARTICIPLE_LEMMA = {
    "seen": "see", "gone": "go", "eaten": "eat", "given": "give", "known": "know", "come": "come", "drunk": "drink",
}


def _fake_participle_lemma(token: str) -> str:
    if token in _FAKE_PARTICIPLE_LEMMA:
        return _FAKE_PARTICIPLE_LEMMA[token]
    return _fake_detect_tense_and_lemma(token)[1]


def _fake_aspect_label(desired: str, aspects: list[str]) -> str | None:
    """The closest of this language's own aspect labels to an English
    ``desired`` one (progressive/perfect), else ``None``."""
    if desired in aspects:
        return desired
    fallback = {"progressive": "imperfective", "perfect": "perfective"}.get(desired)
    return fallback if fallback in aspects else None


def _fake_mood_label(desired: str, moods: list[str]) -> str | None:
    if desired in moods:
        return desired
    return "irrealis" if "irrealis" in moods else None


_FAKE_NUMERALS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_FAKE_QUANTIFIERS = {"many", "few", "some", "several", "every", "each", "all", "both"}
_FAKE_SINGULAR_QUANTIFIERS = {"every", "each"}
_FAKE_POSSESSIVE_PRONOUNS = {"my": "I", "your": "you", "his": "he", "her": "he", "our": "we", "their": "they"}
_FAKE_DEMONSTRATIVES = {"this": "this", "that": "that", "these": "this", "those": "that"}
_FAKE_NOT_A_NOUN = (
    _FAKE_COPULAS | _FAKE_AUX | _FAKE_WH | _FAKE_PERFECT_AUX | set(_FAKE_MODALS)
    | {"not", "and", "the", "a", "an", "i", "you", "he", "we", "she", "they", "it"}
)


def _fake_group_noun_phrases(raw_tokens: list[str]) -> tuple[list[str], dict[str, dict]]:
    """Collapses each run of noun-phrase modifiers (a/an, a possessive
    pronoun or ``X's``, this/that/these/those, a numeral) plus the noun they
    belong to into one placeholder token (letters only, like the name
    placeholders), returning the new token list and placeholder -> info.
    A modifier run with no noun after it is left alone ("I see this")."""
    out: list[str] = []
    info: dict[str, dict] = {}
    i = 0
    while i < len(raw_tokens):
        mods: dict = {}
        j = i
        while j < len(raw_tokens):
            word = raw_tokens[j]
            if word == "the":
                mods.setdefault("the", True)
            elif word in ("a", "an"):
                mods["indefinite"] = True
            elif word in _FAKE_POSSESSIVE_PRONOUNS:
                mods["possessor"] = (_FAKE_POSSESSIVE_PRONOUNS[word], True)
            elif word == "own" and "possessor" in mods:
                mods["own"] = True
            elif word.endswith("'s") and len(word) > 3 and word[:-2] not in _FAKE_NOT_A_NOUN:
                mods["possessor"] = (word[:-2], False)
            elif word in _FAKE_DEMONSTRATIVES and j + 1 < len(raw_tokens) and raw_tokens[j + 1] not in _FAKE_NOT_A_NOUN:
                mods["demonstrative"] = _FAKE_DEMONSTRATIVES[word]
                mods["demonstrative_plural"] = word in ("these", "those")
            elif word in _FAKE_NUMERALS and j + 1 < len(raw_tokens):
                mods["numeral"] = word
            elif word in _FAKE_QUANTIFIERS and j + 1 < len(raw_tokens) and raw_tokens[j + 1] not in _FAKE_NOT_A_NOUN:
                mods["quantifier"] = word
            elif word in ("certain", "particular") and mods.get("indefinite"):
                mods["specific"] = True
            elif (
                word in _FAKE_ADJECTIVES and j + 1 < len(raw_tokens)
                and (raw_tokens[j + 1] in _FAKE_ADJECTIVES or raw_tokens[j + 1] not in _FAKE_NOT_A_NOUN)
                and not _fake_is_adverb(raw_tokens[j + 1])
                and raw_tokens[j + 1] not in ("than", "and", "as", "too", "very", "enough", "less", "least")
            ):
                mods.setdefault("adjectives", []).append(word)
            else:
                break
            j += 1
        real_mods = set(mods) - {"the", "specific"}
        if "adjectives" in mods and mods["adjectives"] and j < len(raw_tokens) and raw_tokens[j] in _FAKE_ADJECTIVES:
            real_mods = set()  # a trailing adjective is the noun-less predicate, not part of a phrase
        if real_mods and j < len(raw_tokens) and raw_tokens[j] not in _FAKE_NOT_A_NOUN and not _fake_is_adverb(raw_tokens[j]):
            placeholder = f"zznp{chr(97 + len(info) % 26)}{chr(97 + len(info) // 26)}zz"
            info[placeholder] = {**mods, "noun": raw_tokens[j]}
            out.append(placeholder)
            i = j + 1
        else:
            out.append(raw_tokens[i])
            i += 1
    return out, info


def _fake_merge_reciprocal(tokens: list[str]) -> list[str]:
    """Joins "each other" / "one another" into the single token ``eachother``."""
    out: list[str] = []
    i = 0
    while i < len(tokens):
        if i + 1 < len(tokens) and (tokens[i], tokens[i + 1]) in (("each", "other"), ("one", "another")):
            out.append(_FAKE_RECIPROCAL)
            i += 2
        else:
            out.append(tokens[i])
            i += 1
    return out


def _fake_singular(token: str) -> str | None:
    """The singular of a plausibly plural English noun token, else ``None``.
    A crude suffix heuristic (this fake has no lexicon): ``-ies``, ``-es``
    after s/x/z/ch/sh, else ``-s``, excluding ``-ss``/``-us``/``-is``."""
    if len(token) <= 3 or token in _FAKE_PLURAL_EXCLUDED or not token.endswith("s"):
        return None
    if token.endswith(("ss", "us", "is")):
        return None
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith(("ses", "xes", "zes", "ches", "shes")):
        return token[:-2]
    return token[:-1]


def _fake_is_adverb(token: str) -> bool:
    return token in _FAKE_ADVERBS or (token.endswith("ly") and len(token) > 4)


_FAKE_ROLE_ORDER = {
    "SOV": ("S", "O", "V"), "SVO": ("S", "V", "O"), "VSO": ("V", "S", "O"),
    "VOS": ("V", "O", "S"), "OVS": ("O", "V", "S"), "OSV": ("O", "S", "V"),
}


def _fake_tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z']+", text.lower())


def _fake_detect_tense_and_lemma(token: str) -> tuple[str, str]:
    if token in ("have", "has"):
        return "non_past", "have"
    if token == "had":
        return "past", "have"
    if token in _FAKE_IRREGULAR_PAST_LEMMA:
        return "past", _FAKE_IRREGULAR_PAST_LEMMA[token]
    if token.endswith("ied") and len(token) > 3:
        return "past", token[:-3] + "y"
    if token.endswith("ed") and len(token) > 2:
        return "past", token[:-2]
    return "non_past", token[:-1] if token.endswith("s") and len(token) > 1 else token


def _fake_tense_label(detected: str, tenses: list[str]) -> str | None:
    if detected == "past":
        return "past" if "past" in tenses else None
    if "non_past" in tenses:
        return "non_past"
    if "present" in tenses:
        return "present"
    return None


_FAKE_PLACE_DESCRIPTORS = {
    "lake", "mount", "mt", "mountain", "river", "sea", "ocean", "cape", "fort", "saint", "st",
}
"""A capitalized word immediately followed by another capitalized word
(e.g. "Lake Baikal", "Mount Everest") is, this often enough in practice,
a generic geographic descriptor plus a specific name -- split the two
rather than treating the whole span as one opaque name (a real user-
reported bug: "Lake Baikal" passed through as literal, English-
pronounced text, since nothing anywhere in this codebase ever handled a
multi-word name). Deliberately narrow: a true multi-word name with no
generic part ("New York") has no mechanical way to split and still isn't
handled -- see docs/LIMITATIONS.md."""


def _fake_extract_names(prompt: str) -> tuple[str, dict[str, str]]:
    """Swaps each capitalized word that is neither sentence-initial nor "I"
    (a plausible proper name; a possessive 's is dropped) for a lowercase
    placeholder token, so the rest of the heuristic sees an ordinary
    noun-like token; returns the rewritten prompt and placeholder -> name.
    A recognized place descriptor immediately followed by another
    capitalized word (see ``_FAKE_PLACE_DESCRIPTORS``) is treated as an
    ordinary word instead -- only the word(s) after it become the name."""
    names: dict[str, str] = {}
    first_word = re.search(r"[A-Za-z']+", prompt)
    start_of_first = first_word.start() if first_word else 0

    def swap(match: re.Match) -> str:
        if match.start() == start_of_first or match.group(1) == "I":
            return match.group(0)
        word = match.group(1)
        if word.lower() in _FAKE_PLACE_DESCRIPTORS and re.match(r"\s+[A-Z][a-z]+", prompt[match.end():]):
            return word.lower()
        placeholder = f"zzname{chr(97 + len(names) % 26)}zz"  # letters only: the tokenizer splits on digits
        names[placeholder] = word
        return placeholder

    return re.sub(r"\b([A-Z][a-z]+)(?:'s)?\b", swap, prompt), names


def _fake_single_clause_plan(prompt: str, metadata: dict[str, str]) -> dict:
    """Deterministically reproduces, from ``prompt`` (the raw English
    input) and the grammar-shape ``metadata`` keys ``sentence_planner.
    plan_sentence`` sets, a plan equivalent to what ``translate_to_conlang``
    built by hand before the LLM-drafted planner existed: a copula-bearing
    2-content-word input becomes a predicate-adjective plan, a
    3-content-word input becomes a subject-verb-object plan (case-marking
    the object under nominative-accusative or the subject under
    ergative-absolutive), and anything else becomes one bare content slot
    per word, in order -- including a "the"/"not"/"and" token, which
    resolves correctly at render time via its own already-existing
    lexicon entry regardless of the placeholder ``"noun"`` pos this
    fallback always uses. A recognized "not" is excluded from those two
    length checks and emitted as its own ``"negation"`` slot next to the
    copula/verb instead -- otherwise "the mountain is not high" would
    miscount as a 3-content-word input and be read as a (wrong) transitive
    sentence with "not" as the verb."""
    word_order = metadata.get("word_order", "SVO")
    alignment = metadata.get("alignment", "nominative_accusative")
    tenses = [t for t in metadata.get("tenses", "").split(",") if t]
    has_articles = metadata.get("has_articles") == "true"
    has_overt_copula = metadata.get("has_overt_copula") == "true"
    adjective_after_noun = metadata.get("adjective_after_noun") == "true"

    ends_with = prompt.rstrip()[-1:]
    prompt, name_by_placeholder = _fake_extract_names(prompt)
    raw_tokens = _fake_merge_reciprocal(_fake_tokenize(prompt))
    evidentials = [e for e in metadata.get("evidentials", "").split(",") if e]
    evidential_label: str | None = None
    for position, word in enumerate(raw_tokens):
        if _FAKE_EVIDENTIAL_WORDS.get(word) in evidentials:
            evidential_label = _FAKE_EVIDENTIAL_WORDS[word]
            raw_tokens = raw_tokens[:position] + raw_tokens[position + 1:]
            break
    raw_tokens, np_info = _fake_group_noun_phrases(raw_tokens)
    wh_token = next((t for t in raw_tokens[:1] if t in _FAKE_WH), None)
    mood = "declarative"
    if ends_with == "?":
        mood = "wh_question" if wh_token else "question"
    elif (
        ends_with == "!"
        and raw_tokens
        and raw_tokens[0] not in _FAKE_PRONOUN_TOKENS | _FAKE_COPULAS | _FAKE_ARTICLES | _FAKE_WH
        and raw_tokens[0] not in name_by_placeholder
        and raw_tokens[0] not in np_info
        and not _fake_is_adverb(raw_tokens[0])
    ):
        mood = "imperative"
    used_article = any(t in _FAKE_ARTICLES for t in raw_tokens)
    tokens = [t for t in raw_tokens if t not in _FAKE_ARTICLES]
    if mood in ("question", "wh_question"):
        tokens = [t for t in tokens if t not in _FAKE_AUX]
    if wh_token:
        tokens = tokens[1:]
    aspects = [a for a in metadata.get("aspects", "").split(",") if a]
    has_indefinite_article = metadata.get("has_indefinite_article") == "true"
    has_specific_article = metadata.get("has_specific_article") == "true"
    demonstrative_after_noun = metadata.get("demonstrative_after_noun") == "true"
    has_dual = "dual" in metadata.get("number_labels", "").split(",")
    has_trial = "trial" in metadata.get("number_labels", "").split(",")
    has_collective = "collective" in metadata.get("number_labels", "").split(",")
    voices = [v for v in metadata.get("voices", "").split(",") if v]
    comparative_strategy = metadata.get("comparative_strategy", "particle")
    comparative_case = metadata.get("comparative_case", "")
    comparative_marking = metadata.get("comparative_marking", "word")
    superlative_marking = metadata.get("superlative_marking", "word")
    reflexive_marking = metadata.get("reflexive_marking", "none")
    reciprocal_marking = metadata.get("reciprocal_marking", "none")
    possessive_pronouns = metadata.get("possessive_pronouns", "regular")
    reflexive_possessive = metadata.get("reflexive_possessive", "none")
    verb_number_agreement = metadata.get("verb_number_agreement") == "true"
    verb_politeness = metadata.get("verb_politeness") == "true"
    referent_honorifics = metadata.get("referent_honorifics") == "true"
    clusivity = metadata.get("clusivity") == "true"
    third_person_gender = metadata.get("third_person_gender") == "true"
    honorific_you = metadata.get("honorific_you") == "true"
    existential = metadata.get("existential", "copula")
    possession_clause = metadata.get("possession_clause", "have")
    negative_existential = metadata.get("negative_existential") == "true"
    cases = [c for c in metadata.get("cases", "").split(",") if c]
    postpositional = metadata.get("postpositional") == "true"
    noun_classes = [c for c in metadata.get("noun_classes", "").split(",") if c]
    object_agreement = metadata.get("object_agreement") == "true"
    verb_moods = [m for m in metadata.get("verb_moods", "").split(",") if m]
    perfect_aux = next(
        (
            t for i, t in enumerate(tokens)
            if t in _FAKE_PERFECT_AUX
            and any(u in _FAKE_PARTICIPLE_LEMMA or (u.endswith("ed") and len(u) > 3) for u in tokens[i + 1:])
        ),
        None,
    )
    if perfect_aux:
        tokens = [t for t in tokens if t != perfect_aux]
    do_support = next(
        (t for i, t in enumerate(tokens) if t in ("do", "does", "did") and i + 1 < len(tokens) and tokens[i + 1] == "not"),
        None,
    )
    if do_support:
        tokens = [t for t in tokens if t != do_support]  # "I do not see": the "do" only supports the "not"
    modal = next((t for t in tokens[1:] if t in _FAKE_MODALS), None)
    if modal:
        tokens = [t for t in tokens if t != modal]
    tokens_no_copula = [t for t in tokens if t not in _FAKE_COPULAS]
    has_copula = any(t in _FAKE_COPULAS for t in tokens)
    copula_tok = next((t for t in tokens if t in _FAKE_COPULAS), None)
    negated = "not" in tokens_no_copula
    adverb_tokens = [t for t in tokens_no_copula if _fake_is_adverb(t)]
    content_tokens = [t for t in tokens_no_copula if t != "not" and not _fake_is_adverb(t)]
    adverb_slots = [{"kind": "content", "gloss": t, "pos": "adverb"} for t in adverb_tokens]

    def content_slot(tok: str, pos: str, case: str | None = None) -> dict:
        slot: dict = {"kind": "content", "gloss": tok, "pos": pos}
        if case:
            slot["case"] = case
        return slot

    def base_of(tok: str) -> str:
        if tok in np_info:
            noun = np_info[tok]["noun"]
            return _fake_singular(noun) or noun
        return _fake_singular(tok) or tok

    def build_np(info: dict, case: str | None) -> list[dict]:
        noun_tok = info["noun"]
        singular = _fake_singular(noun_tok)
        noun_slot = content_slot(singular or noun_tok, "noun", case)
        numeral = info.get("numeral")
        if numeral is not None and _FAKE_NUMERALS[numeral] > 1:
            noun_slot["number"] = (
                "dual" if numeral == "two" and has_dual else "trial" if numeral == "three" and has_trial else "plural"
            )
        elif info.get("quantifier") and info["quantifier"] not in _FAKE_SINGULAR_QUANTIFIERS:
            noun_slot["number"] = "collective" if info["quantifier"] == "all" and has_collective else "plural"
        elif singular or info.get("demonstrative_plural"):
            noun_slot["number"] = "plural"
        before: list[dict] = []
        after: list[dict] = []
        if "possessor" in info:
            possessor, is_pronoun = info["possessor"]
            if info.get("own") and reflexive_possessive != "none":
                before.append({"kind": "possessive_pronoun", "gloss": "self"})
            elif is_pronoun and possessive_pronouns != "regular":
                before.append({"kind": "possessive_pronoun", "gloss": possessor})
            else:
                before.append(
                    {"kind": "content", "gloss": possessor, "pos": "pronoun" if is_pronoun else "noun", "possessive": True}
                )
        if "demonstrative" in info:
            demonstrative = {"kind": "demonstrative", "gloss": info["demonstrative"]}
            (after if demonstrative_after_noun else before).append(demonstrative)
        elif "possessor" not in info:
            if info.get("specific") and has_indefinite_article and has_specific_article:
                before.append({"kind": "specific_article"})
            elif info.get("indefinite") and has_indefinite_article:
                before.append({"kind": "indefinite_article"})
            elif has_articles and (info.get("indefinite") or info.get("the") or used_article):
                before.append({"kind": "article"})
        if numeral is not None:
            before.append({"kind": "content", "gloss": numeral, "pos": "numeral"})
        if info.get("quantifier"):
            before.append({"kind": "content", "gloss": info["quantifier"], "pos": "quantifier"})
        adjective_slots = [content_slot(a, "adjective") for a in info.get("adjectives", [])]
        if adjective_after_noun:
            return before + [noun_slot] + adjective_slots + after
        return before + adjective_slots + [noun_slot] + after

    def pronoun_gloss(tok: str) -> str:
        """This language's own gloss for an English pronoun token (the fake
        mirror of ``generation.pronoun_gen.english_pronoun_gloss``)."""
        if tok in ("i", "me"):
            return "i"
        if tok == "you":
            return "you-polite" if honorific_you and any(t in _FAKE_POLITE_CUES for t in raw_tokens) else "you"
        if tok in ("he", "him"):
            return "he"
        if tok in ("she", "it"):
            return tok if third_person_gender else "he"
        if tok in ("we", "us"):
            return "we-exclusive" if clusivity else "we"
        if tok in ("they", "them"):
            return "they"
        return tok

    def noun_phrase(tok: str, case: str | None) -> list[dict]:
        if tok in np_info:
            return build_np(np_info[tok], case)
        if tok in name_by_placeholder:
            name_slot: dict = {"kind": "name", "gloss": name_by_placeholder[tok]}
            if case:
                name_slot["case"] = case
            return [name_slot]
        is_pronoun = tok in _FAKE_PRONOUN_TOKENS or tok in _FAKE_WH
        prefix = [] if is_pronoun or not (used_article and has_articles) else [{"kind": "article"}]
        singular = None if is_pronoun else _fake_singular(tok)
        slot = content_slot(pronoun_gloss(tok) if is_pronoun else (singular or tok), "pronoun" if is_pronoun else "noun", case)
        if singular:
            slot["number"] = "plural"
        return prefix + [slot]

    def is_plural_subject(tok: str) -> bool:
        """A plural pronoun ("we"/"they"), a noun phrase already marked plural
        (a numeral above one, a plural demonstrative, an English "-s" noun) or a
        bare plural noun token -- shared by every clause shape a subject can
        appear in, so a verb's own number agreement is decided the same way
        everywhere."""
        return tok in ("we", "they", "us", "them") or (
            tok in np_info and (
                _FAKE_NUMERALS.get(np_info[tok].get("numeral", ""), 1) > 1
                or np_info[tok].get("demonstrative_plural")
                or _fake_singular(np_info[tok]["noun"]) is not None
            )
        ) or (tok not in _FAKE_PRONOUN_TOKENS and tok not in np_info and _fake_singular(tok) is not None)

    if wh_token in ("what", "who") and len(content_tokens) == 2 and not has_copula:
        content_tokens = content_tokens + [wh_token]  # "what do you see" -> you see WHAT (object)
        wh_token = None

    existence_slots = _fake_existence_slots(
        tokens, word_order, tenses, has_overt_copula, existential, possession_clause, cases, noun_phrase, base_of,
        noun_classes, name_by_placeholder, negative_existential,
    )
    degree_slots = None if existence_slots is not None else _fake_degree_slots(
        tokens, tenses, has_overt_copula, comparative_strategy, comparative_case, comparative_marking,
        superlative_marking, postpositional, word_order, alignment, noun_phrase, base_of, noun_classes,
        name_by_placeholder,
        {
            "equative": metadata.get("equative_marking", "word"), "excessive": metadata.get("excessive_marking", "word"),
            "elative": metadata.get("elative_marking", "word"), "sufficiency": metadata.get("sufficiency_marking", "word"),
        },
        metadata.get("equative_standard_case", ""),
    )
    voice_slots = None if (existence_slots is not None or degree_slots is not None) else _fake_voice_slots(
        tokens, metadata, voices, postpositional, word_order, alignment, tenses, noun_phrase, base_of,
        noun_classes, name_by_placeholder, tokens_no_copula, object_agreement, pronoun_gloss,
    )
    if existence_slots is not None:
        slots = existence_slots
    elif degree_slots is not None:
        slots = degree_slots
    elif voice_slots is not None:
        slots = voice_slots
    elif mood == "imperative" and content_tokens:
        if negated and content_tokens[0] == "do" and len(content_tokens) > 1:
            content_tokens = content_tokens[1:]  # "Do not go!": the "do" is only support for the "not"
        verb_tok, rest = content_tokens[0], content_tokens[1:]
        object_case = "accusative" if alignment == "nominative_accusative" else None
        verb_group = adverb_slots + [{"kind": "content", "gloss": verb_tok, "pos": "verb"}]
        verb_group = verb_group + ([{"kind": "negation"}] if negated else [])
        object_np = noun_phrase(rest[0], object_case) if rest else []
        extra = [content_slot(t, "noun") for t in rest[1:]]
        verb_first = _FAKE_ROLE_ORDER.get(word_order, ("S", "V", "O")).index("V") < _FAKE_ROLE_ORDER.get(
            word_order, ("S", "V", "O")
        ).index("O")
        slots = (verb_group + object_np if verb_first else object_np + verb_group) + extra
    elif has_copula and len(content_tokens) == 2:
        subject_tok, adj_tok = content_tokens
        subject_np = noun_phrase(subject_tok, None)
        adjective_slot = content_slot(adj_tok, "adjective")
        if noun_classes and subject_tok not in _FAKE_PRONOUN_TOKENS and subject_tok not in name_by_placeholder:
            adjective_slot["agrees_with"] = base_of(subject_tok)
        adjective_group = adverb_slots + [adjective_slot]
        copula_group: list[dict] = []
        if has_overt_copula:
            detected_tense = "past" if copula_tok in _FAKE_PAST_COPULAS else "non_past"
            tense_label = _fake_tense_label(detected_tense, tenses)
            copula_slot = {"kind": "copula", "agreement": _FAKE_AGREEMENT_BY_PRONOUN.get(subject_tok, "default")}
            if noun_classes and subject_tok not in _FAKE_PRONOUN_TOKENS and subject_tok not in name_by_placeholder:
                copula_slot["subject_gloss"] = base_of(subject_tok)
            if tense_label:
                copula_slot["tense"] = tense_label
            if evidential_label:
                copula_slot["evidential"] = evidential_label
            copula_group = [copula_slot]
        if negated:
            copula_group = copula_group + [{"kind": "negation"}]
        slots = (subject_np + copula_group + adjective_group) if adjective_after_noun else (
            adjective_group + copula_group + subject_np
        )
    elif len(content_tokens) == 2:
        # a subject and an intransitive verb ("I sleep.", "The dogs sleep.") -- the narrower voice
        # shapes above (existentials, comparisons, the closed middle/antipassive verb lists) claim
        # this same two-content-word shape first when they apply; this is the plain, general case,
        # including the number agreement a plural subject (pronoun or noun) gives its verb.
        subject_tok, verb_tok = content_tokens
        order = _FAKE_ROLE_ORDER.get(word_order, ("S", "V", "O"))
        verb_first = order.index("V") < order.index("S")
        detected_tense, lemma = _fake_detect_tense_and_lemma(verb_tok)
        aspect_label = None
        verb_mood_label = None
        if perfect_aux:
            lemma = _fake_participle_lemma(verb_tok)
            detected_tense = "past" if perfect_aux == "had" else "non_past"
            aspect_label = _fake_aspect_label("perfect", aspects)
        if do_support == "did":
            detected_tense = "past"
        if modal:
            verb_mood_label = _fake_mood_label(_FAKE_MODALS[modal], verb_moods)
            detected_tense = "non_past"
        tense_label = _fake_tense_label(detected_tense, tenses)
        subject_np = noun_phrase(subject_tok, None)
        verb_slot = {
            "kind": "content", "gloss": lemma, "pos": "verb",
            "agreement": _FAKE_AGREEMENT_BY_PRONOUN.get(subject_tok, "default"),
        }
        if verb_number_agreement and is_plural_subject(subject_tok):
            verb_slot["subject_number"] = "plural"
        referent_honorific = referent_honorifics and base_of(subject_tok) in _FAKE_REFERENT_TITLES
        if verb_politeness and (
            (subject_tok == "you" and pronoun_gloss("you") == "you-polite") or referent_honorific
        ):
            verb_slot["polite"] = True
        if tense_label:
            verb_slot["tense"] = tense_label
        if evidential_label:
            verb_slot["evidential"] = evidential_label
        if noun_classes and subject_tok not in _FAKE_PRONOUN_TOKENS and subject_tok not in name_by_placeholder:
            verb_slot["subject_gloss"] = base_of(subject_tok)
        if aspect_label:
            verb_slot["aspect"] = aspect_label
        if verb_mood_label:
            verb_slot["verb_mood"] = verb_mood_label
        verb_group = adverb_slots + [verb_slot] + ([{"kind": "negation"}] if negated else [])
        slots = (verb_group + subject_np) if verb_first else (subject_np + verb_group)
    elif len(content_tokens) == 3:
        subject_tok, verb_tok, obj_tok = content_tokens
        detected_tense, verb_lemma = _fake_detect_tense_and_lemma(verb_tok)
        aspect_label: str | None = None
        verb_mood_label: str | None = None
        if perfect_aux:
            verb_lemma = _fake_participle_lemma(verb_tok)
            detected_tense = "past" if perfect_aux == "had" else "non_past"
            aspect_label = _fake_aspect_label("perfect", aspects)
        elif has_copula and verb_tok.endswith("ing") and len(verb_tok) > 5:
            verb_lemma = verb_tok[:-3]
            detected_tense = "past" if copula_tok in _FAKE_PAST_COPULAS else "non_past"
            aspect_label = _fake_aspect_label("progressive", aspects)
        if do_support == "did":
            detected_tense = "past"
        if modal:
            verb_mood_label = _fake_mood_label(_FAKE_MODALS[modal], verb_moods)
            detected_tense = "non_past"
        tense_label = _fake_tense_label(detected_tense, tenses)
        subject_case = "ergative" if alignment == "ergative_absolutive" else None
        object_case = "accusative" if alignment == "nominative_accusative" else None
        subject_np = noun_phrase(subject_tok, subject_case)
        reflexive_person = _FAKE_REFLEXIVES.get(obj_tok)
        is_reciprocal = obj_tok == _FAKE_RECIPROCAL
        reflexive_voice: str | None = None
        if reflexive_person is not None or is_reciprocal:
            marking = reciprocal_marking if is_reciprocal else reflexive_marking
            word = "each-other" if is_reciprocal else "self"
            if marking == "affix":
                reflexive_voice = "reciprocal" if is_reciprocal else "reflexive"
                object_np = []
            elif marking == "word":
                object_np = [{"kind": "content", "gloss": word, "pos": "pronoun", **({"case": object_case} if object_case else {})}]
            else:
                stand_in = subject_tok if is_reciprocal or subject_tok in _FAKE_PRONOUN_TOKENS else reflexive_person
                object_np = noun_phrase(stand_in if stand_in in _FAKE_PRONOUN_TOKENS else "they", object_case)
        else:
            object_np = noun_phrase(obj_tok, object_case)
        verb_slot = {
            "kind": "content", "gloss": verb_lemma, "pos": "verb",
            "agreement": _FAKE_AGREEMENT_BY_PRONOUN.get(subject_tok, "default"),
        }
        if reflexive_voice:
            verb_slot["voice"] = reflexive_voice
        if verb_number_agreement and is_plural_subject(subject_tok):
            verb_slot["subject_number"] = "plural"
        referent_honorific = referent_honorifics and base_of(subject_tok) in _FAKE_REFERENT_TITLES
        if verb_politeness and (
            (subject_tok == "you" and pronoun_gloss("you") == "you-polite") or referent_honorific
        ):
            verb_slot["polite"] = True
        if tense_label:
            verb_slot["tense"] = tense_label
        if evidential_label:
            verb_slot["evidential"] = evidential_label
        if noun_classes and subject_tok not in _FAKE_PRONOUN_TOKENS and subject_tok not in name_by_placeholder:
            verb_slot["subject_gloss"] = base_of(subject_tok)
        if object_agreement and (reflexive_person is not None or is_reciprocal):
            if reflexive_voice is None:
                verb_slot["object_gloss"] = "each-other" if is_reciprocal and reciprocal_marking == "word" else (
                    "self" if reflexive_marking == "word" and not is_reciprocal else pronoun_gloss(subject_tok)
                )
        elif object_agreement:
            verb_slot["object_gloss"] = (
                pronoun_gloss(obj_tok) if obj_tok in _FAKE_PRONOUN_TOKENS else base_of(obj_tok)
            )
        if aspect_label:
            verb_slot["aspect"] = aspect_label
        if verb_mood_label:
            verb_slot["verb_mood"] = verb_mood_label
        verb_group = adverb_slots + [verb_slot] + ([{"kind": "negation"}] if negated else [])
        role_slots = {"S": subject_np, "V": verb_group, "O": object_np}
        slots = [s for role in _FAKE_ROLE_ORDER.get(word_order, ("S", "V", "O")) for s in role_slots[role]]
    else:
        slots = []
        for t in tokens_no_copula:
            if t == "not":
                slots.append({"kind": "negation"})
            elif t in name_by_placeholder:
                slots.append({"kind": "name", "gloss": name_by_placeholder[t]})
            elif t in np_info:
                # A grouped noun phrase (adjective/possessor/article/demonstrative
                # + its noun, collapsed to one opaque placeholder by
                # `_fake_group_noun_phrases`) -- resolved back into its real
                # modifier/noun slots via `noun_phrase`, the same helper every
                # other clause shape already uses. Without this check, the raw
                # placeholder string (e.g. "zznpaazz") leaked through as the
                # slot's own gloss -- a real user-reported bug, since this is
                # the only branch of `_fake_single_clause_plan` that forgot it
                # (the 2/3-content-word branches above all go through
                # `noun_phrase`/`object_np` already).
                slots.extend(noun_phrase(t, None))
            else:
                slots.append(content_slot(t, "adverb" if _fake_is_adverb(t) else "noun"))

    if wh_token:
        slots = [{"kind": "content", "gloss": wh_token, "pos": "adverb" if wh_token != "which" else "pronoun"}] + slots
    return {"mood": mood, "slots": slots}


_FAKE_OBJECT_CONTROL = {"tell", "tells", "told", "ask", "asks", "asked", "order", "orders", "ordered", "help", "helps", "helped", "let"}
_FAKE_OBJECT_PRONOUNS = {"me", "him", "her", "us", "them", "you"}
_FAKE_CONTROLLER_PERSON = {
    "i": "I", "me": "I", "you": "you", "he": "he", "him": "he", "she": "he", "her": "he", "we": "we", "us": "we",
    "they": "he", "them": "he", "it": "he",
}
_FAKE_INFINITIVE_VERBS = {
    "want", "wants", "wanted", "like", "likes", "liked", "try", "tries", "tried", "begin", "begins", "began",
    "start", "starts", "started", "need", "needs", "needed", "hope", "hopes", "hoped", "decide", "decides",
    "decided", "love", "loves", "loved",
    # subject-to-subject raising verbs: mechanically the same same-subject infinitive as the verbs above (the
    # matrix verb takes no argument of its own; its subject really belongs to the infinitive) -- "he SEEMS to like her".
    "seem", "seems", "seemed", "appear", "appears", "appeared", "happen", "happens", "happened",
    "tend", "tends", "tended",
}
_FAKE_PASSIVE_CONTROL_PARTICIPLES = {
    "believed": "believe", "thought": "think", "expected": "expect", "known": "know", "said": "say",
    "reported": "report",
}
"""A copula plus one of these (``"is believed"``) before "to VERB" passivizes an object-control verb: the matrix
subject is really the infinitive's own subject, raised through the passive (see ``_fake_infinitive_plan``)."""
_FAKE_SUBORDINATORS = {"that", "because", "if", "when", "although", "while"}
_FAKE_SUBORDINATOR_ROLE = {"that": "complement"}
_FAKE_PP_RELATIVE_PREPS = {"in", "at", "with", "about", "to", "on", "for", "from"}
"""Prepositions a "the house IN WHICH I live"-style relative clause can pied-pipe."""


def _fake_existence_slots(
    tokens, word_order, tenses, has_overt_copula, existential, possession_clause, cases, noun_phrase, base_of,
    noun_classes, name_by_placeholder, negative_existential=False,
):
    """Plans an existential ("there is/are/was X", "is there X?", "there is no
    X") and, in a ``dative_be`` language, a possession clause ("I have X"),
    per the language's own ``existential``/``possession_clause`` strategies;
    ``None`` when the tokens are neither (a ``have`` language's "I have X"
    is left to the ordinary transitive shape)."""
    order = _FAKE_ROLE_ORDER.get(word_order, ("S", "V", "O"))
    verb_first = order.index("V") < order.index("S")
    negated = "not" in tokens or "no" in tokens
    skip = _FAKE_COPULAS | {"there", "not", "no"}

    def be_slots(tense_label: str | None, x_tok: str) -> list[dict]:
        if negated and negative_existential:
            # A dedicated negative-existential word (Russian "net", Turkish
            # "yok") replaces the whole predicate -- no separate copula/verb
            # "exist" and no ordinary negation particle beside it.
            return [{"kind": "content", "gloss": "not-exist", "pos": "preposition"}]
        agrees = {"agreement": "default"}
        if noun_classes and x_tok not in _FAKE_PRONOUN_TOKENS and x_tok not in name_by_placeholder:
            agrees["subject_gloss"] = base_of(x_tok)
        if existential == "verb":
            slot = {"kind": "content", "gloss": "exist", "pos": "verb", **agrees}
        elif has_overt_copula:
            slot = {"kind": "copula", **agrees}
        else:
            slot = None
        out: list[dict] = []
        if slot is not None:
            if tense_label:
                slot["tense"] = tense_label
            out.append(slot)
        if negated:
            out.append({"kind": "negation"})
        return out

    def arrange(np_slots: list[dict], be: list[dict]) -> list[dict]:
        return be + np_slots if verb_first else np_slots + be

    if "there" in tokens and any(t in _FAKE_COPULAS for t in tokens):
        x_tok = next((t for t in tokens if t not in skip), None)
        if x_tok is None:
            return None
        copula = next(t for t in tokens if t in _FAKE_COPULAS)
        tense_label = _fake_tense_label("past" if copula in _FAKE_PAST_COPULAS else "non_past", tenses)
        return arrange(noun_phrase(x_tok, None), be_slots(tense_label, x_tok))

    have_index = next((i for i, t in enumerate(tokens) if t in ("have", "has", "had")), None)
    possessed_index = (
        next((j for j in range(have_index + 1, len(tokens)) if tokens[j] not in ("no", "not")), None)
        if have_index is not None else None
    )
    if possession_clause == "dative_be" and have_index is not None and 0 < have_index and possessed_index is not None:
        possessor_tok, possessed_tok = tokens[have_index - 1], tokens[possessed_index]
        tense_label = _fake_tense_label("past" if tokens[have_index] == "had" else "non_past", tenses)
        if "dative" in cases:
            possessor = noun_phrase(possessor_tok, "dative")
        else:
            possessor = noun_phrase(possessor_tok, None)
            for slot in reversed(possessor):
                if slot.get("kind") in ("content", "name") and slot.get("pos") != "numeral":
                    slot["possessive"] = True
                    break
        return possessor + arrange(noun_phrase(possessed_tok, None), be_slots(tense_label, possessed_tok))
    return None


_FAKE_KNOWN_ADJECTIVES = {
    "green", "red", "blue", "white", "black", "yellow", "brown", "grey", "sweet", "bitter", "sour", "soft", "hard",
    "smooth", "rough", "sharp", "dull", "bright", "dry", "wet", "full", "empty", "safe", "dangerous", "easy",
    "difficult", "kind", "cruel", "proud", "humble", "smart", "foolish", "sick", "healthy", "tired", "hungry",
    "angry", "calm", "sad", "fresh", "ripe", "early", "late", "close", "steep", "flat", "round", "sacred",
    "big", "small", "high", "low", "long", "short", "old", "new", "young", "good", "bad", "large", "tall", "wide",
    "narrow", "strong", "weak", "fast", "slow", "hot", "cold", "heavy", "light", "beautiful", "happy", "dark", "deep",
    "thick", "thin", "rich", "poor", "clean", "dirty", "near", "far", "wise", "brave", "quiet", "loud",
    "wild", "tame", "gentle", "fierce", "broad", "sturdy", "fragile", "plain", "ancient", "modern", "noisy",
    "silent", "pure", "bold", "wicked", "gloomy", "cheerful", "stale", "shallow", "solid", "loose", "tight",
    "straight", "crooked", "salty", "spicy", "mild", "cowardly", "generous", "greedy", "lazy", "diligent",
    "polite", "rude", "friendly", "hostile",
}
_FAKE_IRREGULAR_DEGREES = {
    "better": ("good", "comparative"), "best": ("good", "superlative"),
    "worse": ("bad", "comparative"), "worst": ("bad", "superlative"),
}
_FAKE_NOT_A_SUPERLATIVE = {
    "forest", "west", "rest", "test", "east", "nest", "chest", "guest", "harvest", "interest", "request",
}


def _fake_degree_of(token: str) -> tuple[str, str] | None:
    """``(adjective lemma, "comparative"|"superlative")`` for an English
    ``-er``/``-est`` (or irregular) adjective form, else ``None``. A crude
    suffix heuristic anchored on a small known-adjective list, since nouns
    like "river" and "forest" end the same way."""
    if token in _FAKE_IRREGULAR_DEGREES:
        return _FAKE_IRREGULAR_DEGREES[token]
    for suffix, degree in (("est", "superlative"), ("er", "comparative")):
        if token.endswith(suffix) and len(token) > len(suffix) + 2 and token not in _FAKE_NOT_A_SUPERLATIVE:
            stem = token[: -len(suffix)]
            candidates = [stem, stem + "e"]
            if stem.endswith("i"):
                candidates.append(stem[:-1] + "y")
            if len(stem) >= 3 and stem[-1] == stem[-2]:
                candidates.append(stem[:-1])
            lemma = next((c for c in candidates if c in _FAKE_KNOWN_ADJECTIVES), None)
            if lemma is not None:
                return lemma, degree
    return None


_FAKE_DEGREE_WORD_GLOSS = {
    "comparative": "more", "superlative": "most", "equative": "as", "excessive": "too", "elative": "very",
    "comparative_negative": "less", "superlative_negative": "least", "sufficiency": "enough",
}


def _fake_degree_slots(
    tokens, tenses, has_overt_copula, strategy, comparative_case, comparative_marking, superlative_marking,
    postpositional, word_order, alignment, noun_phrase, base_of, noun_classes, name_by_placeholder, marks=None,
    equative_standard_case="",
):
    """Plans "X is bigger/more beautiful than Y", "X is more beautiful" and
    "X is the biggest/most beautiful" as ``subject + copula + adjective
    [+ standard]``, marking the degree and the standard per the language's own
    strategy; ``None`` when the tokens are not of that shape. Also plans the
    negative degree ("less big [than Y]", "least big") and sufficiency ("big
    enough" -- the one degree word that follows the adjective, not precedes
    it)."""
    copula_index = next((i for i, t in enumerate(tokens) if t in _FAKE_COPULAS), None)
    if copula_index is None or copula_index != 1 or len(tokens) < 3:
        return None
    subject_tok = tokens[0]
    rest = tokens[2:]
    negated = "not" in rest
    rest = [t for t in rest if t != "not"]
    if not rest:
        return None
    marks = marks or {}
    standard_tok = None
    degree = None
    lemma = None
    if len(rest) == 4 and rest[0] == "as" and rest[2] == "as" and rest[1] in _FAKE_KNOWN_ADJECTIVES:
        lemma, degree, standard_tok = rest[1], "equative", rest[3]
    elif len(rest) == 2 and rest[0] == "too" and rest[1] in _FAKE_KNOWN_ADJECTIVES:
        lemma, degree = rest[1], "excessive"
    elif len(rest) == 2 and rest[1] == "enough" and rest[0] in _FAKE_KNOWN_ADJECTIVES:
        lemma, degree = rest[0], "sufficiency"
    elif (
        len(rest) == 2 and rest[0] == "very" and rest[1] in _FAKE_KNOWN_ADJECTIVES and marks.get("elative") == "affix"
    ):
        lemma, degree = rest[1], "elative"
    elif "than" in rest:
        than_index = rest.index("than")
        if than_index == 0 or than_index + 1 >= len(rest):
            return None
        standard_tok = rest[than_index + 1]
        head = rest[:than_index]
        found = _fake_degree_of(head[-1])
        if len(head) >= 2 and head[-2] == "more":
            lemma, degree = head[-1], "comparative"
        elif len(head) >= 2 and head[-2] == "less":
            lemma, degree = head[-1], "comparative_negative"
        elif found is not None and found[1] == "comparative":
            lemma, degree = found
        else:
            return None
    elif len(rest) == 2 and rest[0] in ("more", "most", "less", "least"):
        degree = {
            "more": "comparative", "most": "superlative", "less": "comparative_negative", "least": "superlative_negative",
        }[rest[0]]
        lemma = rest[1]
    elif len(rest) == 1 and _fake_degree_of(rest[0]):
        lemma, degree = _fake_degree_of(rest[0])
    else:
        return None
    order = _FAKE_ROLE_ORDER.get(word_order, ("S", "V", "O"))
    tense_label = _fake_tense_label("past" if tokens[copula_index] in _FAKE_PAST_COPULAS else "non_past", tenses)
    marking = {
        "comparative": comparative_marking, "superlative": superlative_marking,
        "equative": marks.get("equative", "word"), "excessive": marks.get("excessive", "word"),
        "elative": marks.get("elative", "affix"),
        "comparative_negative": comparative_marking, "superlative_negative": superlative_marking,
        "sufficiency": marks.get("sufficiency", "word"),
    }[degree]
    if degree == "equative" and strategy == "exceed":
        strategy = "particle"  # no verb "exceed" for an equality
    subject_np = noun_phrase(subject_tok, None)
    subject_is_noun = subject_tok not in _FAKE_PRONOUN_TOKENS and subject_tok not in name_by_placeholder

    adjective: dict = {"kind": "content", "gloss": lemma, "pos": "adjective"}
    if noun_classes and subject_is_noun:
        adjective["agrees_with"] = base_of(subject_tok)
    adjective_group: list[dict] = []
    if marking == "affix":
        adjective["degree"] = degree
        adjective_group.append(adjective)
    else:
        word_slot = {"kind": "content", "pos": "adverb", "gloss": _FAKE_DEGREE_WORD_GLOSS[degree]}
        if degree == "sufficiency":
            adjective_group.extend([adjective, word_slot])  # "big enough": the word follows
        else:
            adjective_group.extend([word_slot, adjective])

    def agrees(slot: dict) -> dict:
        slot["agreement"] = "default"
        if noun_classes and subject_is_noun:
            slot["subject_gloss"] = base_of(subject_tok)
        if tense_label:
            slot["tense"] = tense_label
        return slot

    be: list[dict] = []
    if (strategy != "exceed" or standard_tok is None) and has_overt_copula:
        be.append(agrees({"kind": "copula"}))
    if negated:
        be.append({"kind": "negation"})

    standard_phrase: list[dict] = []
    if standard_tok is not None:
        object_case = "accusative" if alignment == "nominative_accusative" else None
        # An equative's own standard case is rolled independently of the
        # comparative's; an older saved language (or one whose roll didn't
        # switch it) falls back to sharing the comparative's, the original
        # behavior.
        effective_case = (
            (equative_standard_case or (comparative_case if strategy == "case" else None))
            if degree == "equative"
            else (comparative_case if strategy == "case" else None)
        )
        if effective_case:
            standard_phrase = noun_phrase(standard_tok, effective_case)
        elif strategy == "exceed":
            verb = [agrees({"kind": "content", "gloss": "exceed", "pos": "verb"})]
            standard_np = noun_phrase(standard_tok, object_case)
            standard_phrase = standard_np + verb if order.index("O") < order.index("V") else verb + standard_np
        else:
            than = [{"kind": "content", "gloss": "as" if degree == "equative" else "than", "pos": "preposition"}]
            standard_np = noun_phrase(standard_tok, None)
            standard_phrase = standard_np + than if postpositional else than + standard_np
    return subject_np + be + adjective_group + standard_phrase


_FAKE_MAKE = {"make", "makes", "made"}
_FAKE_ANTIPASSIVE_VERBS = {
    "eat", "eats", "ate", "drink", "drinks", "drank", "read", "reads", "hunt", "hunts", "hunted", "cook", "cooks",
    "cooked", "sing", "sings", "sang", "write", "writes", "wrote", "bake", "bakes", "baked", "wash", "washes",
    "washed", "sew", "sews", "sewed", "clean", "cleans", "cleaned", "build", "builds", "built", "paint", "paints",
    "painted", "weave", "weaves", "wove",
}
_FAKE_MIDDLE_VERBS = {
    "open", "opens", "opened", "close", "closes", "closed", "break", "breaks", "broke", "melt", "melts", "melted",
    "burn", "burns", "burned", "boil", "boils", "boiled", "freeze", "freezes", "froze", "crack", "cracks",
    "cracked", "tear", "tears", "tore", "bend", "bends", "bent", "split", "splits", "sink", "sinks", "sank",
}


def _fake_voice_slots(
    tokens, metadata, voices, postpositional, word_order, alignment, tenses, noun_phrase, base_of,
    noun_classes, name_by_placeholder, tokens_no_copula, object_agreement=False, pronoun_gloss=None,
):
    """Plans a passive ("the river is seen by the dog") or a causative ("I made
    the dog see the river") when the tokens have that shape; ``None``
    otherwise. A passive whose language lacks the passive voice is reworded
    as an active clause (agent as subject, or "they" when no agent); a
    causative in a language without one is left to the ordinary shapes."""
    order = _FAKE_ROLE_ORDER.get(word_order, ("S", "V", "O"))
    object_case = "accusative" if alignment == "nominative_accusative" else None
    subject_case = "ergative" if alignment == "ergative_absolutive" else None

    def verb_slot(lemma: str, tense_label: str | None, subject_tok: str | None, voice: str | None) -> dict:
        slot: dict = {"kind": "content", "gloss": lemma, "pos": "verb", "agreement": "default"}
        if subject_tok is not None:
            slot["agreement"] = _FAKE_AGREEMENT_BY_PRONOUN.get(subject_tok, "default")
            if noun_classes and subject_tok not in _FAKE_PRONOUN_TOKENS and subject_tok not in name_by_placeholder:
                slot["subject_gloss"] = base_of(subject_tok)
        if tense_label:
            slot["tense"] = tense_label
        if voice:
            slot["voice"] = voice
        return slot

    verb_first = order.index("V") < order.index("S")
    if len(tokens) == 2 and not any(t in _FAKE_COPULAS for t in tokens):
        subject_tok, verb_tok = tokens
        voice = None
        # "someone", not English impersonal "one" -- "one" is also a numeral,
        # and _fake_group_noun_phrases always swallows "one <word>" into a
        # numeral-quantified noun phrase before this function ever runs,
        # regardless of whether the second word is really a noun or a verb.
        if subject_tok == "someone" and "impersonal" in voices:
            voice = "impersonal"
        elif verb_tok in _FAKE_ANTIPASSIVE_VERBS and "antipassive" in voices:
            voice = "antipassive"
        elif verb_tok in _FAKE_MIDDLE_VERBS and "middle" in voices:
            voice = "middle"
        if voice is not None:
            detected, lemma = _fake_detect_tense_and_lemma(verb_tok)
            tense_label = _fake_tense_label(detected, tenses)
            if voice == "impersonal":
                # A real impersonal construction has no subject at all --
                # "someone" here is only the English placeholder that signals it.
                return [verb_slot(lemma, tense_label, None, voice)]
            verb = [verb_slot(lemma, tense_label, subject_tok, voice)]
            subject_np = noun_phrase(subject_tok, None)
            return verb + subject_np if verb_first else subject_np + verb
    if len(tokens) == 4 and tokens[2] == "for" and "applicative" in voices:
        subject_tok, verb_tok, _, beneficiary = tokens
        detected, lemma = _fake_detect_tense_and_lemma(verb_tok)
        applicative_verb = verb_slot(lemma, _fake_tense_label(detected, tenses), subject_tok, "applicative")
        if object_agreement and pronoun_gloss is not None:
            # The beneficiary is promoted to a full direct object by the
            # applicative -- it triggers the verb's own object agreement
            # exactly like an ordinary object would (a real valency change,
            # not just a bare suffix on the verb).
            applicative_verb["object_gloss"] = (
                pronoun_gloss(beneficiary) if beneficiary in _FAKE_PRONOUN_TOKENS else base_of(beneficiary)
            )
        roles = {
            "S": noun_phrase(subject_tok, subject_case),
            "V": [applicative_verb],
            "O": noun_phrase(beneficiary, object_case),
        }
        return [x for role in order for x in roles[role]]
    copula_index = next((i for i, t in enumerate(tokens) if t in _FAKE_COPULAS), None)
    if copula_index is not None and 0 < copula_index and copula_index + 1 < len(tokens):
        participle = tokens[copula_index + 1]
        by_index = next((i for i, t in enumerate(tokens) if t == "by" and i > copula_index + 1), None)
        is_participle = participle in _FAKE_PARTICIPLE_LEMMA or (participle.endswith("ed") and len(participle) > 3)
        irregular = participle in _FAKE_PARTICIPLE_LEMMA
        if is_participle and (irregular or by_index is not None):
            patient_tok = tokens[copula_index - 1]
            agent_tok = tokens[by_index + 1] if by_index is not None and by_index + 1 < len(tokens) else None
            lemma = _fake_participle_lemma(participle)
            tense_label = _fake_tense_label("past" if tokens[copula_index] in _FAKE_PAST_COPULAS else "non_past", tenses)
            if "passive" in voices:
                agent_phrase: list[dict] = []
                if agent_tok is not None:
                    by_slot = {"kind": "content", "gloss": "by", "pos": "preposition"}
                    agent_np = noun_phrase(agent_tok, None)
                    agent_phrase = agent_np + [by_slot] if postpositional else [by_slot] + agent_np
                patient_np = noun_phrase(patient_tok, None)
                verb = [verb_slot(lemma, tense_label, patient_tok, "passive")]
                if order.index("V") == 2:  # verb-final: the agent phrase sits before the verb
                    return patient_np + agent_phrase + verb
                first = ("V", "S") if order.index("V") < order.index("S") else ("S", "V")
                return [x for role in first for x in (patient_np if role == "S" else verb)] + agent_phrase
            # no passive voice: reword as an active clause
            if agent_tok is not None:
                subject_np = noun_phrase(agent_tok, subject_case)
                subject_key = agent_tok
            else:
                subject_np = [{"kind": "content", "gloss": "they", "pos": "pronoun"}]
                subject_key = "they"
            roles = {
                "S": subject_np,
                "V": [verb_slot(lemma, tense_label, subject_key, None)],
                "O": noun_phrase(patient_tok, object_case),
            }
            return [x for role in order for x in roles[role]]
    make_index = next((i for i, t in enumerate(tokens) if t in _FAKE_MAKE), None)
    if make_index is not None and "causative" in voices and 0 < make_index and make_index + 2 < len(tokens):
        subject_tok, causee_tok, verb_tok = tokens[make_index - 1], tokens[make_index + 1], tokens[make_index + 2]
        rest = tokens[make_index + 3:]
        tense_label = _fake_tense_label("past" if tokens[make_index] == "made" else "non_past", tenses)
        roles = {
            "S": noun_phrase(subject_tok, subject_case),
            "V": [verb_slot(_fake_detect_tense_and_lemma(verb_tok)[1], tense_label, subject_tok, "causative")],
            "O": noun_phrase(causee_tok, object_case),
        }
        ordered = [x for role in order for x in roles[role]]
        extra = [x for tok in rest[:1] for x in noun_phrase(tok, None)]
        return ordered + extra
    return None


def _fake_drop_subject(clause_slots: list[dict]) -> None:
    """Removes the stand-in subject "he" a clause was planned with."""
    subject = next((i for i, slot in enumerate(clause_slots) if slot.get("gloss") == "he"), None)
    if subject is not None:
        del clause_slots[subject]


def _fake_ensure_verb(clause_slots: list[dict], tenses: list[str]) -> None:
    """A clause of one or two words falls back to bare noun slots; makes the
    first of them the verb."""
    if any(slot.get("pos") == "verb" for slot in clause_slots):
        return
    for slot in reversed(clause_slots):
        if slot.get("kind") == "content" and slot.get("pos") == "noun":
            detected, lemma = _fake_detect_tense_and_lemma(slot["gloss"])
            slot.update({"pos": "verb", "gloss": lemma, "agreement": "default"})
            tense_label = _fake_tense_label(detected, tenses)
            if tense_label:
                slot["tense"] = tense_label
            return


_FAKE_RELATIVE_ORDER = ("subject", "object", "oblique", "possessor")
_FAKE_SUBJECT_PRONOUNS = {"i", "you", "we", "they", "he", "she", "it"}


def _fake_relative_plan(prompt: str, match, metadata: dict[str, str], prep: str | None = None, prep_match=None) -> dict:
    """"I see the dog who sleeps" / "the dog which I see" / "the man whose dog
    sleeps" / "the house in which I live": the main clause, then a relative
    clause slot right after its last noun, with its ``rel_function`` (subject,
    object, possessor, or ``oblique_pp`` for a prepositional argument -- see
    ``prep``) and the relativized position left as a gap -- or filled by a
    resumptive pronoun where the language needs one. ``prep``/``prep_match``
    (set only for the pied-piped "in which" spelling; the stranded "which ...
    live in" spelling is built directly, not detected from free text) mark the
    split point at the preposition instead of the relative word, and the
    preposition is appended to the embedded clause as an ordinary trailing
    "preposition" slot -- the renderer pulls it back out and fronts it with
    the relative word in a language that pied-pipes, or leaves it there,
    stranded after the verb that governs it, in one that doesn't."""
    terminal = prompt.rstrip()[-1:] if prompt.rstrip()[-1:] in ".!?" else ""
    split = prep_match if prep else match
    main = prompt[: split.start()].rstrip(" ,;") + terminal
    rest = prompt[match.end():].strip().rstrip(".!?").strip()
    word = match.group(0).lower()
    main_plan = _fake_single_clause_plan(main, metadata)
    strategy = metadata.get("relativization", "pronoun")
    reach = metadata.get("relativization_reach", "possessor")
    first_rest = rest.split()[0].lower() if rest.split() else ""
    tenses = [t for t in metadata.get("tenses", "").split(",") if t]
    if prep:
        function = "oblique_pp"
        clause_slots = _fake_single_clause_plan(rest, metadata)["slots"]
    elif word == "whose":
        function = "possessor"
        clause_slots = _fake_single_clause_plan("The " + rest, metadata)["slots"]
    elif word == "whom" or first_rest in _FAKE_SUBJECT_PRONOUNS:
        function = "object"
        clause_slots = _fake_single_clause_plan(rest, metadata)["slots"]
    else:
        function = "subject"
        clause_slots = _fake_single_clause_plan("He " + rest, metadata)["slots"]
        if strategy != "resumptive":
            _fake_drop_subject(clause_slots)
    _fake_ensure_verb(clause_slots, tenses)
    plain_reaches = (
        strategy in ("gap", "particle") and function in _FAKE_RELATIVE_ORDER
        and _FAKE_RELATIVE_ORDER.index(function) > _FAKE_RELATIVE_ORDER.index(reach)
    )
    if prep:
        clause_slots.append({"kind": "content", "gloss": prep, "pos": "preposition"})
    elif strategy == "resumptive" or plain_reaches:
        if function == "object":
            clause_slots.append({"kind": "content", "gloss": "he", "pos": "pronoun", "case": "accusative"})
        elif function == "possessor":
            noun_index = next((i for i, slot in enumerate(clause_slots) if slot.get("pos") == "noun"), 0)
            clause_slots.insert(noun_index, {"kind": "content", "gloss": "he", "pos": "pronoun", "possessive": True})
    clause = {
        "kind": "clause", "gloss": "who" if word == "whom" else word, "role": "relative", "rel_function": function,
        "clause": {"slots": clause_slots},
    }
    if prep:
        clause["oblique_prep"] = prep
    slots = list(main_plan["slots"])
    last_noun = max((i for i, slot in enumerate(slots) if slot.get("kind") == "content" and slot.get("pos") == "noun"), default=None)
    slots.insert(len(slots) if last_noun is None else last_noun + 1, clause)
    return {"mood": main_plan["mood"], "slots": slots}


def _fake_stacked_relative_plan(prompt: str, metadata: dict[str, str]) -> dict | None:
    """"the dog that barks that bites": two subject relative clauses stacked
    on the same head noun (a common, unambiguous surface shape for stacking;
    the fake has no way to tell from raw text which noun a *third* relative
    would stack on, so only exactly two are detected). ``None`` when the
    prompt doesn't have this shape."""
    match = re.search(r"\b(who|which)\s+(\w+)\s+(who|which)\s+(\w+)\b", prompt, re.IGNORECASE)
    if match is None:
        return None
    terminal = prompt.rstrip()[-1:] if prompt.rstrip()[-1:] in ".!?" else ""
    main = prompt[: match.start()].rstrip(" ,;") + terminal
    tail = prompt[match.end():].strip().rstrip(".!?").strip()
    if tail:
        return None  # more content after the second clause: not this narrow shape
    main_plan = _fake_single_clause_plan(main, metadata)
    tenses = [t for t in metadata.get("tenses", "").split(",") if t]

    def subject_relative(rel: str, verb_word: str) -> dict:
        clause_slots = _fake_single_clause_plan("He " + verb_word, metadata)["slots"]
        _fake_drop_subject(clause_slots)
        _fake_ensure_verb(clause_slots, tenses)
        return {"kind": "clause", "gloss": rel.lower(), "role": "relative", "rel_function": "subject", "clause": {"slots": clause_slots}}

    clause1 = subject_relative(match.group(1), match.group(2))
    clause2 = subject_relative(match.group(3), match.group(4))
    slots = list(main_plan["slots"])
    last_noun = max((i for i, slot in enumerate(slots) if slot.get("kind") == "content" and slot.get("pos") == "noun"), default=None)
    at = len(slots) if last_noun is None else last_noun + 1
    slots[at:at] = [clause1, clause2]
    return {"mood": main_plan["mood"], "slots": slots}


def _fake_coordination_plan(prompt: str, match, metadata: dict[str, str]) -> dict:
    """"I see the dog and I hear the cat": the first clause, then a
    ``coordinate`` clause slot holding the second -- built by recursing on the
    remainder (not just planning it as one bare clause), so a further
    "and"/"but"/"or" in it nests as a *further* coordinate clause inside this
    one's own plan, one clause per level: "I go, you go, and she goes" is
    clause1 + [clause2 + [clause3]], not three siblings. Each level's own
    renderer pass (``translator._arrange_coordination``, run once per nested
    plan) then converbs that level's own last verb, so a converb-coordinating
    language correctly marks every conjunct but the last."""
    terminal = prompt.rstrip()[-1:] if prompt.rstrip()[-1:] in ".!?" else ""
    main = prompt[: match.start()].rstrip(" ,;") + terminal
    rest = prompt[match.end():].strip().rstrip(".!?").strip()
    tenses = [t for t in metadata.get("tenses", "").split(",") if t]
    main_plan = _fake_single_clause_plan(main, metadata)
    nested = _fake_plan_dict(rest, metadata)
    clause_slots = list(nested["slots"])
    _fake_ensure_verb(clause_slots, tenses)
    clause = {"kind": "clause", "gloss": match.group(0).lower(), "role": "coordinate", "clause": {"slots": clause_slots}}
    return {"mood": main_plan["mood"], "slots": list(main_plan["slots"]) + [clause]}


_FAKE_COORDINATION_CHAIN = re.compile(
    r"^\s*(\w+)\s+(\w+)\s*,\s*(\w+)\s+(\w+)\s*,\s*(and|but|or)\s+(\w+)\s+(\w+)\s*([.!?]?)\s*$", re.IGNORECASE
)


def _fake_coordination_chain_plan(prompt: str, metadata: dict[str, str]) -> dict | None:
    """"I go, you go, and she works.": the ordinary written English style for
    three or more coordinated clauses -- a conjunction ("and"/"but"/"or")
    only before the *last* one, commas alone between the earlier ones (real
    English almost never repeats the conjunction the way ``_fake_plan_dict``'s
    own recursive "and ... and ..." handling needs). Each conjunct here is a
    bare subject + intransitive verb; built directly as the same right-
    branching nest recursive coordination produces (clause1 + [clause2 +
    [clause3]]), so it renders exactly the same way. ``None`` when the prompt
    isn't this three-conjunct shape (a real fourth conjunct would need
    another comma-separated pair before the conjunction, not attempted here)."""
    match = _FAKE_COORDINATION_CHAIN.match(prompt)
    if match is None:
        return None
    subject1, verb1, subject2, verb2, conj, subject3, verb3, _terminal = match.groups()
    tenses = [t for t in metadata.get("tenses", "").split(",") if t]

    def clause_slots(subject: str, verb_word: str) -> list[dict]:
        detected_tense, lemma = _fake_detect_tense_and_lemma(verb_word.lower())
        tense_label = _fake_tense_label(detected_tense, tenses)
        verb_slot = {
            "kind": "content", "gloss": lemma, "pos": "verb",
            "agreement": _FAKE_AGREEMENT_BY_PRONOUN.get(subject.lower(), "default"),
        }
        if tense_label:
            verb_slot["tense"] = tense_label
        return [{"kind": "content", "gloss": subject.lower(), "pos": "pronoun"}, verb_slot]

    innermost = {"kind": "clause", "gloss": conj.lower(), "role": "coordinate", "clause": {"slots": clause_slots(subject3, verb3)}}
    middle = {
        "kind": "clause", "gloss": conj.lower(), "role": "coordinate",
        "clause": {"slots": clause_slots(subject2, verb2) + [innermost]},
    }
    return {"mood": "declarative", "slots": clause_slots(subject1, verb1) + [middle]}


def _fake_gapping_plan(prompt: str, metadata: dict[str, str]) -> dict | None:
    """"I eat rice, and she, beans.": gapping -- the second conjunct's own
    verb, shared with the first, is dropped, written on the page (per the
    usual linguistics convention for this construction) with a comma setting
    off the residual bare subject. In a language with ``clause_gapping`` the
    conlang clause is built with no verb slot at all (subject and object
    only, the object taking the case the shared verb's alignment gives it);
    a language without it gets the full form, the shared verb repeated.
    ``None`` when the prompt isn't this shape."""
    match = re.match(
        r"\s*(\w+)\s+(\w+)\s+(\w+)\s*,\s*(and|but|or)\s+(\w+)\s*,\s*(\w+)\s*([.!?]?)\s*$", prompt, re.IGNORECASE
    )
    if match is None:
        return None
    subject1, verb_word, object1, conj, subject2, object2, _terminal = match.groups()
    tenses = [t for t in metadata.get("tenses", "").split(",") if t]
    word_order = metadata.get("word_order", "SVO")
    alignment = metadata.get("alignment", "nominative_accusative")
    object_case = "accusative" if alignment == "nominative_accusative" else None
    detected_tense, lemma = _fake_detect_tense_and_lemma(verb_word.lower())
    tense_label = _fake_tense_label(detected_tense, tenses)
    order = _FAKE_ROLE_ORDER.get(word_order, ("S", "V", "O"))

    def make_verb(subject: str) -> dict:
        slot = {"kind": "content", "gloss": lemma, "pos": "verb", "agreement": _FAKE_AGREEMENT_BY_PRONOUN.get(subject.lower(), "default")}
        if tense_label:
            slot["tense"] = tense_label
        return slot

    def make_object(word: str) -> dict:
        lowered = word.lower()
        singular = _fake_singular(lowered)
        slot = {"kind": "content", "gloss": singular or lowered, "pos": "noun"}
        if singular:
            slot["number"] = "plural"
        if object_case:
            slot["case"] = object_case
        return slot

    roles1 = {"S": [{"kind": "content", "gloss": subject1.lower(), "pos": "pronoun"}], "V": [make_verb(subject1)], "O": [make_object(object1)]}
    main_slots = [s for role in order for s in roles1[role]]
    gapping = metadata.get("clause_gapping") == "true"
    roles2 = {
        "S": [{"kind": "content", "gloss": subject2.lower(), "pos": "pronoun"}],
        "V": [] if gapping else [make_verb(subject2)],
        "O": [make_object(object2)],
    }
    clause_slots = [s for role in order for s in roles2[role]]
    clause = {"kind": "clause", "gloss": conj.lower(), "role": "coordinate", "clause": {"slots": clause_slots}}
    return {"mood": "declarative", "slots": main_slots + [clause]}


def _fake_right_node_raising_plan(prompt: str, metadata: dict[str, str]) -> dict | None:
    """"I bought, and she sold, the car.": right-node raising -- a direct
    object shared by every conjunct is written only once, after all of them,
    the earlier conjuncts left without one (again the usual written
    convention, commas setting off each verb-only conjunct). A language
    without ``clause_right_node_raising`` gets the shared object repeated
    in every conjunct instead. The shared object is a single bare noun (no
    article, no adjective); ``None`` when the prompt isn't this shape."""
    match = re.match(
        r"\s*(\w+)\s+(\w+)\s*,\s*(and|but|or)\s+(\w+)\s+(\w+)\s*,\s*(?:the\s+)?(.+?)\s*([.!?]?)\s*$", prompt,
        re.IGNORECASE,
    )
    if match is None:
        return None
    subject1, verb1, conj, subject2, verb2, shared_object, _terminal = match.groups()
    if " " in shared_object.strip():
        return None  # more than a bare noun: not this narrow shape
    tenses = [t for t in metadata.get("tenses", "").split(",") if t]
    word_order = metadata.get("word_order", "SVO")
    alignment = metadata.get("alignment", "nominative_accusative")
    object_case = "accusative" if alignment == "nominative_accusative" else None
    order = _FAKE_ROLE_ORDER.get(word_order, ("S", "V", "O"))

    def clause_slots(subject: str, verb_word: str, with_object: bool) -> list[dict]:
        detected_tense, lemma = _fake_detect_tense_and_lemma(verb_word.lower())
        tense_label = _fake_tense_label(detected_tense, tenses)
        verb_slot = {
            "kind": "content", "gloss": lemma, "pos": "verb",
            "agreement": _FAKE_AGREEMENT_BY_PRONOUN.get(subject.lower(), "default"),
        }
        if tense_label:
            verb_slot["tense"] = tense_label
        roles = {"S": [{"kind": "content", "gloss": subject.lower(), "pos": "pronoun"}], "V": [verb_slot], "O": []}
        if with_object:
            roles["O"] = [
                {"kind": "content", "gloss": shared_object.strip().lower(), "pos": "noun",
                 **({"case": object_case} if object_case else {})}
            ]
        return [s for role in order for s in roles[role]]

    keep_object = metadata.get("clause_right_node_raising") != "true"
    main_slots = clause_slots(subject1, verb1, with_object=keep_object)
    clause = {
        "kind": "clause", "gloss": conj.lower(), "role": "coordinate",
        "clause": {"slots": clause_slots(subject2, verb2, with_object=True)},
    }
    return {"mood": "declarative", "slots": main_slots + [clause]}


_FAKE_GERUND_SUBJECT = re.compile(
    r"^\s*(\w+)ing\s+(?:the\s+)?(\w+)\s+(pleases|pleased|please|surprises|surprised|surprise|"
    r"worries|worried|worry|annoys|annoyed|annoy)\s+(me|him|her|us|them|you)\s*([.!?]?)\s*$",
    re.IGNORECASE,
)
_FAKE_PSYCH_VERBS = {
    "pleases": "please", "pleased": "please", "please": "please",
    "surprises": "surprise", "surprised": "surprise", "surprise": "surprise",
    "worries": "worry", "worried": "worry", "worry": "worry",
    "annoys": "annoy", "annoyed": "annoy", "annoy": "annoy",
}
_FAKE_PSYCH_PAST = {"pleased", "surprised", "worried", "annoyed"}
_FAKE_DOUBLED_FINAL = ("mm", "nn", "tt", "pp", "gg", "bb", "dd")
_FAKE_OBJECT_TO_SUBJECT_GLOSS = {"me": "i", "him": "he", "her": "she", "us": "we", "them": "they", "you": "you"}
"""The base (subject-form) gloss of an English object pronoun -- an object is
never a lexicon gloss of its own (only "I"/"you"/"he"/"we"/"she"/"they"/"it"
are; "me" etc. are the SAME word, marked with the accusative case)."""


def _fake_gerund_subject_plan(prompt: str, metadata: dict[str, str]) -> dict | None:
    """"Seeing the river pleases me.": a nominalized clause AS THE SUBJECT
    (not, as usual, an object or a bare predicate) of a small closed set of
    "psych" verbs. ``None`` when the prompt isn't this shape."""
    match = _FAKE_GERUND_SUBJECT.match(prompt)
    if match is None:
        return None
    verb_stem, obj_noun, psych_word, obj_pronoun, _terminal = match.groups()
    lemma = verb_stem.lower()
    if lemma.endswith(_FAKE_DOUBLED_FINAL) and len(lemma) > 2:
        lemma = lemma[:-1]
    tenses = [t for t in metadata.get("tenses", "").split(",") if t]
    psych_lemma = _FAKE_PSYCH_VERBS[psych_word.lower()]
    tense_label = _fake_tense_label("past" if psych_word.lower() in _FAKE_PSYCH_PAST else "non_past", tenses)
    nominalized_available = "nominalized" in [f for f in metadata.get("verb_forms", "").split(",") if f]
    embedded_verb: dict = {"kind": "content", "gloss": lemma, "pos": "verb", "agreement": "default"}
    if nominalized_available:
        embedded_verb["verb_form"] = "nominalized"
    elif tense_label:
        embedded_verb["tense"] = tense_label
    embedded_slots = [embedded_verb, {"kind": "content", "gloss": obj_noun.lower(), "pos": "noun"}]
    subject_clause = {"kind": "clause", "gloss": "", "role": "nominal", "clause": {"slots": embedded_slots}}
    verb_slot = {"kind": "content", "gloss": psych_lemma, "pos": "verb", "agreement": "default"}
    if tense_label:
        verb_slot["tense"] = tense_label
    object_case = "accusative" if metadata.get("alignment", "nominative_accusative") == "nominative_accusative" else None
    object_gloss = _FAKE_OBJECT_TO_SUBJECT_GLOSS.get(obj_pronoun.lower(), obj_pronoun.lower())
    object_slot = {"kind": "content", "gloss": object_gloss, "pos": "pronoun"}
    if object_case:
        object_slot["case"] = object_case
    return {"mood": "declarative", "slots": [subject_clause, verb_slot, object_slot]}


def _fake_passive_control_plan(prompt: str, words, to_index: int, metadata: dict[str, str]) -> dict:
    """"He is believed to sleep.": a passivized control verb. The matrix is
    just subject + a passive verb (no object slot -- the erstwhile object was
    promoted to subject by the passive); the infinitive complement's own
    controller is that same matrix subject, exactly like an ordinary
    same-subject infinitive. Restricted to a pronoun subject (a name would
    need the same noun-phrase handling the ordinary SVO path already has,
    not attempted here)."""
    subject_word = words[0].group(0)
    copula_tok = words[to_index - 2].group(0).lower()
    participle = words[to_index - 1].group(0).lower()
    lemma = _FAKE_PASSIVE_CONTROL_PARTICIPLES[participle]
    rest = prompt[words[to_index].end():].strip().rstrip(".!?").strip()
    tenses = [t for t in metadata.get("tenses", "").split(",") if t]
    tense_label = _fake_tense_label("past" if copula_tok in _FAKE_PAST_COPULAS else "non_past", tenses)
    verb_slot = {
        "kind": "content", "gloss": lemma, "pos": "verb",
        "agreement": _FAKE_AGREEMENT_BY_PRONOUN.get(subject_word.lower(), "default"), "voice": "passive",
    }
    if tense_label:
        verb_slot["tense"] = tense_label
    main_slots = [{"kind": "content", "gloss": subject_word.lower(), "pos": "pronoun"}, verb_slot]
    if "infinitive" in [f for f in metadata.get("verb_forms", "").split(",") if f]:
        clause_slots = _fake_single_clause_plan("He " + rest, metadata)["slots"]
        _fake_drop_subject(clause_slots)
        _fake_ensure_verb(clause_slots, tenses)
        for slot in clause_slots:
            if slot.get("pos") == "verb":
                for key in ("tense", "agreement", "subject_gloss", "aspect", "verb_mood"):
                    slot.pop(key, None)
                slot["verb_form"] = "infinitive"
                if metadata.get("infinitive_agrees") == "true":
                    slot["agreement"] = _FAKE_CONTROLLER_PERSON.get(subject_word.lower(), "default")
        linker = ""
    else:
        clause_slots = _fake_single_clause_plan(f"{subject_word} {rest}", metadata)["slots"]
        linker = "that"
    main_slots.append({"kind": "clause", "gloss": linker, "role": "complement", "clause": {"slots": clause_slots}})
    return {"mood": "declarative", "slots": main_slots}


def _fake_infinitive_plan(prompt: str, words, to_index: int, metadata: dict[str, str]) -> dict:
    """"I want to see the river": the main clause with the complement after
    it -- an infinitive (no subject, no tense) where the language has one,
    else a finite clause repeating the subject. "He seems to see the river"
    (subject-to-subject raising) is mechanically the same shape, already
    handled by ``_FAKE_INFINITIVE_VERBS`` including the raising verbs.
    "He is believed to see the river" (a *passivized* control verb: an
    object-control verb's own object, promoted to subject by the passive, now
    controls the infinitive) is different enough structurally -- the matrix
    has no object slot at all, and its own verb is passive -- to build
    separately; see ``_fake_passive_control_plan``."""
    if (
        words[to_index - 1].group(0).lower() in _FAKE_PASSIVE_CONTROL_PARTICIPLES
        and to_index >= 2
        and words[to_index - 2].group(0).lower() in _FAKE_COPULAS
    ):
        return _fake_passive_control_plan(prompt, words, to_index, metadata)
    terminal = prompt.rstrip()[-1:] if prompt.rstrip()[-1:] in ".!?" else ""
    main = prompt[: words[to_index].start()].rstrip(" ,;") + terminal
    rest = prompt[words[to_index].end():].strip().rstrip(".!?").strip()
    subject_word = words[0].group(0)
    main_verb = words[to_index - 1].group(0).lower()
    controller: str | None = None
    if (
        main_verb in _FAKE_OBJECT_PRONOUNS
        and to_index >= 3
        and words[to_index - 2].group(0).lower() in _FAKE_OBJECT_CONTROL
    ):
        controller = main_verb
        main_verb = words[to_index - 2].group(0).lower()
    main_plan = _fake_single_clause_plan(main, metadata)
    main_slots = list(main_plan["slots"])
    detected_tense, lemma = _fake_detect_tense_and_lemma(main_verb)
    tenses = [t for t in metadata.get("tenses", "").split(",") if t]
    for slot in main_slots:
        if slot.get("gloss") == main_verb:
            slot.update({"pos": "verb", "gloss": lemma, "agreement": _FAKE_AGREEMENT_BY_PRONOUN.get(subject_word.lower(), "default")})
            tense_label = _fake_tense_label(detected_tense, tenses)
            if tense_label:
                slot["tense"] = tense_label
    if "infinitive" in [f for f in metadata.get("verb_forms", "").split(",") if f]:
        clause_slots = _fake_single_clause_plan("He " + rest, metadata)["slots"]
        _fake_drop_subject(clause_slots)
        _fake_ensure_verb(clause_slots, tenses)
        for slot in clause_slots:
            if slot.get("pos") == "verb":
                for key in ("tense", "agreement", "subject_gloss", "aspect", "verb_mood"):
                    slot.pop(key, None)
                slot["verb_form"] = "infinitive"
                if metadata.get("infinitive_agrees") == "true":
                    slot["agreement"] = _FAKE_CONTROLLER_PERSON.get(controller or subject_word.lower(), "default")
        linker = ""
    else:
        clause_slots = _fake_single_clause_plan(f"{subject_word} {rest}", metadata)["slots"]
        linker = "that"
    main_slots.append({"kind": "clause", "gloss": linker, "role": "complement", "clause": {"slots": clause_slots}})
    return {"mood": main_plan["mood"], "slots": main_slots}


def _fake_plan_dict(prompt: str, metadata: dict[str, str]) -> dict:
    """Splits at the first subordinating word that has a main clause before
    it (at least one word) and at least two words after it ("I see that
    mountain" is not split: "that" is a demonstrative there), plans the two
    halves separately and nests the second as a ``"clause"`` slot -- repeated
    on the remainder, so several clauses nest. The nested clause is placed
    after the main clause's own slots whatever the word order (the fake does
    not model where a real language would put it)."""
    the_more = re.match(r"\s*the more\s+(.+?)\s*,\s*the more\s+(.+?)\s*([.!?]?)\s*$", prompt, re.IGNORECASE)
    if the_more:
        return _fake_the_more_plan(the_more, metadata)
    topic_match = re.match(r"\s*as for\s+(.+?)\s*,\s*(.+?)\s*([.!?]?)\s*$", prompt, re.IGNORECASE)
    if topic_match:
        return _fake_topic_plan(topic_match, metadata)
    coordination_chain = _fake_coordination_chain_plan(prompt, metadata)
    if coordination_chain:
        return coordination_chain
    gerund_subject = _fake_gerund_subject_plan(prompt, metadata)
    if gerund_subject:
        return gerund_subject
    gapping = _fake_gapping_plan(prompt, metadata)
    if gapping:
        return gapping
    right_node_raising = _fake_right_node_raising_plan(prompt, metadata)
    if right_node_raising:
        return right_node_raising
    stacked_relative = _fake_stacked_relative_plan(prompt, metadata)
    if stacked_relative:
        return stacked_relative
    words = list(re.finditer(r"[A-Za-z']+", prompt))
    for index, match in enumerate(words):
        word = match.group(0).lower()
        if (
            word == "which" and index >= 1
            and words[index - 1].group(0).lower() in _FAKE_PP_RELATIVE_PREPS
            and len(words) - index - 1 >= 1
        ):
            return _fake_relative_plan(prompt, match, metadata, prep=words[index - 1].group(0).lower(), prep_match=words[index - 1])
        if word in ("who", "which", "whom", "whose") and index >= 1 and len(words) - index - 1 >= 1:
            return _fake_relative_plan(prompt, match, metadata)
        if word == "to" and index >= 2 and len(words) - index - 1 >= 1:
            before = words[index - 1].group(0).lower()
            control = (
                before in _FAKE_OBJECT_PRONOUNS and index >= 3 and words[index - 2].group(0).lower() in _FAKE_OBJECT_CONTROL
            )
            passive_control = (
                before in _FAKE_PASSIVE_CONTROL_PARTICIPLES and index >= 2
                and words[index - 2].group(0).lower() in _FAKE_COPULAS
            )
            if before in _FAKE_INFINITIVE_VERBS or control or passive_control:
                return _fake_infinitive_plan(prompt, words, index, metadata)
        if (
            word in ("and", "but", "or")
            and index >= 2
            and len(words) - index - 1 >= 2
            and words[index + 1].group(0).lower() in _FAKE_SUBJECT_PRONOUNS
        ):
            return _fake_coordination_plan(prompt, match, metadata)
    for index, match in enumerate(words):
        linker = match.group(0).lower()
        if linker not in _FAKE_SUBORDINATORS or index == 0 or len(words) - index - 1 < 2:
            continue
        terminal = prompt.rstrip()[-1:] if prompt.rstrip()[-1:] in ".!?" else ""
        main = prompt[: match.start()].rstrip(" ,;") + terminal
        rest = prompt[match.end():].strip().rstrip(".!?").strip()
        main_plan = _fake_single_clause_plan(main, metadata)
        _fake_ensure_verb(main_plan["slots"], [t for t in metadata.get("tenses", "").split(",") if t])
        nested = _fake_plan_dict(rest, metadata)
        clause_slot: dict = {"kind": "clause", "gloss": linker, "clause": {"slots": nested["slots"]}}
        if linker in _FAKE_SUBORDINATOR_ROLE:
            clause_slot["role"] = _FAKE_SUBORDINATOR_ROLE[linker]
        else:
            clause_slot["role"] = "adverbial"
        return {"mood": main_plan["mood"], "slots": main_plan["slots"] + [clause_slot]}
    return _fake_single_clause_plan(prompt, metadata)


def _fake_the_more_plan(match, metadata: dict[str, str]) -> dict:
    """"The more you read, the more you learn": two parallel parts -- the second
    is the main clause, the first an adverbial clause "the-more" -- each with the
    adverb "more" right before its verb."""
    def with_more(text: str) -> dict:
        plan = _fake_plan_dict(text, metadata)
        slots = list(plan["slots"])
        _fake_ensure_verb(slots, [t for t in metadata.get("tenses", "").split(",") if t])
        at = next((i for i, slot in enumerate(slots) if slot.get("pos") == "verb"), len(slots))
        slots.insert(at, {"kind": "content", "gloss": "more", "pos": "adverb"})
        return {"mood": plan["mood"], "slots": slots}

    terminal = match.group(3) or "."
    nested = with_more(match.group(1) + ".")
    main = with_more(match.group(2) + terminal)
    clause = {"kind": "clause", "gloss": "the-more", "role": "adverbial", "clause": {"slots": nested["slots"]}}
    return {"mood": main["mood"], "slots": main["slots"] + [clause]}


def _fake_topic_plan(match, metadata: dict[str, str]) -> dict:
    """"As for the cat, it sleeps": the topic noun phrase is planned as its
    own "topic"-role clause slot (no verb), placed first. Deliberately a
    bare noun only (optionally plural, optionally with "the") -- the richer
    modifier-grouping machinery (``noun_phrase``/``build_np``) is a closure
    local to ``_fake_single_clause_plan`` and not reusable standalone here.
    The main clause's own resumptive subject pronoun is left in this plan
    as an ordinary pronoun; the renderer drops it
    (``translator._dropped_topic_resumptive_pronouns``), not this function."""
    has_articles = metadata.get("has_articles") == "true"
    topic_tokens = _fake_tokenize(match.group(1))
    has_article = bool(topic_tokens) and topic_tokens[0] in _FAKE_ARTICLES
    if has_article:
        topic_tokens = topic_tokens[1:]
    noun_tok = topic_tokens[-1] if topic_tokens else match.group(1).strip().lower()
    singular = _fake_singular(noun_tok)
    noun_slot: dict = {"kind": "content", "gloss": singular or noun_tok, "pos": "noun"}
    if singular:
        noun_slot["number"] = "plural"
    topic_slots = ([{"kind": "article"}] if has_article and has_articles else []) + [noun_slot]
    terminal = match.group(3) or "."
    remainder = _fake_plan_dict(match.group(2) + terminal, metadata)
    topic_clause = {"kind": "clause", "role": "topic", "clause": {"slots": topic_slots}}
    return {"mood": remainder["mood"], "slots": [topic_clause] + list(remainder["slots"])}


def _fake_sentence_plan(prompt: str, metadata: dict[str, str]) -> str:
    return json.dumps(_fake_plan_dict(prompt, metadata))


def _fake_guess_ipa(form: str) -> str:
    text = form.lower()
    out: list[str] = []
    i = 0
    while i < len(text):
        for digraph, ipa in _GUESS_IPA_DIGRAPHS:
            if text.startswith(digraph, i):
                out.append(ipa)
                i += len(digraph)
                break
        else:
            out.append(_GUESS_IPA_LETTERS.get(text[i], text[i]))
            i += 1
    return "".join(out)


class FakeLLMClient:
    def complete(self, request: LLMRequest) -> LLMResponse:
        strategy = request.metadata.get("fake_strategy", "generic")
        if strategy == "choose_index":
            num_options = int(request.metadata.get("num_options", "1"))
            index = stable_hash(request.prompt) % num_options + 1
            text = str(index)
        elif strategy == "batch_choose_index":
            counts = [int(c) for c in request.metadata.get("candidate_counts", "").split(",") if c]
            text = "\n".join(
                f"{i}:{stable_hash(f'{request.prompt}#{i}') % count + 1}" for i, count in enumerate(counts, start=1)
            )
        elif strategy == "passthrough":
            text = request.metadata.get("fallback_text", "")
        elif strategy == "trait_profile":
            field_names = [f for f in request.metadata.get("trait_fields", "").split(",") if f]
            text = _fake_trait_profile(request.prompt, field_names)
        elif strategy == "guess_ipa":
            text = _fake_guess_ipa(request.prompt)
        elif strategy == "sentence_plan":
            text = _fake_sentence_plan(request.prompt, request.metadata)
        else:
            text = f"fake-response-{stable_hash(request.prompt) % 10_000}"

        return LLMResponse(
            text=text,
            model=FAKE_MODEL_NAME,
            input_tokens=max(1, len(request.system) + len(request.prompt)) // 4,
            output_tokens=max(1, len(text) // 4),
            stop_reason="end_turn",
        )
