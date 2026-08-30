"""Deterministic IPA -> Latin transliteration, kept separate from IPA storage.

A ``RomanizationScheme`` never touches the stored IPA; it only renders a display
form. Rules are tried longest-``ipa``-pattern-first so multi-symbol sequences
(e.g. affricates, toned vowels) are matched before their single-symbol parts.
"""

from __future__ import annotations

import unicodedata

from pydantic import BaseModel


class RomanizationRule(BaseModel, frozen=True):
    ipa: str
    latin: str


class RomanizationScheme(BaseModel, frozen=True):
    rules: tuple[RomanizationRule, ...]

    def _ordered_rules(self) -> list[RomanizationRule]:
        return sorted(self.rules, key=lambda r: len(r.ipa), reverse=True)

    def apply(self, ipa_text: str) -> str:
        """Greedily rewrite an IPA string into its Latin romanization.

        The result is normalized to NFC (precomposed accents, e.g. a single
        'é' codepoint) so it matches what a human typing or copy-pasting the
        romanization would produce -- IPA itself is left untouched, since
        combining diacritics are the conventional IPA representation.
        """
        rules = self._ordered_rules()
        out: list[str] = []
        i = 0
        while i < len(ipa_text):
            for rule in rules:
                if ipa_text.startswith(rule.ipa, i):
                    out.append(rule.latin)
                    i += len(rule.ipa)
                    break
            else:
                out.append(ipa_text[i])
                i += 1
        return unicodedata.normalize("NFC", "".join(out))
