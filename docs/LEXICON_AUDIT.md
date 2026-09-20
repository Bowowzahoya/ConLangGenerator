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
Sanskrit           494            3        340     69% 
Old Norse          490           98        233     68% 
Xhosa               52           19         14     63% 
Mandarin           494          216         97     63% 
Icelandic          494          191        106     60% 
Zulu                84           31         19     60% 
Georgian           169           74         23     57% 
Portuguese         494          244         14     52% 
Welsh              494          172         72     49% 
Korean             494          216         18     47% 
Swedish            494          123        107     47% 
Cantonese          494          222          3     46% 
Danish             494          131         90     45% 
Dutch              494          167         47     43% 
Ancient Greek      494           58        155     43% 
German             494           34        173     42% 
Polish             494            1        204     41% 
Tibetan            365          107         41     41% 
Norwegian          494           95         98     39% 
Spanish            494          125         67     39% 
Tamil              494          128         56     37% 
Hungarian          494          150         31     37% 
Persian            494          107         74     37% 
Italian            494            5        158     33% 
Serbo-Croatian     494            0        156     32% 
Russian            494            1        143     29% 
Sumerian            38            0         11     29% 
Khmer               52            0         15     29% 
Hindi              494          114         24     28% 
Nama                 4            0          1     25% 
Arabic             494            0        122     25% 
Vietnamese         494           90          7     20% 
English            494            0         94     19% 
Bengali            494           64         22     17% 
Swahili            494            4         81     17% 
Mongolian          322           21         33     17% 
Navajo              24            4          0     17% 
Arawakan            49            6          2     16% 
French             494            2         77     16% 
Turkish            494            1         68     14% 
Latin              494            4         61     13% 
Japanese           494           12         50     13% 
Hebrew             494            8         44     11% 
Quechua            412           42          0     10% 
Pama-Nyungan        61            1          5     10% 
Thai               190            5          8      7% 
Basque             494            7         16      5% 
Finnish            494            7         10      3% 
Malay              494            0          5      1% 
Hawaiian           401            2          0      0% 
Indonesian         494            0          1      0% 
Yoruba             102            0          0      0% 
all              20845                             32% 
```

A flagged fraction is **not** an error rate: most flags are the profile being
narrower than the language. The profiles were written to steer *invented*
words and are deliberately small; the lexicons use the language's real sounds.

## What the audit found

**Transcription slips (fixed).** Sanskrit *e* and *o* are always long; the
lexicon had them short (23 words, now `eː`/`oː`).

**Profile gaps (open) -- the frequent causes**

| Cause | Where |
|---|---|
| Word-final `h` (visarga *-ḥ*) not allowed as a coda | Sanskrit (~120 words) |
| `s`+stop onsets (`st sp sk`) and other real onset clusters missing from curated cluster lists | English, German, Italian, Russian, Polish, Latin, Ancient Greek, Old Norse, ... |
| Affricate onsets/codas (`ts`, `tɬ`) and `kw` | Nahuatl, German, Italian |
| Coda `ʁ` (vocalized in speech) | German, Danish, French |
| Vowel sets missing long/mid vowels (`ɔ ɛ ɪ ə øː yː ɛː ɑː iː`) | English, German, Swedish, Norwegian, Danish, Persian, Welsh, Icelandic, ... |
| Doubled consonants written as a cluster (`tt`, `ss`, `jj`, `ll`) | Italian, Arabic, Hungarian, Finnish |
| Palatal lateral `ʎ`, tap `ɾ`, `r` vs `ɾ` | Portuguese, Italian, Spanish |
| `w` restricted before rounded vowels (English *water*) | English |

Fixing these means editing profile YAMLs (tiers, restricted lists, attested
clusters) and, for doubled consonants, adding long consonants to the pool --
see `docs/DEFERRED.md` section 1.
