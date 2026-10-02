"""Reported speech, second round (grammar pass 35, a Discourse follow-up): a
quotative particle marks a complement clause under a *speech* verb ("say",
"tell", "claim", ...) as reported/quoted content, additional to whatever
"that"/complementizer-by-verb marking already exists -- not a replacement
for it. Models only indirect speech. Also: `_reported_speech_tense`
(tense backshift) is now gated to speech verbs specifically, not any
past-tense verb's complement."""

from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient
from tests._shared_language import cached_language
from conlang_generator.translation.sentence_planner import PlannedSlot, SentencePlan
from conlang_generator.translation.translator import _render_plan, translate_to_conlang, translate_to_english

_CLIENT = FakeLLMClient()

_language = cached_language


def _find(predicate, limit: int = 300):
    for seed in range(1, limit):
        language = _language(seed)
        if predicate(language.grammar):
            return language
    raise AssertionError("no seed found")


def _render(language, *slots):
    _, romanized, _, glosses = _render_plan(SentencePlan(slots=tuple(slots)), language, _CLIENT, [])
    return romanized, glosses


def _pronoun(gloss: str, **kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="pronoun", **kw)


def _verb(gloss: str = "sleep", **kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="verb", **kw)


def _clause(role: str, *slots: PlannedSlot, **kw) -> PlannedSlot:
    return PlannedSlot(kind="clause", gloss="that", role=role, clause=SentencePlan(slots=tuple(slots)), **kw)


def _annotation(language, text: str) -> str:
    """The annotated draft the fluency model would see for ``text``."""

    class _Spy(FakeLLMClient):
        def __init__(self):
            self.seen: list = []

        def complete(self, request):
            self.seen.append(request)
            return super().complete(request)

    spy = _Spy()
    translate_to_english(text, language, spy)
    return next(r.prompt for r in spy.seen if r.purpose == "translate.fluency")


# --- generation --------------------------------------------------------------


def test_quotative_particle_rolls_both_set_and_empty():
    grammars = [_language(s).grammar for s in range(1, 60)]
    assert any(g.quotative_particle for g in grammars)
    assert any(not g.quotative_particle for g in grammars)


def test_the_new_grammar_field_defaults_for_older_saved_languages():
    assert type(_language(1).grammar).model_fields["quotative_particle"].default == ""


# --- direct-plan rendering ----------------------------------------------------


def test_quotative_particle_follows_a_speech_verb_complement():
    language = _find(lambda g: g.quotative_particle)
    particle_rom = language.romanization.apply(language.grammar.quotative_particle)
    subject = _pronoun("he")
    verb = _verb("say", tense="past")
    complement = _clause("complement", _pronoun("she"), _verb("be"))
    romanized, _ = _render(language, subject, verb, complement)
    assert particle_rom in romanized
    # It's the very last token: the clause's own content, then the particle.
    assert romanized[-1] == particle_rom


def test_quotative_particle_is_gated_to_speech_verbs():
    # "He knew that she was late" is not reported speech -- no particle,
    # even on a language that has one.
    language = _find(lambda g: g.quotative_particle)
    particle_rom = language.romanization.apply(language.grammar.quotative_particle)
    subject = _pronoun("he")
    verb = _verb("know", tense="past")
    complement = _clause("complement", _pronoun("she"), _verb("be"))
    romanized, _ = _render(language, subject, verb, complement)
    assert particle_rom not in romanized


# --- free-text round trip -----------------------------------------------------


def test_free_text_speech_verb_complement_decodes_with_quoted_speech_annotation():
    language = _find(lambda g: g.quotative_particle)
    rendered = translate_to_conlang("He said that she was late.", language, _CLIENT)
    annotation = _annotation(rendered.language, rendered.text)
    assert "(quoted speech)" in annotation


def test_free_text_non_speech_verb_complement_has_no_quoted_speech_annotation():
    language = _find(lambda g: g.quotative_particle)
    rendered = translate_to_conlang("He knew that she was late.", language, _CLIENT)
    annotation = _annotation(rendered.language, rendered.text)
    assert "(quoted speech)" not in annotation


def test_plain_decode_is_unaffected_by_the_quotative_particle():
    # The particle is swallowed silently in the plain (fake/fallback) text,
    # same as the question particle.
    language = _find(lambda g: g.quotative_particle)
    rendered = translate_to_conlang("He said that she was late.", language, _CLIENT)
    decoded = translate_to_english(rendered.text, rendered.language, _CLIENT)
    assert "<unknown" not in decoded.text
