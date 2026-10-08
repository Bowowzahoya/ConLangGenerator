"""Tests for speech.tts_cache.CachingTTSClient -- the content-addressed
audio cache wrapping a real TTSClient, keyed on (engine identity, IPA
text) rather than text alone."""

from pathlib import Path

from conlang_generator.speech import tts, tts_cache


class _FakeClient:
    """A minimal TTSClient double that counts real synthesis calls, so
    tests can tell a cache hit apart from a fresh synthesis without
    depending on a real backend being installed."""

    def __init__(self, identity: str = "fake") -> None:
        self.identity = identity
        self.calls = 0

    def synthesize(self, ipa_text: str, output_path: Path) -> bool:
        self.calls += 1
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(f"{self.identity}:{ipa_text}".encode("utf-8"))
        return True

    def capabilities(self):
        return tts.TTSCapabilities("Fake", frozenset(), ())

    def for_utterance(self, ipa_text: str) -> "_FakeClient":
        return self

    def cache_identity(self) -> str:
        return self.identity


def test_a_second_synthesize_call_is_served_from_cache_not_resynthesized(tmp_path: Path):
    fake = _FakeClient()
    client = tts_cache.CachingTTSClient(fake, tmp_path / "cache")
    out1, out2 = tmp_path / "out1.wav", tmp_path / "out2.wav"

    assert client.synthesize("kat", out1) is True
    assert client.synthesize("kat", out2) is True
    assert fake.calls == 1  # the second call hit the cache, not the real client
    assert out1.read_bytes() == out2.read_bytes()


def test_different_ipa_text_is_not_conflated(tmp_path: Path):
    fake = _FakeClient()
    client = tts_cache.CachingTTSClient(fake, tmp_path / "cache")
    out1, out2 = tmp_path / "out1.wav", tmp_path / "out2.wav"

    client.synthesize("kat", out1)
    client.synthesize("mat", out2)
    assert fake.calls == 2
    assert out1.read_bytes() != out2.read_bytes()


def test_different_engine_identity_is_not_conflated_even_for_the_same_text(tmp_path: Path):
    # Same IPA text, two different "engines" (e.g. eSpeak vs. eSpeak's own
    # Mandarin voice) -- must not share a cache entry.
    cache_dir = tmp_path / "cache"
    client_a = tts_cache.CachingTTSClient(_FakeClient("engine-a"), cache_dir)
    client_b = tts_cache.CachingTTSClient(_FakeClient("engine-b"), cache_dir)
    out_a, out_b = tmp_path / "a.wav", tmp_path / "b.wav"

    client_a.synthesize("kat", out_a)
    client_b.synthesize("kat", out_b)
    assert out_a.read_bytes() != out_b.read_bytes()


def test_a_failed_synthesis_is_not_cached(tmp_path: Path):
    class _AlwaysFails:
        def synthesize(self, ipa_text, output_path):
            return False

        def cache_identity(self):
            return "fails"

    cache_dir = tmp_path / "cache"
    client = tts_cache.CachingTTSClient(_AlwaysFails(), cache_dir)
    assert client.synthesize("kat", tmp_path / "out.wav") is False
    assert not cache_dir.exists() or not list(cache_dir.glob("*.wav"))


def test_for_utterance_keeps_the_result_wrapped_in_caching(tmp_path: Path):
    fake = _FakeClient()
    client = tts_cache.CachingTTSClient(fake, tmp_path / "cache")
    result = client.for_utterance("kat")
    assert isinstance(result, tts_cache.CachingTTSClient)
    assert result.cache_identity() == "fake"


def test_capabilities_and_cache_identity_delegate_to_the_wrapped_client(tmp_path: Path):
    fake = _FakeClient("espeak:en-us:False")
    client = tts_cache.CachingTTSClient(fake, tmp_path / "cache")
    assert client.capabilities().label == "Fake"
    assert client.cache_identity() == "espeak:en-us:False"


def test_real_espeak_client_round_trips_through_the_cache(tmp_path: Path):
    if tts._find_espeak_ng() is None:
        import pytest

        pytest.skip("espeak-ng not installed on this machine")
    client = tts_cache.CachingTTSClient(tts.build_tts_client("espeak"), tmp_path / "cache")
    out1, out2 = tmp_path / "out1.wav", tmp_path / "out2.wav"
    assert client.synthesize("kat", out1) is True
    assert client.synthesize("kat", out2) is True
    assert out1.read_bytes() == out2.read_bytes()
    assert len(list((tmp_path / "cache").glob("*.wav"))) == 1
