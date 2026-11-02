"""Détection locale du type de texte dans l'unique barre de recherche.

Aucune donnée de contact n'est transmise ni recherchée auprès de tiers.
"""
import re
from dataclasses import dataclass
from urllib.parse import urlencode

from profile_review import normalize_instagram

@dataclass(frozen=True)
class Query:
    kind: str
    text: str

def interpret(text: str) -> Query:
    value = " ".join((text or "").strip().split())
    if not value or len(value) > 200:
        raise ValueError("Requête vide ou trop longue.")
    if re.fullmatch(r"[^\s@]+@[^\s@]+\.[A-Za-z]{2,}", value):
        return Query("email", value)
    digits = re.sub(r"[^\d]", "", value)
    if len(digits) >= 9 and re.fullmatch(r"[+\d().\s-]+", value):
        return Query("phone", value)
    if len(value.split()) >= 2 and all(
        re.fullmatch(r"[^\W\d_]+(?:[-'][^\W\d_]+)*", x)
        for x in value.split()
    ):
        return Query("name", value)
    handle, _ = normalize_instagram(value)
    return Query("username", handle)

def public_search_links(query: Query) -> dict[str, str]:
    if query.kind not in {"name", "username"}:
        return {}
    quoted = '"' + query.text + '"'
    return {
        "Google": "https://www.google.com/search?" + urlencode({"q": quoted}),
        "Bing": "https://www.bing.com/search?" + urlencode({"q": quoted}),
        "DuckDuckGo": "https://duckduckgo.com/?" + urlencode({"q": quoted}),
    }
