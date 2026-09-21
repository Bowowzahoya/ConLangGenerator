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
Finnish            493      1            0         10      2% 
Xhosa               52      0            0          1      2% 
Portuguese         494      0            0          6      1% 
Zulu                84      0            0          1      1% 
Georgian           169      0            0          2      1% 
Icelandic          494      0            0          5      1% 
Tamil              489      5            0          4      1% 
Nahuatl            246      0            0          2      1% 
Old Norse          490      0            0          3      1% 
Ancient Greek      494      0            0          3      1% 
French             494      0            2          1      1% 
Basque             486      8            0          2      0% 
Arabic             494      0            0          2      0% 
Bengali            494      0            0          2      0% 
Dutch              494      0            0          2      0% 
German             494      0            1          1      0% 
Mandarin           494      0            0          2      0% 
Polish             494      0            0          2      0% 
Swahili            489      5            0          1      0% 
Persian            491      3            0          1      0% 
Turkish            493      1            0          1      0% 
Korean             494      0            0          1      0% 
Norwegian          494      0            0          1      0% 
Russian            494      0            0          1      0% 
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
Sanskrit           494      0            0          0      0% 
Sumerian            38      0            0          0      0% 
Swedish            494      0            0          0      0% 
Thai               190      0            0          0      0% 
Tibetan            365      0            0          0      0% 
Vietnamese         494      0            0          0      0% 
Welsh              494      0            0          0      0% 
Yoruba             102      0            0          0      0% 
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

**Still open** -- see `docs/DEFERRED.md` section 1:
three-consonant clusters, glide+vowel sequences, and the languages not yet
reviewed (Old Norse, Nahuatl, Mandarin, Icelandic, Welsh, Georgian, Korean,
Ancient Greek, Zulu/Xhosa, Tibetan, Tamil, Hungarian, Persian, Spanish,
Hindi).
