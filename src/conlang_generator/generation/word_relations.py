"""A small, hand-curated table of real English word relatedness: which gloss is built from which
other one(s), and how -- the ``"algorithmic"`` (no-LLM) source for ``derivation_gen``'s word-
formation mechanism (``core.traits.TraitProfile.compound_likelihood``), an alternative to asking the
configured LLM the same question (``GenerationSpec.word_formation == "llm"``).

Scoped deliberately small and entirely real rather than large and partly guessed (direct user
confirmation after being asked): every entry here is a genuine, citable English relationship, not
a plausible-sounding invention. Two halves:

- Relations *within* ``lexicon_gen.ALL_MEANINGS`` (both the derived word and its base(s) are
  themselves one of the ~496 core/extended meanings) -- these are rare by construction, since
  ``ALL_MEANINGS`` was chosen for basic/Swadesh-style universality, which tends to exclude
  compound-derived concepts. Demonstrable at fresh-generation time.
- Common English compounds reaching *outside* that fixed list -- real open vocabulary a
  translation might need, used only at translation time (``translation.expansion``'s coinage path).

Growing this list further (toward the thousands) is logged as its own follow-up in
``docs/DEFERRED.md``, not attempted in this pass."""

from __future__ import annotations

from typing import NamedTuple


class WordRelation(NamedTuple):
    kind: str
    """``"compound"``: ``parts`` is (modifier gloss, head gloss), joined via
    ``GrammarProfile.compounding``. ``"derive"``: ``parts`` is a single-element tuple (the base
    gloss), transformed via ``rule`` -- one of ``derivation_gen.RULES``'s own names (``"agent"``,
    ``"abstract"``, ...) or an ``derivation_gen.ABLAUT_RULES`` name (a root-vowel change, no affix,
    the real mechanism behind "sing"/"song", "die"/"death")."""
    parts: tuple[str, ...]
    rule: str = ""


WORD_RELATIONS: dict[str, WordRelation] = {
    # --- within ALL_MEANINGS itself (generation-time demonstrable) ---
    # Common Germanic ablaut families, now mostly fossilized past recognition -- the user's own
    # original "death"/"die" example, plus "life"/"live" (a length/quality vowel difference) and
    # the textbook strong-verb case "sing"/"song" (i -> o).
    "death": WordRelation("derive", ("die",), "ablaut_v2n"),
    "life": WordRelation("derive", ("live",), "ablaut_v2n"),
    "song": WordRelation("derive", ("sing",), "ablaut_v2n"),
    "teacher": WordRelation("derive", ("teach",), "agent"),
    "hunter": WordRelation("derive", ("hunt",), "agent"),
    "truth": WordRelation("derive", ("true",), "abstract"),

    # --- common English compounds, reaching outside ALL_MEANINGS (translation-time) ---
    "understand": WordRelation("compound", ("under", "stand")),
    "moonlight": WordRelation("compound", ("moon", "light")),
    "sunlight": WordRelation("compound", ("sun", "light")),
    "sunrise": WordRelation("compound", ("sun", "rise")),
    "sunset": WordRelation("compound", ("sun", "set")),
    "sunflower": WordRelation("compound", ("sun", "flower")),
    "rainbow": WordRelation("compound", ("rain", "bow")),
    "rainfall": WordRelation("compound", ("rain", "fall")),
    "snowman": WordRelation("compound", ("snow", "man")),
    "snowfall": WordRelation("compound", ("snow", "fall")),
    "waterfall": WordRelation("compound", ("water", "fall")),
    "earthquake": WordRelation("compound", ("earth", "quake")),
    "thunderstorm": WordRelation("compound", ("thunder", "storm")),
    "football": WordRelation("compound", ("foot", "ball")),
    "basketball": WordRelation("compound", ("basket", "ball")),
    "baseball": WordRelation("compound", ("base", "ball")),
    "headache": WordRelation("compound", ("head", "ache")),
    "toothache": WordRelation("compound", ("tooth", "ache")),
    "heartbeat": WordRelation("compound", ("heart", "beat")),
    "heartbreak": WordRelation("compound", ("heart", "break")),
    "homeland": WordRelation("compound", ("home", "land")),
    "homework": WordRelation("compound", ("home", "work")),
    "homesick": WordRelation("compound", ("home", "sick")),
    "birthday": WordRelation("compound", ("birth", "day")),
    "birthplace": WordRelation("compound", ("birth", "place")),
    "lifetime": WordRelation("compound", ("life", "time")),
    "daylight": WordRelation("compound", ("day", "light")),
    "daytime": WordRelation("compound", ("day", "time")),
    "nighttime": WordRelation("compound", ("night", "time")),
    "midnight": WordRelation("compound", ("mid", "night")),
    "seashell": WordRelation("compound", ("sea", "shell")),
    "seaside": WordRelation("compound", ("sea", "side")),
    "seashore": WordRelation("compound", ("sea", "shore")),
    "countryside": WordRelation("compound", ("country", "side")),
    "horseback": WordRelation("compound", ("horse", "back")),
    "horsepower": WordRelation("compound", ("horse", "power")),
    "cowboy": WordRelation("compound", ("cow", "boy")),
    "fireplace": WordRelation("compound", ("fire", "place")),
    "firefly": WordRelation("compound", ("fire", "fly")),
    "firewood": WordRelation("compound", ("fire", "wood")),
    "fireworks": WordRelation("compound", ("fire", "work")),
    "fishhook": WordRelation("compound", ("fish", "hook")),
    "fisherman": WordRelation("compound", ("fish", "man")),
    "farmland": WordRelation("compound", ("farm", "land")),
    "farmhouse": WordRelation("compound", ("farm", "house")),
    "farmyard": WordRelation("compound", ("farm", "yard")),
    "doorway": WordRelation("compound", ("door", "way")),
    "doorstep": WordRelation("compound", ("door", "step")),
    "gateway": WordRelation("compound", ("gate", "way")),
    "roadside": WordRelation("compound", ("road", "side")),
    "hillside": WordRelation("compound", ("hill", "side")),
    "riverbank": WordRelation("compound", ("river", "bank")),
    "riverbed": WordRelation("compound", ("river", "bed")),
    "woodland": WordRelation("compound", ("wood", "land")),
    "grassland": WordRelation("compound", ("grass", "land")),
    "wasteland": WordRelation("compound", ("waste", "land")),
    "mainland": WordRelation("compound", ("main", "land")),
    "highland": WordRelation("compound", ("high", "land")),
    "lowland": WordRelation("compound", ("low", "land")),
    "upland": WordRelation("compound", ("up", "land")),
    "wetland": WordRelation("compound", ("wet", "land")),
    "landlord": WordRelation("compound", ("land", "lord")),
    "landmark": WordRelation("compound", ("land", "mark")),
    "landslide": WordRelation("compound", ("land", "slide")),
    "windmill": WordRelation("compound", ("wind", "mill")),
    "windpipe": WordRelation("compound", ("wind", "pipe")),
    "windstorm": WordRelation("compound", ("wind", "storm")),
    "snowstorm": WordRelation("compound", ("snow", "storm")),
    "rainstorm": WordRelation("compound", ("rain", "storm")),
    "sandstorm": WordRelation("compound", ("sand", "storm")),
    "handshake": WordRelation("compound", ("hand", "shake")),
    "handwriting": WordRelation("compound", ("hand", "write")),
    "handbook": WordRelation("compound", ("hand", "book")),
    "handmade": WordRelation("compound", ("hand", "make")),
    "footstep": WordRelation("compound", ("foot", "step")),
    "footpath": WordRelation("compound", ("foot", "path")),
    "footprint": WordRelation("compound", ("foot", "print")),
    "footnote": WordRelation("compound", ("foot", "note")),
    "headline": WordRelation("compound", ("head", "line")),
    "headlight": WordRelation("compound", ("head", "light")),
    "headmaster": WordRelation("compound", ("head", "master")),
    "haircut": WordRelation("compound", ("hair", "cut")),
    "eyesight": WordRelation("compound", ("eye", "sight")),
    "eyebrow": WordRelation("compound", ("eye", "brow")),
    "eyelash": WordRelation("compound", ("eye", "lash")),
    "eyelid": WordRelation("compound", ("eye", "lid")),
    "eyeball": WordRelation("compound", ("eye", "ball")),
    "toothbrush": WordRelation("compound", ("tooth", "brush")),
    "toothpick": WordRelation("compound", ("tooth", "pick")),
    "heartland": WordRelation("compound", ("heart", "land")),
    "bloodshed": WordRelation("compound", ("blood", "shed")),
    "bloodline": WordRelation("compound", ("blood", "line")),
    "skinfold": WordRelation("compound", ("skin", "fold")),
    "backbone": WordRelation("compound", ("back", "bone")),
    "backyard": WordRelation("compound", ("back", "yard")),
    "background": WordRelation("compound", ("back", "ground")),
    "backward": WordRelation("compound", ("back", "ward")),
    "forward": WordRelation("compound", ("fore", "ward")),
    "afterlife": WordRelation("compound", ("after", "life")),
    "afternoon": WordRelation("compound", ("after", "noon")),
    "overnight": WordRelation("compound", ("over", "night")),
    "overcome": WordRelation("compound", ("over", "come")),
    "overthrow": WordRelation("compound", ("over", "throw")),
    "outside": WordRelation("compound", ("out", "side")),
    "inside": WordRelation("compound", ("in", "side")),
    "upside": WordRelation("compound", ("up", "side")),
    "downside": WordRelation("compound", ("down", "side")),
    "downfall": WordRelation("compound", ("down", "fall")),
    "downstream": WordRelation("compound", ("down", "stream")),
    "upstream": WordRelation("compound", ("up", "stream")),
    "upbringing": WordRelation("compound", ("up", "bring")),
    "uproot": WordRelation("compound", ("up", "root")),
    "withhold": WordRelation("compound", ("with", "hold")),
    "withdraw": WordRelation("compound", ("with", "draw")),
    "warship": WordRelation("compound", ("war", "ship")),
    "warpath": WordRelation("compound", ("war", "path")),
    "warlord": WordRelation("compound", ("war", "lord")),
    "lawmaker": WordRelation("compound", ("law", "make")),
    "lawsuit": WordRelation("compound", ("law", "suit")),
    "storyteller": WordRelation("compound", ("story", "tell")),
    "songbird": WordRelation("compound", ("song", "bird")),
    "songwriter": WordRelation("compound", ("song", "write")),
    "lifeblood": WordRelation("compound", ("life", "blood")),
    "lifelong": WordRelation("compound", ("life", "long")),
    "lifelike": WordRelation("compound", ("life", "like")),
    "friendship": WordRelation("compound", ("friend", "ship")),
}
