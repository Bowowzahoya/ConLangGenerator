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
Nahuatl            246           23        172     79% 
Old Norse          490           98        213     63% 
Xhosa               52           19         14     63% 
Mandarin           494          216         97     63% 
Zulu                84           31         19     60% 
Icelandic          494          191         96     58% 
Georgian           169           74         22     57% 
Korean             494          216         18     47% 
Welsh              494          172         60     47% 
Cantonese          494          222          3     46% 
Tibetan            365          107         41     41% 
Tamil              494          128         56     37% 
Hungarian          494          150         31     37% 
Ancient Greek      494           58        117     35% 
Spanish            494          125         38     33% 
Persian            494          107         52     32% 
Sumerian            38            0         11     29% 
Hindi              494          114         20     27% 
Khmer               52            0         14     27% 
Nama                 4            0          1     25% 
Arabic             494            0        113     23% 
Italian            494            0        105     21% 
Vietnamese         494           90          7     20% 
Bengali            494           64         21     17% 
Swahili            494            4         81     17% 
Navajo              24            4          0     17% 
Mongolian          322           21         32     16% 
Arawakan            49            6          2     16% 
Sanskrit           494            3         68     14% 
Japanese           494           12         50     13% 
Hebrew             494            8         44     11% 
Quechua            412           42          0     10% 
Pama-Nyungan        61            1          5     10% 
Polish             494            1         44      9% 
German             494            1         25      5% 
Russian            494            1         25      5% 
Danish             494           17          7      5% 
Basque             494            7         16      5% 
Finnish            494            7         10      3% 
Portuguese         494            0         15      3% 
Serbo-Croatian     494            0         15      3% 
Thai               190            5          0      3% 
Dutch              494            0         11      2% 
French             494            2          8      2% 
Norwegian          494            0         10      2% 
Latin              494            4          4      2% 
Turkish            494            1          7      2% 
Swedish            494            0          7      1% 
Malay              494            0          5      1% 
English            494            0          4      1% 
Hawaiian           401            2          0      0% 
Indonesian         494            0          1      0% 
Yoruba             102            0          0      0% 
all              20845                             20%
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

**Still open** -- see `docs/DEFERRED.md` section 1: doubled consonants,
three-consonant clusters, glide+vowel sequences, and the languages not yet
reviewed (Old Norse, Nahuatl, Mandarin, Icelandic, Welsh, Georgian, Korean,
Ancient Greek, Zulu/Xhosa, Tibetan, Tamil, Hungarian, Persian, Spanish,
Hindi).
