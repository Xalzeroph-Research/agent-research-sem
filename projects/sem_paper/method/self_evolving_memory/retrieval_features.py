from __future__ import annotations

import re
import unicodedata

_WORD_RE = re.compile(r"[^\W_]+", flags=re.UNICODE)
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")


def lexical_features(text: str) -> frozenset[str]:
    """Deterministic lightweight retrieval features for multilingual grounded text.

    Word tokens cover whitespace-delimited/alphanumeric languages.  CJK runs additionally
    emit character bigrams so a short Chinese query can match a longer unsegmented phrase.
    The function is intentionally dependency-free and stable across runtime providers.
    """

    normalized = unicodedata.normalize("NFKC", text).casefold()
    features: set[str] = set(_WORD_RE.findall(normalized))
    for match in _CJK_RE.finditer(normalized):
        run = match.group(0)
        if len(run) == 1:
            features.add(run)
        else:
            features.update(run[index : index + 2] for index in range(len(run) - 1))
    return frozenset(features)


__all__ = ["lexical_features"]
