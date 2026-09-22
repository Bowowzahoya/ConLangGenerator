# Lexicon audit

`conlang audit-lexicons [LANGUAGE ...] [--examples N] [--fail-above RATE]`
(`generation/reference_languages/lexicon_audit.py`) checks every curated real
word against its language's own reference profile:

* **off-profile** -- the word uses a sound the profile does not list;
* **structure** -- all its sounds are listed, but with the profile's own
  phonotactics (max onset/coda, allowed clusters, restricted onset/coda
  consonants, onset+nucleus and nucleus+coda pairs) the word is not a legal
  one. The structure is a strict-source-language phonology generation; a
  profile with no curated clusters gets the full sonority-legal cluster
  closure instead of a randomly thinned one.

Sounds are read relative to the profile: a pool symbol such as prenasalized
`nd` is read as `n` + `d` unless the profile lists it (so Italian *andare* is
not audited as having a prenasalized stop). The audit is advisory -- a flagged
word means either the transcription or the profile is wrong, and only the
language can say which.

## Stress and pitch accent in real words

A lexicon IPA string carries its stress as the usual mark `ˈ` before the stressed syllable's onset (none on a
monosyllable), the convention generated words already use (`generation/reference_languages/real_stress.py`
reads and writes it). Marks reach the language in three places: an exact copy (word strictness 1.0) keeps the
real word verbatim, stress included; a looser real-based word keeps the *position* of the real word's stress
(`real_words._with_stress`); and evolution, romanization and TTS already understand the mark.

How each language's marks were produced:

* **Fixed-pattern languages** -- stress computed from the profile's own `stress_pattern` on the real syllabification
  (maximal onset under the profile's phonotactics): Bengali, Danish, Dutch, Finnish, French (never a final schwa),
  German, Hebrew, Hungarian, Icelandic, Mongolian, Nahuatl, Norwegian, Old Norse, Pama-Nyungan, Persian, Polish,
  Quechua, Swahili, Swedish, Tamil, Turkish, Welsh -- plus Spanish and Portuguese by their coda/vowel rules with
  the written accent as an override, Latin by syllable weight, Italian penultimate with a hand-listed set of
  antepenult words, Indonesian and Malay penultimate unless the penult is schwa.
* **Five languages with a weight or position rule of their own:** Georgian (Aronson: initial in two- and
  three-syllable words, the antepenult in longer ones; whether Georgian stress is phonetically real at all is
  disputed) and Hawaiian (a right-to-left moraic trochee in which a long vowel or diphthong is a foot of its own: a
  heavy final syllable is stressed, otherwise the penult; ten listed diphthongs are one syllable), Arabic by the Cairene / Modern Standard rule
  (a superheavy final syllable, else a heavy penult, else the antepenult; a disyllable with a light penult takes its
  first -- Classical and colloquial dialects differ), Hindi by syllable weight (the heaviest of the last
  three syllables; a tie goes to the rightmost non-final one, so an all-equal word is penultimate; light = short open,
  medium = long vowel or one coda, heavy = both or two codas; nasal vowels count long, a geminate closes the syllable
  before it), and Basque by the commonly taught Central/Gipuzkoan norm (the second syllable of a word of three or more,
  the first of a disyllable) -- the Basque profile itself calls accentuation a live dialect dispute.
* **Exceptions I listed by hand:** unstressed prefixes (German/Dutch *be- ge- ver-*, Scandinavian *be- for-*), Hebrew
  segolate nouns, Turkish *anne*, *baba*, *-ında* adverbs.
* **Fully lexical languages -- curated word by word:** English (non-initial stress) and Russian (every polysyllable).
* **Japanese pitch accent:** per-syllable High/Low marks, the encoding generated Japanese words use, from Tokyo
  dictionary accent numbers in morae (a long vowel or moraic `n` adds a mora), for 424 of 454 polysyllabic words
  (93%). Fixed along the way: the reader was applying a generic Indo-European offglide-fusion rule to Japanese,
  which has none -- every written vowel is its own mora (*taiyō* "sun" is 4 morae, not 2) -- silently
  under-counting syllables and misreading pitch for any word containing a vowel-hiatus sequence the rule would
  fuse (`tests/test_real_stress.py`'s own regression test). The actually-stored marks were unaffected (the
  writer was always mora-correct); only the *reading* was wrong, so the true coverage turned out the same 91%
  it already looked like. Left unmarked rather than guessed: phrases with particles (*ni tsuite*), most
  conjugated forms, remaining homographs (*kara*) and several words whose accent I did not know (*yari*,
  *nameraka*, *horu*, *kizutsukeru*); *hana* "nose" and *hashi* "bridge" now use their gloss's own correct
  reading, distinct from their homographs *hana* "flower" and *hashi* "chopsticks".
* **Ancient Greek accent:** the project's per-syllable High/Low encoding with the circumflex as the falling mark on
  the kernel, from the accent placement of the LSJ lemma forms -- 452 of 453 polysyllabic spellings (only the phrase
  *dia ti* "why", where proclisis makes the accent a phrase-level question, is left unmarked). The circumflex follows
  the real rule (a long penult under an accent with a short final syllable; final *-ai*/*-oi* count as short), with
  hand-forced circumflexes where the lexicon does not show length (*sitos*, *mythos*, *pilos*, *pragma*, *houtos*,
  *hēmeis*). Every accent sits in the last three syllables (the trimoric law); vowel length that the lexicon does not
  write (α ι υ) limits the circumflex rule. Fixed along the way: `with_greek_accent` computed its own, separate
  "first vowel of this syllable" index instead of reusing the same nucleus list the reader uses, so any word with a
  fused diphthong offglide (*poieō*, *pisteuō*, *pauō*, *homoios*, *ploion*, ...) got its mark on the offglide instead
  of the real nucleus, leaving the true nucleus unmarked and the word unparseable -- 8 spellings affected, all among
  the ones this session's own "still unmarked" count already listed, so nothing already counted as done was wrong.
* **A systematic check for the same two bug shapes across every other curated language.** With the Greek and
  Japanese bugs fixed, every language that has *ever* been given real stress marks was re-audited for the same
  two failure modes: (a) a writer computing its own nucleus positions instead of reusing the shared reader (only
  `with_greek_accent` did this); (b) the generic vowel + high-offglide fusion rule (built for Greek/Germanic-style
  diphthongs) applied to a language that doesn't have that phonology. For (b), every curated lexicon was scanned
  for a fusable vowel sequence, and each hit checked against whether the real language actually fuses it (the same
  way the Japanese bug itself was found). Confirmed real bugs, fixed:
  - **Serbo-Croatian, Polish, Russian (Slavic: no phonemic diphthongs at all).** *pauk* "spider" (Serbo-Croatian
    and Russian, the same word) is *pa-uk*, two syllables, not one; Polish *nauczyciel* "teacher" is *na-u-czy-ciel*,
    four syllables. Both words round-tripped through this project's "stress a monosyllable never carries a mark"
    convention as silently unmarked, or (Polish) had their mark on the wrong syllable of an undercounted word.
  - **Swahili (Bantu: strict open-syllable CV structure, no diphthongs and no closed syllables at all).**
    *kusahau* "to forget" is *ku-sa-ha-u* (four syllables, not three); 14 words' stress moved to the correct
    penultimate syllable once the true syllable count was restored.
  - **Nahuatl (a plain 4-vowel system with no diphthong phonemes in the profile itself).** *maitl* "hand" is
    *ma-itl*, two syllables, not one.
  - **Two individual, named exceptions**, fixed as specific words rather than a language-wide rule (the general
    fusion behavior is correct for the rest of each language): Spanish *oír*/*reír*/*raíz*, where a written tilde
    on í/ú next to another vowel marks real hiatus, not a diphthong; Swedish *nio*/*tio* ("nine"/"ten"), a genuine
    *ni-o*/*ti-o* hiatus the generic rule wrongly fused. A hand-edited string alone would not have been enough for
    these (re-reading it would re-fuse the vowels and desync the stress index from the true syllable count), so
    `_NEVER_FUSE_WORDS` fixes the underlying read, keyed per word per language.

  **Checked and left alone** (real diphthongs, fusion is correct): Ancient Greek, Basque, Danish, Finnish,
  Hawaiian (already its own explicit pair list), Icelandic, Italian, Latin, Norwegian, Old Norse, Portuguese
  (already its own rule), Tamil (ai/au are traditional unit vowels in the Tamil vowel inventory), Thai, Welsh.

  **Not resolved, lower confidence, left as-is:** Indonesian and Malay have a large hit count (25, 23) but the
  real facts are genuinely mixed -- Indonesian *does* have real word-final /ai/, /au/, /oi/ diphthongs in most
  positions, but a handful of specific words (*air* "water" is the standard example) are known exceptions
  pronounced as hiatus; I don't have reliable per-word knowledge of which is which, and a blanket rule would
  introduce more errors than it fixes. Persian's 2 hits (*davidan*, *qahvei*) look more like a transcription
  choice (و as vowel "u" rather than consonant "v") than a fusion-rule bug, and are left alone. Bengali,
  Hebrew, Korean, Mongolian, Turkish had small hit counts (2-17) I did not have time to individually verify;
  Cantonese and Mandarin's large counts are irrelevant noise -- they are tonal languages this project's stress
  mechanism never touches (they use a separate tone-marking pipeline).
* **Danish stød and the Swedish/Norwegian word accents:** encoded as generated words carry them (the glottalization
  mark `ˀ` after the stressed syllable's rime; a High or Low diacritic on the stressed vowel). Beyond each profile's
  own shape default (Danish: a monosyllable takes stød when its syllable is heavy -- a long vowel or diphthong, or a
  short vowel + `n m ŋ l ʁ ð v j w` -- unless it is a function word; Swedish/Norwegian: accent 1 on a monosyllable or
  a word stressed on its last syllable, accent 2 otherwise), one further real, reliable rule is applied: a word whose
  *unstressed final syllable* is just a reduced vowel plus a bare `l`/`n`/`r` with no vowel of its own (*vatten*,
  *fågel*, *vinter*, *syster*, Danish *gammel*, *himmel*) is accent 1/stød -- a genuine Common Scandinavian class
  (an originally monosyllabic root + an early, tonally-inert suffix), not a guess; a handful of function words and one
  live plural that happen to share the shape (*under*, *efter*, *nyheter*) are excluded by hand since the rule is
  about root history, not shape alone. Real per-word exceptions still outside this (Swedish *anden* "duck" vs
  "spirit" -- a genuine minimal pair no shape rule can resolve; other -el/-en/-er words that are recent formations,
  not this old class; compounds; Danish stød on polysyllabic *inflected* forms, and on transcribed short vowels the
  lexicon writes without length, e.g. *træ*) are not known here. Fixing Danish's own coda-/r/-as-a-written-vowel
  quirk (*mor* /moːɐ/ was mis-syllabified as two syllables and wrongly stress-marked) turned up along the way --
  44 words corrected.
* **Serbo-Croatian:** every polysyllable now carries the four-way Neo-Stokavian accent (short/long x
  falling/rising, falling only on the first syllable) -- 151 words from the first pass, the other 233 from a
  second, hand-curated pass. **This second batch is the least reliable data in this project.** Unlike every
  other stress rule here, BCMS pitch accent is not recoverable from a word's shape or from a general position
  rule -- it is lexical, word by word, and I could not reach a source that exposes it to automated lookup
  (dictionary sites like the Hrvatski jezični portal need an interactive search a page fetch can't drive;
  Wiktionary has it for some words but not reliably, and cross-checking one word, *vrijeme*, surfaced a real
  wrinkle: this project's syllabifier treats `ije` as two vowels, which does not always match how it is
  pronounced). So the 233 are my own best recollection of standard Croatian accentuation, with a few
  systematic guesses layered in (unstressed prefixes *do- po- s- o-* usually keep the root syllable stressed;
  everything else defaults to initial, short). Expect real errors in this batch specifically -- more than
  the rest of the project's "best-effort, not linguist-verified" caveat already implies -- and treat it as a
  first pass a fluent speaker should check, not as curated data. The lexicon is the Croatian (ijekavian)
  standard.

All of it is best-effort, like the rest of the lexicons: not linguist-verified, and the fixed patterns ignore the
real exceptions (loanwords, verbs, compounds) unless listed above.

```
language        stress pattern                     marked polysyll.
Ancient Greek   positional_pitch_accent               452       453
Arabic          lexical                               365       365
Arawakan        -                                       0        42
Basque          lexical                               468       468
Bengali         initial                               393       393
Cantonese       -                                      43       133
Danish          initial                               222       222
Dutch           initial                               230       230
English         lexical                               112       114
Finnish         initial                               472       472
French          final                                 286       286
Georgian        lexical                               127       127
German          initial                               270       270
Hawaiian        lexical                               369       369
Hebrew          final                                 378       378
Hindi           lexical                               366       366
Hungarian       initial                               288       288
Icelandic       initial                               346       346
Indonesian      lexical                               476       476
Italian         lexical                               473       473
Japanese        positional_pitch_accent               424       454
Khmer           -                                       0         7
Korean          -                                       0       374
Latin           lexical                               442       442
Malay           lexical                               473       473
Mandarin        -                                       4       155
Mongolian       first_long_vowel_else_initial         203       203
Nahuatl         penultimate                           234       234
Nama            -                                       0         4
Navajo          -                                       0        16
Norwegian       initial                               228       228
Old Norse       initial                               224       224
Pama-Nyungan    initial                                61        61
Persian         final                                 326       326
Polish          penultimate                           362       362
Portuguese      final_unless_unstressed_vowel         431       431
Quechua         penultimate                           387       387
Russian         lexical                               380       380
Sanskrit        -                                       0       371
Serbo-Croatian  lexical                               385       385
Spanish         penultimate_or_final_by_coda          447       447
Sumerian        -                                       0        17
Swahili         penultimate                           471       471
Swedish         initial                               242       242
Tamil           initial                               441       441
Thai            -                                       3        29
Tibetan         -                                       0       126
Turkish         final                                 392       392
Vietnamese      -                                      19       138
Welsh           penultimate                           287       287
Xhosa           -                                       0        48
Yoruba          -                                      24        85
Zulu            -                                       0        80
```

Not covered: Sanskrit (Vedic accent), and every tonal language
(which mark tone, not stress).

## Loanwords

A lexicon entry may carry a third element, `[spelling, ipa, loan]`, marking an obvious loanword
(`generation/reference_languages/real_lexicon.loan_glosses`). The audit skips those by default -- a loan may
use clusters the native phonotactics rightly bar -- and reports them in a `loans` column;
`conlang audit-lexicons --include-loans` audits them too. Tagging is deliberately partial: 32 words, chosen
because they were flagged and are plainly borrowed (Basque *triste*, Turkish *kral*, Swahili *kabla*, Tamil
*sakthi*, Malay *nasib*, ...). Loans still work as real words for word strictness; only the audit ignores them.

## Baseline (all curated lexicons; loans excluded)

```
language         words  loans  off-profile  structure  flagged
Georgian           169      0            0          2      1% 
Icelandic          494      0            0          5      1% 
Portuguese         494      0            0          5      1% 
Tamil              489      5            0          4      1% 
Nahuatl            246      0            0          2      1% 
Ancient Greek      494      0            0          3      1% 
French             494      0            2          1      1% 
Swahili            489      5            0          2      0% 
Finnish            493      1            0          2      0% 
Arabic             494      0            0          2      0% 
Dutch              494      0            0          2      0% 
German             494      0            1          1      0% 
Mandarin           494      0            0          2      0% 
Basque             486      8            0          1      0% 
Old Norse          490      0            0          1      0% 
Persian            491      3            0          1      0% 
Turkish            493      1            0          1      0% 
Bengali            494      0            0          1      0% 
Korean             494      0            0          1      0% 
Norwegian          494      0            0          1      0% 
Polish             494      0            0          1      0% 
Serbo-Croatian     494      0            0          1      0% 
Spanish            494      0            0          1      0% 
Arawakan            49      0            0          0      0% 
Cantonese          494      0            0          0      0% 
Danish             494      0            0          0      0% 
English            494      0            0          0      0% 
Hawaiian           399      2            0          0      0% 
Hebrew             494      0            0          0      0% 
Hindi              493      1            0          0      0% 
Hungarian          494      0            0          0      0% 
Indonesian         493      1            0          0      0% 
Italian            494      0            0          0      0% 
Japanese           494      0            0          0      0% 
Khmer               52      0            0          0      0% 
Latin              494      0            0          0      0% 
Malay              489      5            0          0      0% 
Mongolian          322      0            0          0      0% 
Nama                 4      0            0          0      0% 
Navajo              24      0            0          0      0% 
Pama-Nyungan        61      0            0          0      0% 
Quechua            412      0            0          0      0% 
Russian            494      0            0          0      0% 
Sanskrit           494      0            0          0      0% 
Sumerian            38      0            0          0      0% 
Swedish            494      0            0          0      0% 
Thai               190      0            0          0      0% 
Tibetan            365      0            0          0      0% 
Vietnamese         494      0            0          0      0% 
Welsh              494      0            0          0      0% 
Xhosa               52      0            0          0      0% 
Yoruba             102      0            0          0      0% 
Zulu                84      0            0          0      0% 
all              20813     32                              0%
```

A flagged fraction is **not** an error rate: most flags are the profile being
narrower than the language. The profiles were written to steer *invented*
words and are deliberately small; the lexicons use the language's real sounds.

## What the audit found

**Transcription slips (fixed).** Sanskrit *e* and *o* are always long; the
lexicon had them short (23 words, now `eː`/`oː`).

**Profile gaps fixed so far (group 1):** Sanskrit visarga `h`; `s`+stop and
other real onset/coda clusters (English, German, Polish, Italian, French,
Dutch, Latin, Serbo-Croatian, Sanskrit, the Scandinavian languages); coda `ʁ`
(German/French/Danish); long and mid vowels in German, Danish, Swedish and
Norwegian; Italian `ʎ`; Polish onset `ɲ`; English's incorrect "w never
precedes a rounded vowel" restriction; Portuguese/Dutch rhotics in the
lexicons. Attested clusters now also bypass the generic sonority check.

**Word-final devoicing (fixed):** it now bars voiced obstruents only from the
word's last syllable (`SyllableStructure.excluded_final_coda_consonants`), with
voiced+voiceless obstruent boundaries excluded as assimilation; Turkish keeps
`z v ɣ ʒ` (`coda_devoicing_exempt`). The Russian and Polish lexicons were also
transcribed with devoicing (*iz*, *pod*).

**Doubled consonants (fixed):** 27 reference-only geminate twins (`bː mː rː tʃː dˤː` ...) join the six
already in the pool; lexicons write `tt` as `tː` (except where the doubling is a
morpheme boundary: Korean, Indonesian, Malay, Mongolian, Russian, Polish); profiles list the
geminates their lexicon uses. Geminates are word-medial only (barred from onset and from the
word-final coda); a sonorant-coda profile such as Italian's lets geminates close a syllable.

**Three-consonant clusters (fixed):** `SyllableStructure.allowed_onset_triples` /
`allowed_coda_triples`, fed by the profile fields `attested_onset_triples` /
`attested_coda_triples`. A triple is legal only when listed; invented languages stay at
two. Curated for English, German, Polish, Russian, Italian, Serbo-Croatian, Dutch, the
Scandinavian languages, French, Old Norse, Icelandic, Ancient Greek, Spanish, Latin.

**Old Norse and Icelandic (fixed):** 55% -> 3% / 1%. Old Norse's lexicon used `ɛ ɔ w` where the
profile has phonemic `e o v` (now aligned; `ŋ` added, `hv`/`kv` clusters); Icelandic's used
voiced stops and palatal allophones the language lacks (`g d b c ɲ` -> `k t p kʰ ŋ`, intervocalic
`g d` -> `ɣ ð`) and its profile lacked long vowels (`iː uː ɛː aː yː ɔː` added) and `ŋ`. New profile field
`final_geminates` (both languages: *steinn*, *hverr*) exempts a language from the medial-only rule.

**Mandarin and Korean (fixed):** 63% -> 0% / 47% -> 0%. Mandarin gains the aspirated stops and
affricates (`pʰ tʰ kʰ ts tsʰ tɕ tɕʰ`), `ɥ`, and `ə ɨ ɛ`; Korean gains `tʃʰ tʃʼ`. Both now allow
glide onset clusters (`max_onset: 2`, attested `Cj`/`Cw`), since the medial glides are onsets in this
model. Korean's lexicon was transcribed with voiced `g d b` and `ʒ ʃ r`, which the phonemic profile
writes `k t p`, `tʃ s l`.

**Cantonese, Tibetan, Tamil, Hindi (fixed):** 46% -> 0%, 41% -> 0%, 27% -> 2%, 27% -> 0.2%.
Cantonese gains `ɔ ɛ ɪ ʊ y ø œ` and the `kw` glide cluster; Tibetan `ɛ y ø`, `ts dz tsʰ tʃʰ z ɕ`, the
glottal-stop coda `ʔ` (its lexicon is now transcribed with final `k p g b` -> `ʔ`, as in Lhasa) and glide
clusters; Hindi `ẽ õ`, `tʃʰ ʈʰ dʒʱ ɖʱ z f ŋ`, and its lexicon uses the profile's phonemic `i u e o ã`; Tamil's
lexicon is transcribed phonemically (`ɖ`->`ʈ`, `g d b`->`k t p`, `s c ʃ`->`tʃ`) and `ʈ` may open a syllable
(medial `ʈ` has no other onset slot in this model).

**Welsh, Georgian, Zulu, Xhosa (fixed):** 47% -> 0%, 57% -> 1%, 60% -> 1%, 63% -> 2%. Welsh gains
`ɛ ɔ ɨ ɨː ɔː` and its real onset/coda clusters (`gw`, `br`, `bl`; `-fr`, `-dr`, `-gr` as in *llyfr*); Georgian
gains the aspirated and ejective stops/affricates, `ts dz ɣ`, and the long initial clusters (with 3-consonant
onsets such as `mtr`, `sxv`); Zulu and Xhosa gain plain `b d g`, `mb nd ŋg nz` prenasalized units, and
nasal+consonant onset clusters (`nt`, `ŋk`, `ml`, triple `mnt` as in *umntu*).

**Nahuatl, Hungarian, Persian, Ancient Greek (fixed):** 73% -> 1%, 33% -> 1%, 32% -> 2%, 36% -> 1%.
Nahuatl's codas were wrongly restricted (no `m n`); real words end in `-tl`, `-n` and have medial `k h s tl` codas, so
codas are unrestricted, with `ts`, `kw`/`kj` clusters. Hungarian gains `ɔ` (short *a*) and `ŋ`, frees `ɲ` to open
words (*nyelv*) and takes `final_geminates`. Persian gains `iː uː ʔ`, `max_coda: 2` and its real final clusters
(`rg rm ng ʃt`). Ancient Greek gets the new profile field `restricted_final_coda_consonants` (stops and `m l` may close
a syllable inside a word but never end it; words end in `n r s`, `ks`, `ps`), plus the onset clusters `zd ps ks pt kt mn`
and its lexicon aligned to `ɛː`/`y`.

**Spanish and Arabic (fixed):** 32% -> 0.2%, 21% -> 3%. The Spanish lexicon is now written phonemically
(`b d g`, not the intervocalic allophones `β ð ɣ`, which the profile deliberately omits) and its rising
diphthongs (*sj pj mw*, with triples such as *gɾj*) are onset clusters. Arabic's lexicon writes
`aw`/`aj` as the profile's diphthongs `au`/`ai`, and the profile gains `final_geminates` (*shadda* ends
words) and ~70 real final clusters (*ʕd ħm dr ml*).

**Vietnamese, Swahili, Bengali, Mongolian (fixed):** 20% -> 0%, 17% -> 1%, 17% -> 1%, 16% -> 0%.
Vietnamese gains `c ʈ ɣ ɤ` (*ch*, *tr*, *g/gh*, *ơ*) and medial `Cw` onset clusters (*qu-*, *hu-*); Swahili the
nasal+consonant and labialized onset clusters (*mw*, *mk*, *mbw*), `ʒ`, and `dʒ` clusters; Bengali `tʃʰ dʒʱ ʈ ʈʰ ɖ`,
final aspirates (an old restriction was wrong: *kaʈʰ*), `final_geminates`, and its lexicon's `ɪ w ɦ` normalized;
Mongolian `ts dz ɔː`, `max_coda: 2` and its real final clusters (`nd lt gd`), `v` -> `w`.

**Khmer, Nama, Sumerian, Navajo, Arawakan (fixed):** all to 0%. Khmer gains 12 sesquisyllabic onset
clusters (*phnum*, *khnhom*, *kmeng*) and final `-ch`; Nama the click+nasal onsets (`ǃn`); Sumerian unrestricted
codas (*gub*, *sag*, *diš*) with curated coda tiers; Navajo's lexicon is written with the unaspirated stops
`t k` (orthographic `d g`); Arawakan gains `g` and `kw`. **These lexicons are tiny (4-52 words), so the
clusters rest on very little evidence** -- treat the Nama and Sumerian additions as a fit to the sample,
not a description of the language.

**Quechua, Hebrew, Pama-Nyungan, Japanese (fixed):** all to 0%. Quechua's lexicon is phonemic (`a i u`; `e o` are
allophones next to `q`) and the profile gains the ejective affricate `tʃʼ`; Hebrew's `r` is written `ʁ`, and it
gains `ts` and its real initial clusters (`ʃn`, `bl`, `zʁ`); Japanese gains `ts` and the palatalized-mora onsets
(`kya`, `ryo`, as `Cj`), with `ç` written as phonemic `h`; Pama-Nyungan's onset restriction on `ŋ` is removed (the
profile barred a sound that Warlpiri and Yolngu words start with).

**Basque, Danish, Polish, Italian, Russian, Old Norse (fixed):** 5% -> 2%, 4% -> 0%, 5% -> 0%, 5% -> 0%,
3% -> 0%, 3% -> 1%. Italian gets `ts`/`tsː` (*senza*, *ragazzo*), an onset slot for intervocalic `z`
(*casa*, *usare*) and `tw`/`rw`/`lw` glide onsets; Old Norse's lexicon writes `ng` as `ŋg` and final *f* as
`f`; Danish's `w`/`ɪ` slips became `v`/`j`; Russian's `h` became `x`; Basque's plain `s`, `tz` and silent `h`
were normalized to the apical/laminal set and final *-ts* is a legal coda; Polish and Russian initial/final
clusters were added from the lexicon's own words. **Left flagged on purpose:** Basque's Romance-loan clusters
(*triste*, *fruitua*; the profile bars a lone `ɾ` from onsets, which also bars it inside a cluster), four-consonant
runs in Old Norse and Russian, and Polish *ssać*/*miejsce*.

**Sanskrit and the small remainders (fixed):** Sanskrit 14% -> 0%. Its lexicon wrote *ṛ* as a voiceless
trill (`r̥`); it is the syllabic `r̩`, now a profile vowel, as is nasalized `ã` (anusvara). Verbal roots
are cited bare (*vac*, *labh*, *budh*), so aspirates and affricates may close a syllable. The rest are one-line
additions (Arabic/Persian/Turkish/Hungarian final clusters, Portuguese `kw`/`gj` glide onsets, Latin `gw`,
Dutch `wr`, Thai `iə uə`). **Deliberately not admitted, because they occur only in loanwords:** Turkish
initial `kr`, Finnish `st`, Basque `tɾ fɾ pɾ kɾ`, Tamil `kr` (Sanskrit loans), German `sv`, Hawaiian `b s`, and the
Arabic-loan words in Swahili. What remains flagged (~0.7%) is these loans, four-consonant runs, geminate+cluster
sequences in Finnish, and nasal-vowel spellings in French.

**Four-consonant runs and Finnish geminate+cluster (fixed):** `SyllableStructure.allowed_onset_quads` /
`allowed_coda_quads` (profile `attested_onset_quads` / `attested_coda_quads`) carry Old Norse *þyrstr* and
*heimskr*, Russian *vstretit'* and Xhosa *umntwana*. A new word-initial-only restriction
(`excluded_initial_onset_consonants`, profile `restricted_initial_consonants`) replaces the all-onset ban for
Finnish geminates -- they may open a later syllable (*kan.sːa*, *hel.pːo*) but never a word -- and Basque `ɾ`.
Finnish went 2% -> 0%. Still flagged: Finnish *-sta* and *myrsky*, Old Norse *verkfæri*, Polish *ssać*, and
the other one-off words, plus French nasal-vowel spellings. The other geminate profiles (Ancient Greek, Arabic, Bengali, Hindi,
Hungarian, Icelandic, Italian, Japanese, Latin, Old Norse, Persian, Sanskrit, Turkish, Welsh) now use the same
initial-only field: their geminates are barred from opening a word, not from every onset, so they also occur as
the onset of a later syllable (Italian *at.to*, Old Norse *nn.a*). The geminates moved into each profile's
`onset_frequency_tiers` (rare).

**Position restrictions (cleanup).** Word-position rules now share one vocabulary: `restricted_onset_consonants`
(barred from every onset: `ŋ`, Vietnamese `p`), `restricted_initial_consonants` (never open a word, but open
later syllables: geminates, retroflexes, English `ʒ`, Bengali/Hindi `ɽ`, Tamil `ɭ ɻ ɳ ʈ`, Pama-Nyungan `r l`),
`restricted_final_coda_consonants` (never end a word) and `medial_only_consonants` (both: Icelandic `ʰp ʰt ʰk`).
Tamil, Nahuatl, Sumerian and Swahili geminates are now word-medial too. French and Portuguese lexicons use real
nasal vowels, and every /g/ is ASCII `g`.

**Still open** -- see `docs/DEFERRED.md` section 1:
three-consonant clusters, glide+vowel sequences, and the languages not yet
reviewed (Old Norse, Nahuatl, Mandarin, Icelandic, Welsh, Georgian, Korean,
Ancient Greek, Zulu/Xhosa, Tibetan, Tamil, Hungarian, Persian, Spanish,
Hindi).
