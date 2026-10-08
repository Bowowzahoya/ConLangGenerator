"""Tests for speech.engine_selection -- the per-word "auto" engine
choice built on top of speech.phoneme_coverage."""

from conlang_generator.speech import engine_selection


def test_choose_engine_returns_none_for_an_empty_candidate_list():
    assert engine_selection.choose_engine("pata", []) is None


def test_choose_engine_breaks_a_coverage_tie_with_naturalness():
    # "pata" is exact under both engines -- SAPI is ranked more natural.
    choice = engine_selection.choose_engine("pata", ["espeak", "sapi"])
    assert choice is not None
    assert choice.kind == "sapi"
    assert choice.fidelity == "exact"
    assert choice.notes == ()


def test_choose_engine_prefers_better_coverage_over_naturalness():
    # "kʼa" (ejective) is approximate under eSpeak, poor under SAPI --
    # eSpeak wins despite SAPI's higher naturalness rank.
    choice = engine_selection.choose_engine("kʼa", ["espeak", "sapi"])
    assert choice is not None
    assert choice.kind == "espeak"
    assert choice.fidelity == "approximate"
    assert choice.notes


def test_choose_engine_with_a_single_candidate_just_rates_it():
    choice = engine_selection.choose_engine("kʼa", ["sapi"])
    assert choice is not None
    assert choice.kind == "sapi"
    assert choice.fidelity == "poor"


def test_auto_client_for_word_returns_a_none_client_for_an_unresolvable_word():
    client_for_word = engine_selection.auto_client_for_word("pata", [])
    from conlang_generator.speech.tts import NoneTTSClient

    assert isinstance(client_for_word("pata"), NoneTTSClient)


def test_auto_client_for_word_groups_by_assigned_engine_before_resolving_for_utterance():
    # A toneless word and a tonal word, both forced onto eSpeak (SAPI
    # rates the ejective poorly, and strips tones outright) -- both
    # should share exactly one eSpeak client, switched to the Mandarin
    # tonal voice for the *whole* assigned group, not decided per word.
    # This is a regression guard for the exact bug the plan called out:
    # resolving for_utterance per bare word (or over the raw sentence)
    # would either miss the toneless word's own voice-consistency
    # guarantee or silently ignore the grouping eSpeak itself requires.
    tonal_ejective = "k" + "ʼ" + "a" + "́"  # kʼá
    plain_ejective = "p" + "ʼ" + "a"  # pʼa
    sentence = f"{tonal_ejective} {plain_ejective}"
    client_for_word = engine_selection.auto_client_for_word(sentence, ["espeak", "sapi"])

    c1 = client_for_word(tonal_ejective)
    c2 = client_for_word(plain_ejective)
    assert c1 is c2  # one shared client for the whole eSpeak-assigned group
    assert c1.tones is True  # switched to the Mandarin voice because *a* word in its group needed it
    assert c1.voice == "cmn"


def test_auto_client_for_word_keeps_engines_independent_across_groups():
    # "pata" (exact under both, naturalness picks SAPI) alongside "kʼa"
    # (forced onto eSpeak) -- two different engines, two different
    # clients, each resolved against only its own assigned words.
    sentence = "pata kʼa"
    client_for_word = engine_selection.auto_client_for_word(sentence, ["espeak", "sapi"])
    sapi_client = client_for_word("pata")
    espeak_client = client_for_word("kʼa")
    assert type(sapi_client).__name__ == "SapiTTSClient"
    assert type(espeak_client).__name__ == "EspeakTTSClient"


def test_auto_pronunciation_warnings_reports_no_engine_available():
    warnings = engine_selection.auto_pronunciation_warnings("pata", [])
    assert len(warnings) == 1
    assert "pata" in warnings[0] and "No TTS engine" in warnings[0]


def test_auto_pronunciation_warnings_reports_an_approximate_word_but_not_an_exact_one():
    warnings = engine_selection.auto_pronunciation_warnings("pata kʼa", ["espeak", "sapi"])
    assert len(warnings) == 1
    assert "kʼa" in warnings[0]
    assert "pata" not in warnings[0]


def test_auto_pronunciation_warnings_deduplicates_repeated_words():
    warnings = engine_selection.auto_pronunciation_warnings("kʼa kʼa", ["espeak", "sapi"])
    assert len(warnings) == 1
