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
_FAKE_PRONOUN_TOKENS = {"i", "you", "he", "we", "this", "that"}
_FAKE_AGREEMENT_BY_PRONOUN = {"i": "I", "you": "you", "he": "he", "we": "we"}
_FAKE_IRREGULAR_PAST_LEMMA = {
    "went": "go", "saw": "see", "came": "come", "ate": "eat", "drank": "drink",
    "said": "say", "knew": "know", "slept": "sleep", "gave": "give",
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
    raw_tokens = _fake_tokenize(prompt)
    wh_token = next((t for t in raw_tokens[:1] if t in _FAKE_WH), None)
    mood = "declarative"
    if ends_with == "?":
        mood = "wh_question" if wh_token else "question"
    elif (
        ends_with == "!"
        and raw_tokens
        and raw_tokens[0] not in _FAKE_PRONOUN_TOKENS | _FAKE_COPULAS | _FAKE_ARTICLES | _FAKE_WH
        and raw_tokens[0] not in name_by_placeholder
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

    def noun_phrase(tok: str, case: str | None) -> list[dict]:
        if tok in name_by_placeholder:
            name_slot: dict = {"kind": "name", "gloss": name_by_placeholder[tok]}
            if case:
                name_slot["case"] = case
            return [name_slot]
        is_pronoun = tok in _FAKE_PRONOUN_TOKENS or tok in _FAKE_WH
        prefix = [] if is_pronoun or not (used_article and has_articles) else [{"kind": "article"}]
        singular = None if is_pronoun else _fake_singular(tok)
        slot = content_slot(singular or tok, "pronoun" if is_pronoun else "noun", case)
        if singular:
            slot["number"] = "plural"
        return prefix + [slot]

    if wh_token in ("what", "who") and len(content_tokens) == 2 and not has_copula:
        content_tokens = content_tokens + [wh_token]  # "what do you see" -> you see WHAT (object)
        wh_token = None

    if mood == "imperative" and content_tokens:
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
            adjective_slot["agrees_with"] = _fake_singular(subject_tok) or subject_tok
        adjective_group = adverb_slots + [adjective_slot]
        copula_group: list[dict] = []
        if has_overt_copula:
            detected_tense = "past" if copula_tok in _FAKE_PAST_COPULAS else "non_past"
            tense_label = _fake_tense_label(detected_tense, tenses)
            copula_slot = {"kind": "copula", "agreement": _FAKE_AGREEMENT_BY_PRONOUN.get(subject_tok, "default")}
            if noun_classes and subject_tok not in _FAKE_PRONOUN_TOKENS and subject_tok not in name_by_placeholder:
                copula_slot["subject_gloss"] = _fake_singular(subject_tok) or subject_tok
            if tense_label:
                copula_slot["tense"] = tense_label
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
        if modal:
            verb_mood_label = _fake_mood_label(_FAKE_MODALS[modal], verb_moods)
            detected_tense = "non_past"
        tense_label = _fake_tense_label(detected_tense, tenses)
        subject_case = "ergative" if alignment == "ergative_absolutive" else None
        object_case = "accusative" if alignment == "nominative_accusative" else None
        subject_np = noun_phrase(subject_tok, subject_case)
        object_np = noun_phrase(obj_tok, object_case)
        verb_slot = {
            "kind": "content", "gloss": verb_lemma, "pos": "verb",
            "agreement": _FAKE_AGREEMENT_BY_PRONOUN.get(subject_tok, "default"),
        }
        if tense_label:
            verb_slot["tense"] = tense_label
        if noun_classes and subject_tok not in _FAKE_PRONOUN_TOKENS and subject_tok not in name_by_placeholder:
            verb_slot["subject_gloss"] = _fake_singular(subject_tok) or subject_tok
        if object_agreement:
            verb_slot["object_gloss"] = (
                obj_tok if obj_tok in _FAKE_PRONOUN_TOKENS else (_fake_singular(obj_tok) or obj_tok)
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


_FAKE_SUBORDINATORS = {"that", "because", "if", "when", "although", "while"}
_FAKE_SUBORDINATOR_ROLE = {"that": "complement"}


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
        linker = match.group(0).lower()
        if linker not in _FAKE_SUBORDINATORS or index == 0 or len(words) - index - 1 < 2:
            continue
        terminal = prompt.rstrip()[-1:] if prompt.rstrip()[-1:] in ".!?" else ""
        main = prompt[: match.start()].rstrip(" ,;") + terminal
        rest = prompt[match.end():].strip().rstrip(".!?").strip()
        main_plan = _fake_single_clause_plan(main, metadata)
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
