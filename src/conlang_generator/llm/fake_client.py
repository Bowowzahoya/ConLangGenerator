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
_FAKE_ADVERBS = {"very", "extremely", "quite", "really", "too", "so", "always", "never", "often"}


_FAKE_EVIDENTIAL_WORDS = {
    "reportedly": "reported", "allegedly": "reported", "apparently": "inferred", "evidently": "inferred",
    "visibly": "witnessed",
}
_FAKE_PERFECT_AUX = {"have", "has", "had"}
_FAKE_MODALS = {"would": "conditional", "may": "potential", "might": "potential", "can": "potential", "could": "potential"}
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
            else:
                break
            j += 1
        real_mods = set(mods) - {"the"}
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


def _fake_extract_names(prompt: str) -> tuple[str, dict[str, str]]:
    """Swaps each capitalized word that is neither sentence-initial nor "I"
    (a plausible proper name; a possessive 's is dropped) for a lowercase
    placeholder token, so the rest of the heuristic sees an ordinary
    noun-like token; returns the rewritten prompt and placeholder -> name."""
    names: dict[str, str] = {}
    first_word = re.search(r"[A-Za-z']+", prompt)
    start_of_first = first_word.start() if first_word else 0

    def swap(match: re.Match) -> str:
        if match.start() == start_of_first or match.group(1) == "I":
            return match.group(0)
        placeholder = f"zzname{chr(97 + len(names) % 26)}zz"  # letters only: the tokenizer splits on digits
        names[placeholder] = match.group(1)
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
    demonstrative_after_noun = metadata.get("demonstrative_after_noun") == "true"
    has_dual = "dual" in metadata.get("number_labels", "").split(",")
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
    clusivity = metadata.get("clusivity") == "true"
    third_person_gender = metadata.get("third_person_gender") == "true"
    honorific_you = metadata.get("honorific_you") == "true"
    existential = metadata.get("existential", "copula")
    possession_clause = metadata.get("possession_clause", "have")
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
            noun_slot["number"] = "dual" if numeral == "two" and has_dual else "plural"
        elif info.get("quantifier") and info["quantifier"] not in _FAKE_SINGULAR_QUANTIFIERS:
            noun_slot["number"] = "plural"
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
            if info.get("indefinite") and has_indefinite_article:
                before.append({"kind": "indefinite_article"})
            elif has_articles and (info.get("indefinite") or info.get("the") or used_article):
                before.append({"kind": "article"})
        if numeral is not None:
            before.append({"kind": "content", "gloss": numeral, "pos": "numeral"})
        if info.get("quantifier"):
            before.append({"kind": "content", "gloss": info["quantifier"], "pos": "quantifier"})
        return before + [noun_slot] + after

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

    if wh_token in ("what", "who") and len(content_tokens) == 2 and not has_copula:
        content_tokens = content_tokens + [wh_token]  # "what do you see" -> you see WHAT (object)
        wh_token = None

    existence_slots = _fake_existence_slots(
        tokens, word_order, tenses, has_overt_copula, existential, possession_clause, cases, noun_phrase, base_of,
        noun_classes, name_by_placeholder,
    )
    degree_slots = None if existence_slots is not None else _fake_degree_slots(
        tokens, tenses, has_overt_copula, comparative_strategy, comparative_case, comparative_marking,
        superlative_marking, postpositional, word_order, alignment, noun_phrase, base_of, noun_classes,
        name_by_placeholder,
    )
    voice_slots = None if (existence_slots is not None or degree_slots is not None) else _fake_voice_slots(
        tokens, metadata, voices, postpositional, word_order, alignment, tenses, noun_phrase, base_of,
        noun_classes, name_by_placeholder, tokens_no_copula,
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
        plural_subject = subject_tok in ("we", "they", "us", "them") or (
            subject_tok in np_info and (
                _FAKE_NUMERALS.get(np_info[subject_tok].get("numeral", ""), 1) > 1
                or np_info[subject_tok].get("demonstrative_plural")
                or _fake_singular(np_info[subject_tok]["noun"]) is not None
            )
        ) or (subject_tok not in _FAKE_PRONOUN_TOKENS and subject_tok not in np_info and _fake_singular(subject_tok) is not None)
        if verb_number_agreement and plural_subject:
            verb_slot["subject_number"] = "plural"
        if verb_politeness and subject_tok == "you" and pronoun_gloss("you") == "you-polite":
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
        slots = [
            {"kind": "negation"} if t == "not"
            else {"kind": "name", "gloss": name_by_placeholder[t]} if t in name_by_placeholder
            else content_slot(t, "adverb" if _fake_is_adverb(t) else "noun")
            for t in tokens_no_copula
        ]

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
}
_FAKE_SUBORDINATORS = {"that", "because", "if", "when", "although", "while"}
_FAKE_SUBORDINATOR_ROLE = {"that": "complement"}


def _fake_existence_slots(
    tokens, word_order, tenses, has_overt_copula, existential, possession_clause, cases, noun_phrase, base_of,
    noun_classes, name_by_placeholder,
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
    if possession_clause == "dative_be" and have_index is not None and 0 < have_index < len(tokens) - 1:
        possessor_tok, possessed_tok = tokens[have_index - 1], tokens[have_index + 1]
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
    "big", "small", "high", "low", "long", "short", "old", "new", "young", "good", "bad", "large", "tall", "wide",
    "narrow", "strong", "weak", "fast", "slow", "hot", "cold", "heavy", "light", "beautiful", "happy", "dark", "deep",
    "thick", "thin", "rich", "poor", "clean", "dirty", "near", "far", "wise", "brave", "quiet", "loud",
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


def _fake_degree_slots(
    tokens, tenses, has_overt_copula, strategy, comparative_case, comparative_marking, superlative_marking,
    postpositional, word_order, alignment, noun_phrase, base_of, noun_classes, name_by_placeholder,
):
    """Plans "X is bigger/more beautiful than Y", "X is more beautiful" and
    "X is the biggest/most beautiful" as ``subject + copula + adjective
    [+ standard]``, marking the degree and the standard per the language's own
    strategy; ``None`` when the tokens are not of that shape."""
    copula_index = next((i for i, t in enumerate(tokens) if t in _FAKE_COPULAS), None)
    if copula_index is None or copula_index != 1 or len(tokens) < 3:
        return None
    subject_tok = tokens[0]
    rest = tokens[2:]
    negated = "not" in rest
    rest = [t for t in rest if t != "not"]
    if not rest:
        return None
    standard_tok = None
    degree = None
    lemma = None
    if "than" in rest:
        than_index = rest.index("than")
        if than_index == 0 or than_index + 1 >= len(rest):
            return None
        standard_tok = rest[than_index + 1]
        head = rest[:than_index]
        found = _fake_degree_of(head[-1])
        if len(head) >= 2 and head[-2] == "more":
            lemma, degree = head[-1], "comparative"
        elif found is not None and found[1] == "comparative":
            lemma, degree = found
        else:
            return None
    elif len(rest) == 2 and rest[0] in ("more", "most"):
        lemma, degree = rest[1], "comparative" if rest[0] == "more" else "superlative"
    elif len(rest) == 1 and _fake_degree_of(rest[0]):
        lemma, degree = _fake_degree_of(rest[0])
    else:
        return None
    order = _FAKE_ROLE_ORDER.get(word_order, ("S", "V", "O"))
    tense_label = _fake_tense_label("past" if tokens[copula_index] in _FAKE_PAST_COPULAS else "non_past", tenses)
    marking = comparative_marking if degree == "comparative" else superlative_marking
    subject_np = noun_phrase(subject_tok, None)
    subject_is_noun = subject_tok not in _FAKE_PRONOUN_TOKENS and subject_tok not in name_by_placeholder

    adjective: dict = {"kind": "content", "gloss": lemma, "pos": "adjective"}
    if noun_classes and subject_is_noun:
        adjective["agrees_with"] = base_of(subject_tok)
    adjective_group: list[dict] = []
    if marking == "affix":
        adjective["degree"] = degree
    else:
        adjective_group.append(
            {"kind": "content", "gloss": "more" if degree == "comparative" else "most", "pos": "adverb"}
        )
    adjective_group.append(adjective)

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
        if strategy == "case" and comparative_case:
            standard_phrase = noun_phrase(standard_tok, comparative_case)
        elif strategy == "exceed":
            verb = [agrees({"kind": "content", "gloss": "exceed", "pos": "verb"})]
            standard_np = noun_phrase(standard_tok, object_case)
            standard_phrase = standard_np + verb if order.index("O") < order.index("V") else verb + standard_np
        else:
            than = [{"kind": "content", "gloss": "than", "pos": "preposition"}]
            standard_np = noun_phrase(standard_tok, None)
            standard_phrase = standard_np + than if postpositional else than + standard_np
    return subject_np + be + adjective_group + standard_phrase


_FAKE_MAKE = {"make", "makes", "made"}


def _fake_voice_slots(
    tokens, metadata, voices, postpositional, word_order, alignment, tenses, noun_phrase, base_of,
    noun_classes, name_by_placeholder, tokens_no_copula,
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


def _fake_relative_plan(prompt: str, match, metadata: dict[str, str]) -> dict:
    """"I see the dog who sleeps" / "the dog which I see" / "the man whose dog
    sleeps": the main clause, then a relative clause slot right after its last
    noun, with its ``rel_function`` (subject, object or possessor) and the
    relativized position left as a gap -- or filled by a resumptive pronoun
    where the language needs one."""
    terminal = prompt.rstrip()[-1:] if prompt.rstrip()[-1:] in ".!?" else ""
    main = prompt[: match.start()].rstrip(" ,;") + terminal
    rest = prompt[match.end():].strip().rstrip(".!?").strip()
    word = match.group(0).lower()
    main_plan = _fake_single_clause_plan(main, metadata)
    strategy = metadata.get("relativization", "pronoun")
    reach = metadata.get("relativization_reach", "possessor")
    first_rest = rest.split()[0].lower() if rest.split() else ""
    tenses = [t for t in metadata.get("tenses", "").split(",") if t]
    if word == "whose":
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
    plain_reaches = strategy in ("gap", "particle") and _FAKE_RELATIVE_ORDER.index(function) > _FAKE_RELATIVE_ORDER.index(reach)
    if strategy == "resumptive" or plain_reaches:
        if function == "object":
            clause_slots.append({"kind": "content", "gloss": "he", "pos": "pronoun", "case": "accusative"})
        elif function == "possessor":
            noun_index = next((i for i, slot in enumerate(clause_slots) if slot.get("pos") == "noun"), 0)
            clause_slots.insert(noun_index, {"kind": "content", "gloss": "he", "pos": "pronoun", "possessive": True})
    clause = {
        "kind": "clause", "gloss": "who" if word == "whom" else word, "role": "relative", "rel_function": function,
        "clause": {"slots": clause_slots},
    }
    slots = list(main_plan["slots"])
    last_noun = max((i for i, slot in enumerate(slots) if slot.get("kind") == "content" and slot.get("pos") == "noun"), default=None)
    slots.insert(len(slots) if last_noun is None else last_noun + 1, clause)
    return {"mood": main_plan["mood"], "slots": slots}


def _fake_coordination_plan(prompt: str, match, metadata: dict[str, str]) -> dict:
    """"I see the dog and I hear the cat": the first clause, then a
    ``coordinate`` clause slot holding the second."""
    terminal = prompt.rstrip()[-1:] if prompt.rstrip()[-1:] in ".!?" else ""
    main = prompt[: match.start()].rstrip(" ,;") + terminal
    rest = prompt[match.end():].strip().rstrip(".!?").strip()
    tenses = [t for t in metadata.get("tenses", "").split(",") if t]
    main_plan = _fake_single_clause_plan(main, metadata)
    clause_slots = _fake_single_clause_plan(rest, metadata)["slots"]
    _fake_ensure_verb(clause_slots, tenses)
    clause = {"kind": "clause", "gloss": match.group(0).lower(), "role": "coordinate", "clause": {"slots": clause_slots}}
    return {"mood": main_plan["mood"], "slots": list(main_plan["slots"]) + [clause]}


def _fake_infinitive_plan(prompt: str, words, to_index: int, metadata: dict[str, str]) -> dict:
    """"I want to see the river": the main clause with the complement after
    it -- an infinitive (no subject, no tense) where the language has one,
    else a finite clause repeating the subject."""
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
    words = list(re.finditer(r"[A-Za-z']+", prompt))
    for index, match in enumerate(words):
        word = match.group(0).lower()
        if word in ("who", "which", "whom", "whose") and index >= 1 and len(words) - index - 1 >= 1:
            return _fake_relative_plan(prompt, match, metadata)
        if word == "to" and index >= 2 and len(words) - index - 1 >= 1:
            before = words[index - 1].group(0).lower()
            control = (
                before in _FAKE_OBJECT_PRONOUNS and index >= 3 and words[index - 2].group(0).lower() in _FAKE_OBJECT_CONTROL
            )
            if before in _FAKE_INFINITIVE_VERBS or control:
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
