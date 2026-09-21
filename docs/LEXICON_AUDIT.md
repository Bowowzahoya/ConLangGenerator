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

## Baseline (all curated lexicons)

```
language         words  off-profile  structure  flagged
Spanish            494          125         34     32% 
Khmer               52            0         14     27% 
Nama                 4            0          1     25% 
Sumerian            38            0          9     24% 
Arabic             494            0        104     21% 
Vietnamese         494           90          7     20% 
Swahili            494            4         80     17% 
Navajo              24            4          0     17% 
Bengali            494           61         21     17% 
Mongolian          322           21         32     16% 
Arawakan            49            6          2     16% 
Sanskrit           494            3         66     14% 
Japanese           494           11         43     11% 
Hebrew             494            8         44     11% 
Quechua            412           42          0     10% 
Pama-Nyungan        61            1          5     10% 
Polish             494            1         25      5% 
Italian            494            0         25      5% 
Basque             494            7         16      5% 
Danish             494           17          1      4% 
Russian            494            1         16      3% 
Old Norse          490            0         16      3% 
Portuguese         494            0         15      3% 
Thai               190            5          0      3% 
Finnish            494            1         10      2% 
Persian            494            0         11      2% 
German             494            1          9      2% 
Xhosa               52            0          1      2% 
Tamil              494            1          8      2% 
Turkish            494            0          7      1% 
Latin              494            4          2      1% 
Zulu                84            0          1      1% 
Georgian           169            0          2      1% 
Ancient Greek      494            0          5      1% 
Icelandic          494            0          5      1% 
Malay              494            0          5      1% 
Norwegian          494            0          5      1% 
Serbo-Croatian     494            0          5      1% 
Nahuatl            246            0          2      1% 
Hungarian          494            0          4      1% 
Dutch              494            0          3      1% 
French             494            2          1      1% 
Hawaiian           401            2          0      0% 
Mandarin           494            0          2      0% 
Swedish            494            0          2      0% 
Hindi              494            0          1      0% 
Indonesian         494            0          1      0% 
Korean             494            0          1      0% 
Cantonese          494            0          0      0% 
English            494            0          0      0% 
Tibetan            365            0          0      0% 
Welsh              494            0          0      0% 
Yoruba             102            0          0      0% 
all              20845                              5%
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

**Still open** -- see `docs/DEFERRED.md` section 1:
three-consonant clusters, glide+vowel sequences, and the languages not yet
reviewed (Old Norse, Nahuatl, Mandarin, Icelandic, Welsh, Georgian, Korean,
Ancient Greek, Zulu/Xhosa, Tibetan, Tamil, Hungarian, Persian, Spanish,
Hindi).
