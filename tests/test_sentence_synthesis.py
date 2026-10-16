"""Tests for speech.sentence_synthesis -- stitching several words' own
separately-synthesized .wav files into one combined sentence recording.
Shared by webui/app.py's /api/pronounce and cli/main.py's translate
--tts; these tests exercise the module directly, with no FastAPI/web
optional-dependency involved."""

import io
import wave

from conlang_generator.speech import sentence_synthesis

_FRAMERATE, _SAMPWIDTH, _NCHANNELS = 16000, 2, 1
_WORD_FRAMES = 100


class _FixedLengthClient:
    """A controllable fake client with a known frame count, so the exact
    silence-insertion byte math is checkable without depending on a real
    backend's own word-length variance."""

    def synthesize(self, ipa_text, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as wf:
            wf.setnchannels(_NCHANNELS)
            wf.setsampwidth(_SAMPWIDTH)
            wf.setframerate(_FRAMERATE)
            wf.writeframes(b"\x01\x00" * _WORD_FRAMES)
        return True


class _AlwaysFailsClient:
    def synthesize(self, ipa_text, output_path):
        return False


def test_synthesize_sentence_inserts_exactly_one_inter_word_silence_gap(tmp_path):
    # DEFERRED.md: the old 0.15s gap was reported as too long and
    # shortened to INTER_WORD_SILENCE_SECONDS.
    audio = sentence_synthesis.synthesize_sentence(lambda _w: _FixedLengthClient(), "kat mat", tmp_path)
    assert audio is not None
    with wave.open(io.BytesIO(audio), "rb") as wf:
        total_frames = wf.getnframes()
    silence_frames = int(sentence_synthesis.INTER_WORD_SILENCE_SECONDS * _FRAMERATE)
    assert total_frames == 2 * _WORD_FRAMES + silence_frames


def test_synthesize_sentence_returns_none_for_an_empty_sentence(tmp_path):
    assert sentence_synthesis.synthesize_sentence(lambda _w: _FixedLengthClient(), "", tmp_path) is None
    assert sentence_synthesis.synthesize_sentence(lambda _w: _FixedLengthClient(), "   ", tmp_path) is None


def test_synthesize_sentence_skips_a_failing_word_and_still_renders_the_rest(tmp_path):
    def client_for_word(word):
        return _AlwaysFailsClient() if word == "bad" else _FixedLengthClient()

    audio = sentence_synthesis.synthesize_sentence(client_for_word, "kat bad mat", tmp_path)
    assert audio is not None
    with wave.open(io.BytesIO(audio), "rb") as wf:
        total_frames = wf.getnframes()
    # Only the 2 successful words contribute frames + one silence gap
    # between them -- the failing middle word contributes nothing.
    silence_frames = int(sentence_synthesis.INTER_WORD_SILENCE_SECONDS * _FRAMERATE)
    assert total_frames == 2 * _WORD_FRAMES + silence_frames


def test_synthesize_sentence_returns_none_when_every_word_fails(tmp_path):
    audio = sentence_synthesis.synthesize_sentence(lambda _w: _AlwaysFailsClient(), "kat mat", tmp_path)
    assert audio is None


def test_synthesize_sentence_cleans_up_its_temp_files(tmp_path):
    sentence_synthesis.synthesize_sentence(lambda _w: _FixedLengthClient(), "kat mat", tmp_path)
    assert list(tmp_path.iterdir()) == []
