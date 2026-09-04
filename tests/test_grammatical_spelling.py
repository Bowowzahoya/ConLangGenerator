from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.romanization import GrammaticalSpelling, MuteSuffixRule, RomanizationScheme, apply_grammatical_spelling


def _scheme(**grammatical_spelling_kwargs) -> RomanizationScheme:
    return RomanizationScheme(rules=(), grammatical_spelling=GrammaticalSpelling(**grammatical_spelling_kwargs))


def test_no_rules_leaves_the_word_untouched():
    scheme = _scheme()
    assert apply_grammatical_spelling(scheme, "katze", PartOfSpeech.NOUN) == "katze"


def test_capitalized_pos_capitalizes_only_the_first_letter():
    scheme = _scheme(capitalized_pos=(PartOfSpeech.NOUN,))
    assert apply_grammatical_spelling(scheme, "katze", PartOfSpeech.NOUN) == "Katze"
    assert apply_grammatical_spelling(scheme, "laufen", PartOfSpeech.VERB) == "laufen"  # different POS, untouched


def test_all_caps_pos_uppercases_the_whole_word():
    scheme = _scheme(all_caps_pos=(PartOfSpeech.PRONOUN,))
    assert apply_grammatical_spelling(scheme, "ich", PartOfSpeech.PRONOUN) == "ICH"


def test_all_caps_wins_over_plain_capitalization_for_the_same_pos():
    scheme = _scheme(capitalized_pos=(PartOfSpeech.NOUN,), all_caps_pos=(PartOfSpeech.NOUN,))
    assert apply_grammatical_spelling(scheme, "katze", PartOfSpeech.NOUN) == "KATZE"


def test_mute_suffix_appends_with_no_ipa_change():
    scheme = _scheme(mute_suffix_by_pos=(MuteSuffixRule(pos=PartOfSpeech.VERB, suffix="r"),))
    assert apply_grammatical_spelling(scheme, "parle", PartOfSpeech.VERB) == "parler"
    assert apply_grammatical_spelling(scheme, "chat", PartOfSpeech.NOUN) == "chat"  # different POS, untouched


def test_mute_suffix_and_capitalization_combine():
    scheme = _scheme(
        capitalized_pos=(PartOfSpeech.VERB,),
        mute_suffix_by_pos=(MuteSuffixRule(pos=PartOfSpeech.VERB, suffix="r"),),
    )
    assert apply_grammatical_spelling(scheme, "parle", PartOfSpeech.VERB) == "Parler"


def test_multiple_mute_suffix_rules_only_apply_to_their_own_pos():
    scheme = _scheme(
        mute_suffix_by_pos=(
            MuteSuffixRule(pos=PartOfSpeech.VERB, suffix="r"),
            MuteSuffixRule(pos=PartOfSpeech.NOUN, suffix="e"),
        )
    )
    assert apply_grammatical_spelling(scheme, "parle", PartOfSpeech.VERB) == "parler"
    assert apply_grammatical_spelling(scheme, "chat", PartOfSpeech.NOUN) == "chate"
    assert apply_grammatical_spelling(scheme, "bon", PartOfSpeech.ADJECTIVE) == "bon"
