"""The extended core vocabulary: ~445 further basic meanings beyond the
original 51 in ``lexicon_gen.CORE_MEANINGS`` (which stays exactly as it was,
since ``experiments/`` scripts index real-language lexicons against its
order); ``lexicon_gen.ALL_MEANINGS`` is the two concatenated (~496).
Chosen in the same Swadesh/Leipzig-Jakarta-style basic-vocabulary spirit as
the original list -- function words, basic actions and qualities, body
parts, nature, animals, kin and society, food, everyday objects, abstract
nouns -- ordered roughly by how basic each group is (see ``_ORDER``), so
``GenerationSpec.vocabulary_size`` (a prefix of ``ALL_MEANINGS``) always
keeps the most fundamental words and drops the least basic nouns first.
Glosses are unique across both lists.
"""

from __future__ import annotations

from conlang_generator.core.lexicon import PartOfSpeech

_N, _V, _ADJ, _PRO, _NUM, _PART = (
    PartOfSpeech.NOUN, PartOfSpeech.VERB, PartOfSpeech.ADJECTIVE,
    PartOfSpeech.PRONOUN, PartOfSpeech.NUMERAL, PartOfSpeech.PARTICLE,
)

_GROUPS: tuple[tuple[PartOfSpeech, str], ...] = (
    (_PRO, "she it they who what"),
    (_NUM, "four five six seven eight nine ten hundred thousand"),
    (_N, "head hair face ear nose mouth tooth tongue neck arm leg foot finger nail skin blood bone heart belly "
         "back knee liver lip horn tail feather wing egg fat flesh brain breast shoulder"),
    (_N, "earth sky cloud star sea river lake island forest leaf root branch seed flower fruit grass sand dust "
         "ash smoke snow ice night day year month morning evening road path field hill valley cave salt iron "
         "gold silver wood storm thunder lightning shadow light air heat"),
    (_N, "dog cat horse cow pig sheep goat snake mouse rabbit wolf bear deer insect worm ant spider frog turtle "
         "monkey elephant lion"),
    (_N, "man woman boy girl brother sister friend enemy king chief teacher hunter farmer village town house door "
         "roof wall bed family god spirit song story word law war peace money gift game dream death life"),
    (_N, "food bread meat milk rice honey oil wine sugar soup vegetable"),
    (_N, "knife spear bow arrow axe stick boat ship wheel pot cup bowl basket net cloth shoe hat ring key book "
         "letter picture mirror lamp tool bag box bridge gate rope"),
    (_N, "thing place time way part number side end top bottom middle center edge reason question "
         "news voice sound color shape size weight age power truth luck"),
    (_V, "have do make take put get find want need like love hate fear think believe remember forget understand "
         "learn teach tell ask answer call speak hear listen look watch show smell taste touch feel laugh cry "
         "sing dance play work walk run jump swim fly climb fall sit stand lie turn push pull throw catch hold "
         "carry bring send open close break cut tear tie dig burn cook wash wipe sew build plant grow die live "
         "kill fight hunt hit wound bite suck blow breathe cough vomit spit swell freeze flow shine rise begin "
         "stop wait stay leave arrive return follow lead meet join split divide count measure weigh buy sell "
         "pay steal share choose try help use wear wake"),
    (_ADJ, "long short wide narrow thick thin heavy fast slow strong weak young dry wet full empty clean dirty "
           "dead alive sharp dull smooth rough round straight red green blue yellow black white brown sweet sour "
           "bitter right left near far happy sad angry afraid hungry thirsty tired sick rich poor beautiful ugly "
           "easy hard true false same different quiet loud soft warm cool deep shallow dark bright free brave "
           "wise foolish kind cruel strange ready holy"),
    (_PART, "in on at to from with without for of about between under over through before after if because "
            "when where how why also only very all many few some other each every"),
)


_ORDER = (0, 1, 11, 9, 10, 2, 3, 4, 5, 6, 7, 8)
"""Indices into ``_GROUPS``: pronouns, numerals, particles/prepositions,
verbs, adjectives, then the noun groups (body, nature, animals, people,
food, objects, abstract)."""


def _build() -> tuple[tuple[str, PartOfSpeech], ...]:
    entries: list[tuple[str, PartOfSpeech]] = []
    for index in _ORDER:
        pos, words = _GROUPS[index]
        for word in words.split():
            entries.append((word, pos))
    return tuple(entries)


EXTENDED_MEANINGS: tuple[tuple[str, PartOfSpeech], ...] = _build()
