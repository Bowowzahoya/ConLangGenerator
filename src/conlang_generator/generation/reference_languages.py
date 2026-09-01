"""A small, hand-curated set of real languages' rough phonological
profiles, used to bias generation toward "sounds like X" / "mix of X and
Y" when ``TraitProfile.contact_languages`` names one we recognize.

Symbol sets are restricted to symbols already in ``phonology_gen.py``'s
pools (so matching against a generated inventory is a plain set
intersection). These are illustrative typological sketches for flavor, not
authoritative phonological descriptions -- real language phonology is far
richer than what our own symbol pool and phonotactic model can represent
(no aspiration, length, or pharyngealization contrasts; no noun-class or
root-and-pattern morphology, etc.).

Nine languages, chosen for typological spread rather than exhaustiveness:
CV-only/no-clusters (Japanese, Hawaiian), strong vowel harmony (Finnish),
tonal (Mandarin), pharyngeal/uvular (Arabic), ejective/cluster-heavy
(Georgian), clicks (a Nguni-family stand-in), a Romance stand-in, and Dutch
(a rich-vowel, complex-coda/cluster Germanic language).
"""

from __future__ import annotations

from pydantic import BaseModel


class ReferenceLanguageProfile(BaseModel, frozen=True):
    name: str
    aliases: tuple[str, ...] = ()
    consonants: tuple[str, ...]
    vowels: tuple[str, ...]
    coda_profile: str  # "none" | "sonorant" | "unrestricted"
    max_onset: int
    tonal: bool
    vowel_harmony: bool = False

    def symbols(self) -> frozenset[str]:
        return frozenset(self.consonants) | frozenset(self.vowels)


REFERENCE_LANGUAGES: tuple[ReferenceLanguageProfile, ...] = (
    ReferenceLanguageProfile(
        name="Japanese",
        consonants=("p", "b", "t", "d", "k", "g", "tʃ", "dʒ", "ʔ", "m", "n", "s", "ʃ", "h", "z", "ɾ", "j", "w"),
        vowels=("i", "a", "u", "e", "o"),
        coda_profile="sonorant",
        max_onset=1,
        tonal=False,
    ),
    ReferenceLanguageProfile(
        name="Finnish",
        consonants=("p", "t", "k", "d", "m", "n", "ŋ", "s", "h", "l", "r", "j", "v"),
        vowels=("i", "a", "u", "e", "o", "y", "ø", "æ"),
        coda_profile="unrestricted",
        max_onset=1,
        tonal=False,
        vowel_harmony=True,
    ),
    ReferenceLanguageProfile(
        name="Mandarin",
        aliases=("chinese", "mandarin chinese"),
        consonants=("p", "t", "k", "tʃ", "ʈ", "ʂ", "ʐ", "m", "n", "ŋ", "f", "s", "ʃ", "x", "l", "j", "w"),
        vowels=("i", "a", "u", "e", "o"),
        coda_profile="sonorant",
        max_onset=1,
        tonal=True,
    ),
    ReferenceLanguageProfile(
        name="Arabic",
        aliases=("modern standard arabic",),
        consonants=("t", "d", "k", "q", "ʔ", "tʃ", "m", "n", "s", "ʃ", "x", "z", "f", "h", "ħ", "ʕ", "l", "r", "j", "w"),
        vowels=("i", "a", "u"),
        coda_profile="unrestricted",
        max_onset=1,
        tonal=False,
    ),
    ReferenceLanguageProfile(
        name="Hawaiian",
        consonants=("p", "k", "ʔ", "h", "m", "n", "l", "w"),
        vowels=("i", "a", "u", "e", "o"),
        coda_profile="none",
        max_onset=1,
        tonal=False,
    ),
    ReferenceLanguageProfile(
        name="Georgian",
        consonants=("p", "b", "t", "d", "k", "g", "tʃ", "dʒ", "pʼ", "tʼ", "kʼ", "q", "m", "n", "s", "ʃ", "x", "z", "ʒ", "v", "l", "r", "j", "w"),
        vowels=("i", "a", "u", "e", "o"),
        coda_profile="unrestricted",
        max_onset=2,
        tonal=False,
    ),
    ReferenceLanguageProfile(
        name="Xhosa",
        aliases=("zulu", "click language", "nguni"),
        consonants=("p", "b", "t", "d", "k", "g", "tʃ", "dʒ", "ʔ", "m", "n", "ŋ", "s", "ʃ", "h", "z", "l", "j", "w", "ǀ", "ǃ", "ǂ", "ǁ"),
        vowels=("i", "a", "u", "e", "o"),
        coda_profile="sonorant",
        max_onset=1,
        tonal=True,
    ),
    ReferenceLanguageProfile(
        name="Spanish",
        aliases=("italian", "romance", "romance language"),
        consonants=("p", "b", "t", "d", "k", "g", "tʃ", "m", "n", "s", "f", "h", "l", "ɾ", "r", "j", "w"),
        vowels=("i", "a", "u", "e", "o"),
        coda_profile="unrestricted",
        max_onset=2,
        tonal=False,
    ),
    ReferenceLanguageProfile(
        name="Dutch",
        aliases=("nederlands",),
        consonants=("p", "b", "t", "d", "k", "f", "v", "s", "z", "x", "h", "m", "n", "ŋ", "l", "r", "w", "j"),
        vowels=("i", "ɪ", "e", "ɛ", "a", "ɑ", "ɔ", "o", "u", "y", "ø", "œ", "ə"),
        coda_profile="unrestricted",
        max_onset=2,
        tonal=False,
    ),
)


def match_profiles(names: tuple[str, ...]) -> tuple[ReferenceLanguageProfile, ...]:
    """Case-insensitive match against name+aliases; unknown names are
    silently ignored (best-effort, same spirit as everything else
    ``contact_languages`` touches)."""
    matched = []
    for raw_name in names:
        needle = raw_name.strip().lower()
        for profile in REFERENCE_LANGUAGES:
            if needle == profile.name.lower() or needle in profile.aliases:
                matched.append(profile)
                break
    return tuple(matched)
