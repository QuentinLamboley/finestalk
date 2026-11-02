"""Vérification de présence publique d'un pseudonyme sur des plateformes choisies.

Les correspondances sont strictement des *comptes* portant ce pseudonyme.
Elles ne permettent pas de déterminer qui contrôle ces comptes, ni d'établir
qu'ils appartiennent à une même personne. Aucune donnée personnelle, contact,
localisation ou nom civil n'est collecté.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from urllib.parse import quote, urlencode
import json
import re

import requests

from profile_review import normalize_instagram

MAX_BODY = 160_000
TIMEOUT = (3.5, 7)
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Finestalk-PublicPresence/1.0 (one public account check per platform)",
}
PLATFORMS = ("GitHub", "GitLab", "DEV Community", "Chess.com", "Hacker News")
RESTRICTED = frozenset({401, 403, 429})


@dataclass(frozen=True)
class AccountResult:
    platform: str
    username: str
    state: str  # found | absent | unknown | unsupported
    profile_url: str
    source_url: str
    description: str
    checked_at: str
    http_status: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _endpoint(platform: str, handle: str) -> tuple[str, str] | None:
    name = quote(handle, safe="")
    if platform == "GitHub":
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", handle):
            return None
        return f"https://api.github.com/users/{name}", f"https://github.com/{name}"
    if platform == "GitLab":
        return (
            "https://gitlab.com/api/v4/users?" + urlencode({"username": handle}),
            f"https://gitlab.com/{name}",
        )
    if platform == "DEV Community":
        return (
            "https://dev.to/api/users/by_username?" + urlencode({"url": handle}),
            f"https://dev.to/{name}",
        )
    if platform == "Chess.com":
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,30}", handle):
            return None
        return f"https://api.chess.com/pub/player/{name}", f"https://www.chess.com/member/{name}"
    if platform == "Hacker News":
        if not re.fullmatch(r"[A-Za-z0-9_-]{2,30}", handle):
            return None
        return (
            f"https://hacker-news.firebaseio.com/v0/user/{name}.json",
            "https://news.ycombinator.com/user?" + urlencode({"id": handle}),
        )
    raise ValueError("Plateforme non prise en charge.")


def search_links(handle: str) -> dict[str, str]:
    """Liens de recherche manuelle, sans interrogation automatique des moteurs."""
    handle, _ = normalize_instagram(handle)
    exact = '"' + handle + '"'
    return {
        "Google": "https://www.google.com/search?" + urlencode({"q": exact}),
        "Bing": "https://www.bing.com/search?" + urlencode({"q": exact}),
        "DuckDuckGo": "https://duckduckgo.com/?" + urlencode({"q": exact}),
    }


def _read_json(response):
    """Lit une petite réponse JSON sans téléchargement illimité."""
    content_type = response.headers.get("Content-Type", "").lower()
    if "json" not in content_type:
        raise ValueError("La réponse n'est pas du JSON.")
    data = bytearray()
    for chunk in response.iter_content(chunk_size=8192):
        data.extend(chunk)
        if len(data) > MAX_BODY:
            raise ValueError("Réponse trop volumineuse.")
    return json.loads(bytes(data).decode("utf-8-sig"))


def _exact_username(platform: str, payload, username: str) -> bool | None:
    """True = fiche exacte, False = réponse contradictoire, None = format inconnu."""
    if platform == "GitLab":
        if not isinstance(payload, list):
            return None
        if not payload:
            return False
        return any(
            isinstance(item, dict) and
            str(item.get("username", "")).casefold() == username.casefold()
            for item in payload
        )
    if platform == "Hacker News":
        if payload is None:
            return False
        if not isinstance(payload, dict):
            return None
        return payload.get("id") == username  # Identifiants HN sensibles à la casse.
    if not isinstance(payload, dict):
        return None
    key = {
        "GitHub": "login",
        "DEV Community": "username",
        "Chess.com": "username",
    }[platform]
    actual = payload.get(key)
    if not isinstance(actual, str) or not actual:
        return None
    return actual.casefold() == username.casefold()


def check_platform(platform: str, handle: str, *, http_get=None) -> AccountResult:
    """Une requête par plateforme; aucune redirection ni corrélation de comptes."""
    username, _ = normalize_instagram(handle)
    stamp = _now()
    endpoint = _endpoint(platform, username)
    if endpoint is None:
        return AccountResult(
            platform, username, "unsupported", "", "",
            "Format du pseudo non accepté sur cette plateforme.", stamp,
        )
    source_url, profile_url = endpoint
    getter = http_get or requests.get
    try:
        response = getter(
            source_url, headers=HEADERS, timeout=TIMEOUT,
            stream=True, allow_redirects=False,
        )
        with response:
            status = response.status_code
            if status == 404:
                return AccountResult(
                    platform, username, "absent", profile_url, source_url,
                    "Aucune fiche publique trouvée à cette adresse.", stamp, status,
                )
            if status in RESTRICTED:
                return AccountResult(
                    platform, username, "unknown", profile_url, source_url,
                    "Accès limité ou authentification requise.", stamp, status,
                )
            if status != 200:
                return AccountResult(
                    platform, username, "unknown", profile_url, source_url,
                    "La plateforme n'a pas fourni de réponse exploitable.", stamp, status,
                )
            try:
                data = _read_json(response)
            except (ValueError, UnicodeError, json.JSONDecodeError):
                return AccountResult(
                    platform, username, "unknown", profile_url, source_url,
                    "Format de réponse inattendu ou taille dépassée.", stamp, status,
                )
            exact = _exact_username(platform, data, username)
            if exact is True:
                return AccountResult(
                    platform, username, "found", profile_url, source_url,
                    "Compte public portant exactement ce pseudonyme, confirmé par l'API.",
                    stamp, status,
                )
            if exact is False and platform in {"GitLab", "Hacker News"}:
                return AccountResult(
                    platform, username, "absent", profile_url, source_url,
                    "Aucune fiche publique exacte retournée par l'API.", stamp, status,
                )
            return AccountResult(
                platform, username, "unknown", profile_url, source_url,
                "L'API ne confirme pas de compte portant exactement ce pseudonyme.",
                stamp, status,
            )
    except requests.RequestException:
        return AccountResult(
            platform, username, "unknown", profile_url, source_url,
            "Requête impossible depuis ce serveur (réseau, délai ou filtrage).",
            stamp,
        )


def check_public_presence(handle: str, *, http_get=None) -> list[AccountResult]:
    username, _ = normalize_instagram(handle)
    # Cinq consultations indépendantes, maximum trois simultanées.
    # Un échec réseau ne bloque pas les autres plateformes.
    with ThreadPoolExecutor(max_workers=3) as pool:
        future = {
            p: pool.submit(check_platform, p, username, http_get=http_get)
            for p in PLATFORMS
        }
        return [future[p].result() for p in PLATFORMS]
