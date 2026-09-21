"""Stress (and Japanese pitch accent) in the curated real lexicons."""

import pytest

from conlang_generator.core.romanization import STRESS_MARK
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.reference_languages import real_stress
from conlang_generator.generation.reference_languages.real_lexicon import curated_profiles, real_words
from conlang_generator.llm.fake_client import FakeLLMClient

# languages whose lexicons carry a stress mark on (nearly) every polysyllabic word
_STRESS_LANGUAGES = (
    "Arabic", "Basque", "Bengali", "Danish", "Dutch", "English", "Finnish", "French", "Georgian", "German", "Hawaiian", "Hebrew", "Hindi", "Hungarian", "Icelandic",
    "Indonesian", "Italian", "Latin", "Malay", "Mongolian", "Nahuatl", "Norwegian", "Old Norse", "Pama-Nyungan",
    "Persian", "Polish", "Portuguese", "Quechua", "Russian", "Spanish", "Swahili", "Swedish", "Tamil", "Turkish", "Welsh",
)


def _by_spelling(name):
    return {spelling: ipa for spelling, ipa in real_words(name).values()}


@pytest.mark.parametrize("name", _STRESS_LANGUAGES)
def test_stress_marks_sit_before_a_syllable_onset_and_monosyllables_stay_unmarked(name):
    for spelling, ipa in real_words(name).values():
        assert ipa.count(STRESS_MARK) <= 1, (name, spelling, ipa)
        if STRESS_MARK not in ipa:
            continue
        count = real_stress.syllable_count(ipa, name)
        assert count > 1, f"{name}: monosyllable {spelling!r} /{ipa}/ is marked"
        index = real_stress.stressed_syllable(ipa, name)
        assert index is not None and 0 <= index < count, (name, spelling, ipa)
        # the mark sits exactly where the word's own syllable break is
        assert real_stress.with_stress(ipa, name, index) == ipa, (name, spelling, ipa)


@pytest.mark.parametrize("name", _STRESS_LANGUAGES)
def test_nearly_every_polysyllabic_word_carries_a_stress_mark(name):
    marked, total = real_stress.coverage(name)
    assert total and marked / total >= 0.97, (name, marked, total)


def test_known_stress_positions_across_the_kinds_of_language():
    def stressed(name, spelling):
        ipa = _by_spelling(name)[spelling]
        return real_stress.stressed_syllable(ipa, name)

    assert stressed("Dutch", "water") == 0 and stressed("Dutch", "geloven") == 1  # initial, unstressed prefix ge-
    assert stressed("German", "Wasser") == 0 and stressed("German", "bekommen") == 1
    assert stressed("English", "water") == 0 and stressed("English", "between") == 1 and stressed("English", "understand") == 2
    assert stressed("Russian", "voda") == 1 and stressed("Russian", "kamen'") == 0 and stressed("Russian", "golova") == 2
    assert stressed("Spanish", "corazón") == 2 and stressed("Spanish", "árbol") == 0 and stressed("Spanish", "luna") == 0
    assert stressed("Portuguese", "árvore") == 0 and stressed("Portuguese", "coração") == 2
    assert stressed("Italian", "albero") == 0 and stressed("Italian", "mangiare") == 1  # antepenult / penult
    assert stressed("French", "montagne") == 1 and stressed("French", "prendre") == 0  # final, but never a final schwa
    assert stressed("Latin", "aqua") == 0 and stressed("Latin", "ignis") == 0  # a light or two-syllable word: the first
    assert stressed("Basque", "mendia") == 1 and stressed("Basque", "ura") == 0 and stressed("Basque", "ilargia") == 1
    assert stressed("Hindi", "bahut") == 1 and stressed("Hindi", "paani") == 0 and stressed("Hindi", "zaroorat") == 1
    assert stressed("Arabic", "hayawan") == 2 and stressed("Arabic", "kabir") == 1 and stressed("Arabic", "ana") == 0
    assert stressed("Georgian", "deda") == 0 and stressed("Georgian", "adamiani") == 2  # initial; antepenult of a longer word
    assert stressed("Hawaiian", "aloha") == 1 and stressed("Hawaiian", "kēlā") == 1 and stressed("Hawaiian", "keiki") == 0
    assert stressed("Polish", "woda") == 0 and stressed("Turkish", "kapı") == 1 and stressed("Turkish", "anne") == 0


def test_latin_uses_the_weight_rule_not_a_flat_pattern():
    # amīcus: long penult -> penult; mulier: light penult -> antepenult
    assert real_stress.stressed_syllable(real_stress.with_stress("amiːkus", "Latin", real_stress.default_stress_index("amiːkus", "Latin")), "Latin") == 1
    assert real_stress.default_stress_index("mulier", "Latin") == 0


def test_stress_survives_the_real_word_pipeline_for_exact_and_looser_copies():
    def language(word, sound):
        traits = TraitProfile(source_languages=("Dutch",), source_language_strictness=sound, source_word_strictness=word)
        return generate_language("T", GenerationSpec(prompt="p", seed=3, traits=traits), FakeLLMClient())

    exact = language(1.0, 1.0)
    water = exact.lexicon.by_gloss("water")
    assert water.ipa == "ˈwatər"
    dutch = {gloss: ipa for gloss, (_, ipa) in real_words("Dutch").items()}
    loose = [e for e in language(0.6, 0.9).lexicon.entries if e.notes.startswith("real-based")]
    checked = 0
    for entry in loose:
        real_ipa = dutch[entry.primary_gloss]
        plain = entry.ipa.replace(STRESS_MARK, "")
        if STRESS_MARK in real_ipa and len(real_stress.syllable_starts(real_stress.tokens(plain, "Dutch"), "Dutch")) > 1:
            checked += 1
            assert STRESS_MARK in entry.ipa, (entry.primary_gloss, real_ipa, entry.ipa)  # the real word's stress carries over
    assert checked >= 40


def test_japanese_pitch_accent_is_encoded_as_per_syllable_high_low_marks():
    japanese = _by_spelling("Japanese")
    pattern = lambda spelling: real_stress.pitch_pattern(japanese[spelling], "Japanese")
    assert pattern("taberu") == "LHL"  # accent 2: the drop follows the second mora
    assert pattern("sakana") == "LHH"  # flat (heiban)
    assert pattern("kodomo") == "LHH" and pattern("tsuki") == "LH"
    assert pattern("otoko") == "LHH" and pattern("sensei") == "LH" and pattern("uta") == "LH"  # senseː: 4 morae, the drop follows the third
    # phrases with particles and words with several possible accents are left unmarked rather than guessed
    assert real_stress.pitch_pattern(japanese["ni tsuite"], "Japanese") is None
    marked = [real_stress.pitch_pattern(ipa, "Japanese") for ipa in japanese.values()]
    marked = [p for p in marked if p]
    assert len(marked) >= 380  # ~91% of the polysyllabic entries; phrases and homographs stay unmarked
    for p in marked:
        assert p[0] in "LH" and "HLH" not in p  # at most one drop, never a rise after it
        assert p.count("LH") <= 1 or p[0] == "H"


def test_pitch_accent_number_places_the_drop_by_mora():
    assert real_stress.pitch_pattern(real_stress.with_pitch_accent("otoko", "Japanese", 3), "Japanese") == "LHH"
    assert real_stress.pitch_pattern(real_stress.with_pitch_accent("hikari", "Japanese", 1), "Japanese") == "HLL"
    assert real_stress.pitch_pattern(real_stress.with_pitch_accent("mizu", "Japanese", 0), "Japanese") == "LH"
    # a long vowel counts two morae: koːɾi is three morae, so accent 3 falls after its last syllable (ɾi)
    assert real_stress.pitch_pattern(real_stress.with_pitch_accent("koːɾi", "Japanese", 3), "Japanese") == "LH"
    assert real_stress.pitch_pattern(real_stress.with_pitch_accent("koːɾi", "Japanese", 2), "Japanese") == "HL"


def test_every_curated_language_is_readable_by_the_stress_reader():
    for profile in curated_profiles():
        for _, ipa in list(real_words(profile.name).values())[:40]:
            real_stress.syllable_count(ipa, profile.name)  # never raises


def test_hindi_stress_follows_syllable_weight_in_the_last_three_syllables():
    def index(ipa):
        return real_stress.default_stress_index(ipa, "Hindi")

    assert index("kərnaː") == 0 and index("paːniː") == 0  # a tie: the rightmost non-final syllable (penult)
    assert index("bəɖaː") == 1 and index("bəhut") == 1  # a heavier final syllable wins
    assert index("pəhaːɖ") == 1 and index("kitaːb") == 1  # a superheavy final syllable
    assert index("dʒaːnvər") == 0 and index("bənaːnaː") == 1  # the heaviest of the last three
    assert index("dʒaːnːaː") == 0  # a geminate closes the syllable before it: dʒaːn.naː
    weights = real_stress._syllable_weights(real_stress.tokens("kitaːb", "Hindi"), real_stress.syllable_starts(real_stress.tokens("kitaːb", "Hindi"), "Hindi"))
    assert weights == [1, 3]  # ki (light), taːb (long vowel + coda)


def test_basque_takes_the_second_syllable_of_a_word_of_three_or_more():
    assert real_stress.default_stress_index("mendia", "Basque") == 1
    assert real_stress.default_stress_index("etxe", "Basque") == 0  # a disyllable keeps its first
    assert real_stress.default_stress_index("bedeɾat̻s̻i", "Basque") == 1
    assert real_stress.default_stress_index("ur", "Basque") is None


def test_arabic_stress_is_the_cairene_weight_rule():
    def index(ipa):
        return real_stress.default_stress_index(ipa, "Arabic")

    assert index("kataba") == 0 and index("madrasa") == 0  # all light: the antepenult
    assert index("katabtu") == 1 and index("maktab") == 0  # a heavy (closed) penult; a disyllable's first
    assert index("kabiːr") == 1 and index("hajawaːn") == 2 and index("kitaːb") == 1  # superheavy final
    assert index("ʔistiʕmaːl") == 2 and index("taʕalama") == 1
    assert index("baina") == 0  # a diphthong is a long vowel: the heavy penult of a disyllable
    assert real_stress.default_stress_index("ʕuː", "Arabic") is None  # a monosyllable


def test_georgian_and_hawaiian_rules():
    georgian = lambda ipa: real_stress.default_stress_index(ipa, "Georgian")
    assert georgian("deda") == 0 and georgian("saxeli") == 0 and georgian("adamiani") == 2 and georgian("mama") == 0
    hawaiian = lambda ipa: real_stress.default_stress_index(ipa, "Hawaiian")
    assert hawaiian("aloha") == 1 and hawaiian("wahine") == 1 and hawaiian("kaːne") == 0  # penult
    assert hawaiian("ʔehaː") == 1 and hawaiian("inaː") == 1  # a final long vowel is a foot of its own
    assert hawaiian("keiki") == 0 and hawaiian("maikaʔi") == 1  # ei/ai are one syllable
    assert hawaiian("maːkou") == 1 and hawaiian("ʔoe") == 0  # a final diphthong is heavy; oe is a hiatus
    assert real_stress.syllable_count("hawaʔi", "Hawaiian") == 3 and real_stress.syllable_count("ia", "Hawaiian") == 2
