"""Interprétation locale de la barre de recherche unique Finestalk.

Ne transmet aucune adresse e-mail ni aucun téléphone à un service externe.
Les noms proposés en recherche publique n'impliquent aucune identification.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from urllib.parse import urlencode

from profile_review import normalize_instagram


@dataclass(frozen=True)
class Query:
    kind: str
    text: str


_EMAIL = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}$")
_NAME_WORD = re.compile(r"^[^\W\d_]+(?:[-'’][^\W\d_]+)*$", re.UNICODE)
_PHONE_CHARS = re.compile(r"^[+\d][\d\s.()\-]+$")


def interpret(raw: str) -> Query:
    """Renvoie username, name, email ou phone ; aucun appel réseau."""
    value = unicodedata.normalize("NFC", str(raw or "")).strip()
    if not value or len(value) > 254 or any(ord(c) < 32 for c in value):
        raise ValueError("Indiquez un pseudonyme, un nom complet ou une coordonnée.")
    value = " ".join(value.split())
    if value.casefold().startswith(("https://", "http://", "www.", "instagram.com/")):
        username, _ = normalize_instagram(value)
        return Query("username", username)
    if "@" in value and not value.startswith("@"):
        if not _EMAIL.fullmatch(value) or ".." in value or len(value.split("@", 1)[0]) > 64:
            raise ValueError("Le format de cette adresse e-mail est invalide.")
        return Query("email", value)
    numbers = re.sub(r"\D", "", value)
    if _PHONE_CHARS.fullmatch(value) and (
        value.startswith("+")
        or value.startswith("00")
        or (len(numbers) == 10 and value.startswith("0"))
        or (len(numbers) >= 9 and any(ch in value for ch in " -()."))
    ):
        if not (9 <= len(numbers) <= 15):
            raise ValueError("Le format de ce numéro de téléphone est invalide.")
        return Query("phone", value)
    tokens = value.split(" ")
    if len(tokens) >= 2:
        if not (2 <= len(tokens) <= 5) or not all(_NAME_WORD.fullmatch(token) for token in tokens):
            raise ValueError("Saisissez un prénom et un nom ou un pseudonyme valide.")
        return Query("name", " ".join(tokens))
    username, _ = normalize_instagram(value)
    return Query("username", username)


def public_search_links(query: Query) -> dict[str, str]:
    """Recherches web à ouvrir manuellement. Aucun résultat n'est aspiré."""
    if query.kind not in {"username", "name"}:
        return {}
    quoted = '"' + query.text + '"'
    return {
        "Google": "https://www.google.com/search?" + urlencode({"q": quoted}),
        "Bing": "https://www.bing.com/search?" + urlencode({"q": quoted}),
        "DuckDuckGo": "https://duckduckgo.com/?" + urlencode({"q": quoted}),
    }
