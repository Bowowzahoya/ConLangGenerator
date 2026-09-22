"""Pronunciation engines list what they can voice and warn about tones they
can't; eSpeak voices tones through its Mandarin voice; tone sandhi is
probabilistic and a graded trait."""

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from conlang_generator.core.phonology import TONE_CONTOURS, TONE_DIACRITICS, ToneLevel, ToneSandhiRule
from conlang_generator.core.traits import GRADED_TRAIT_FIELDS, TraitProfile
from conlang_generator.generation import phonology_gen
from conlang_generator.generation.reference_languages import match_profiles_weighted
from conlang_generator.speech import ipa_to_kirshenbaum, tts
from conlang_generator.webui.app import app

_THIRD = ToneSandhiRule(before=ToneLevel.DIPPING, after=ToneLevel.DIPPING, becomes=ToneLevel.RISING)
_MANDARIN_LEVELS = (
    ToneLevel.HIGH, ToneLevel.RISING, ToneLevel.DIPPING, ToneLevel.FALLING, ToneLevel.NEUTRAL,
)


def _tone(base: str, level: ToneLevel) -> str:
    return base + TONE_DIACRITICS[level]


# --- capabilities and warnings ---------------------------------------------


def test_each_engine_lists_what_it_can_and_cannot_voice():
    caps = tts.backend_capabilities()
    assert set(caps) == {"none", "espeak", "sapi"}
    assert set(caps["espeak"]["tones"]) == {level.value for level in ToneLevel}
    assert caps["sapi"]["tones"] == [] and caps["none"]["tones"] == []
    assert all(entry["notes"] for entry in caps.values())


def test_a_tone_the_engine_cannot_voice_is_reported_and_others_are_not():
    ipa = _tone("ma", ToneLevel.DIPPING) + " " + _tone("ta", ToneLevel.HIGH)
    sapi = tts.build_tts_client("sapi").capabilities()
    warning = tts.pronunciation_warnings(sapi, ipa)
    assert len(warning) == 1 and "dipping" in warning[0] and "high" in warning[0] and "Windows SAPI" in warning[0]
    assert tts.pronunciation_warnings(tts.build_tts_client("espeak").capabilities(), ipa) == []
    assert tts.pronunciation_warnings(sapi, "mata") == []  # no tones, nothing to warn about
    partial = tts.TTSCapabilities("Partial", frozenset({ToneLevel.HIGH}), ())
    assert "dipping" in tts.pronunciation_warnings(partial, ipa)[0] and "high" not in tts.pronunciation_warnings(partial, ipa)[0]


def test_the_web_api_lists_capabilities_and_checks_a_translation():
    client = TestClient(app)
    options = client.get("/api/options").json()
    assert set(options["tts_capabilities"]) == {"none", "espeak", "sapi"}
    ipa = _tone("ma", ToneLevel.FALLING)
    sapi = client.post("/api/pronunciation-check", json={"ipa": ipa, "tts": "sapi"}).json()
    assert sapi["warnings"] and sapi["capabilities"]["label"] == "Windows SAPI"
    assert client.post("/api/pronunciation-check", json={"ipa": ipa, "tts": "espeak"}).json()["warnings"] == []
    assert client.post("/api/pronunciation-check", json={"ipa": ipa, "tts": "none"}).json()["warnings"] == []
    assert client.post("/api/pronunciation-check", json={"ipa": ipa, "tts": "bogus"}).status_code == 400


# --- the eSpeak tone path ---------------------------------------------------


def test_convert_word_appends_contour_digits_only_when_asked():
    word = _tone("ma", ToneLevel.DIPPING)
    assert ipa_to_kirshenbaum.convert_word(word) == ipa_to_kirshenbaum.convert_word("ma")
    with_tones = ipa_to_kirshenbaum.convert_word(word, {ToneLevel.DIPPING: "214"})
    assert with_tones == ipa_to_kirshenbaum.convert_word("ma") + "214"
    two = ipa_to_kirshenbaum.convert_word(_tone("ma", ToneLevel.HIGH) + _tone("ta", ToneLevel.FALLING), tts._ESPEAK_TONE_NUMBERS)
    assert two.count("55") == 1 and two.count("51") == 1


def test_espeak_tone_numbers_is_the_same_canonical_contour_data_everywhere_else():
    # Contour representation: this engine's own pitch-contour digits used
    # to be a private, eSpeak-specific table; now they're sourced from
    # core.phonology.TONE_CONTOURS, the same real Chao pitch-level numbers
    # chao_letters()/reader.describe() use for display -- one real fact,
    # not two tables that could quietly drift apart.
    assert tts._ESPEAK_TONE_NUMBERS is TONE_CONTOURS


def test_espeak_voices_a_tonal_word_with_its_mandarin_voice_and_tone_digits(monkeypatch, tmp_path):
    seen = []

    def fake_run(args, **kwargs):
        seen.append(args)
        Path(args[args.index("-w") + 1]).write_bytes(b"RIFF")
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(tts, "_find_espeak_ng", lambda: "espeak-ng")
    monkeypatch.setattr(tts.subprocess, "run", fake_run)
    client = tts.build_tts_client("espeak")
    assert client.synthesize(_tone("ma", ToneLevel.FALLING), tmp_path / "a.wav")
    assert client.synthesize("ma", tmp_path / "b.wav")
    tonal, plain = seen
    assert tonal[tonal.index("-v") + 1] == "cmn" and tonal[-1].endswith("51]]")
    assert plain[plain.index("-v") + 1] == "en-us" and "51" not in plain[-1]


def test_a_tonal_sentence_keeps_one_voice_for_every_word():
    tonal = _tone("ma", ToneLevel.HIGH) + " " + "ta"
    client = tts.build_tts_client("espeak")
    assert client.for_utterance(tonal).voice == "cmn" and client.for_utterance(tonal).tones
    assert client.for_utterance("mata") is client
    assert tts.build_tts_client("sapi").for_utterance(tonal).capabilities().label == "Windows SAPI"


def test_sapi_removes_tone_marks_so_a_tonal_word_is_still_spoken(monkeypatch, tmp_path):
    scripts = []

    def fake_run(args, **kwargs):
        scripts.append(args[-1])
        out = tmp_path / "s.wav"
        out.write_bytes(b"\x00" * 100)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(tts.sys, "platform", "win32")
    monkeypatch.setattr(tts.subprocess, "run", fake_run)
    assert tts.build_tts_client("sapi").synthesize(_tone("ma", ToneLevel.RISING), tmp_path / "s.wav")
    assert not any(ch in scripts[0] for ch in TONE_DIACRITICS.values())


# --- probabilistic sandhi ---------------------------------------------------


def _resolve(strictness, strength, seed, profiles="Mandarin", levels=_MANDARIN_LEVELS):
    weighted = match_profiles_weighted((profiles,), ()) if profiles else ()
    return phonology_gen.resolve_tone_sandhi(levels, weighted, strictness, strength, seed)


def test_full_strictness_always_keeps_the_real_sandhi_whatever_the_trait():
    for seed in range(60):
        assert _resolve(1.0, 0.0, seed) == (_THIRD,)
        assert _resolve(1.0, -1.0, seed) == (_THIRD,)


def test_lower_strictness_sometimes_drops_the_real_rule_and_sometimes_swaps_in_a_different_one():
    outcomes = [_resolve(0.4, 0.0, seed) for seed in range(400)]
    kept = sum(o == (_THIRD,) for o in outcomes)
    none = sum(o == () for o in outcomes)
    different = sum(bool(o) and _THIRD not in o for o in outcomes)
    assert 0.25 * 400 < kept < 0.55 * 400  # about the strictness (0.4)
    assert none > 0.2 * 400 and different > 0.03 * 400
    assert kept + none + different == 400


def test_strictness_zero_has_no_real_rule_and_the_trait_moves_the_odds():
    def rate(strength, profile):
        return sum(bool(_resolve(0.0, strength, seed, profile)) for seed in range(400)) / 400

    # at strictness 0 the real rule only turns up when an invented rule happens to coincide with it
    assert sum(_THIRD in _resolve(0.0, 0.0, seed) for seed in range(200)) < 8
    assert rate(1.0, None) == 1.0  # a strongly sandhi-friendly tonal language always invents one
    assert rate(-1.0, None) == 0.0  # explicitly none
    assert 0.05 < rate(0.0, None) < 0.3  # the world-typical rate
    assert rate(0.8, "Mandarin") > rate(0.0, "Mandarin") > rate(-0.8, "Mandarin") - 1e-9


def test_invented_rules_only_use_the_languages_own_tones_and_never_map_a_tone_to_itself():
    levels = (ToneLevel.LOW, ToneLevel.MID, ToneLevel.HIGH)
    for seed in range(100):
        for rule in _resolve(0.0, 1.0, seed, None, levels):
            assert {rule.before, rule.after, rule.becomes} <= set(levels)
            assert rule.becomes is not rule.before


def test_sandhi_decisions_do_not_disturb_the_main_generation_draws():
    import random

    from conlang_generator.core.spec import GenerationSpec

    def inventory(strength):
        traits = TraitProfile(source_languages=("Mandarin",), source_language_strictness=0.6, tone_sandhi=strength)
        spec = GenerationSpec(prompt="p", seed=11, traits=traits)
        inv, structure, _, _ = phonology_gen.generate_phonology(random.Random(11), spec)
        return inv.consonant_symbols(), inv.vowel_symbols(), structure

    assert inventory(-1.0) == inventory(1.0)


def test_tone_sandhi_is_a_graded_trait_the_classifier_reads():
    assert "tone_sandhi" in GRADED_TRAIT_FIELDS
    assert TraitProfile().tone_sandhi == 0.0
    from conlang_generator.generation.prompt_classifier import classify_prompt
    from conlang_generator.llm.base import LLMResponse

    class _Fixed:
        def complete(self, request):
            return LLMResponse(text='{"tone_sandhi": 0.7}', model="stub", input_tokens=1, output_tokens=1)

    assert classify_prompt("a tonal language where tones shift a lot", False, _Fixed()).tone_sandhi == 0.7
