"""Consultation minimale de métadonnées publiquement retournées par Instagram.

Une seule requête HTTPS, vers un hôte fixé par le programme, sans connexion,
redirection, navigation automatisée, recherche de personnes ni corrélation
entre pseudonymes. Ne conclut jamais à une identité civile.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import re

import requests

from profile_review import normalize_instagram


MAX_HTML_BYTES = 512 * 1024
TITLE_MAX_CHARS = 240
DESCRIPTION_MAX_CHARS = 700


def _clean(value: str, limit: int) -> str:
    value = re.sub(r"[\x00-\x1f\x7f]", " ", value or "")
    return re.sub(r"\s+", " ", value).strip()[:limit]


class _MetaParser(HTMLParser):
    """Uniquement les métadonnées de la page, pas les scripts embarqués."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.data: dict[str, str] = {}
        self.title_fragments: list[str] = []
        self.in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        if name == "title":
            self.in_title = True
        elif name == "meta":
            props = dict(attrs)
            key = (props.get("property") or props.get("name") or "").lower().strip()
            if key in ("og:title", "og:description", "twitter:title", "description"):
                if key not in self.data and props.get("content"):
                    self.data[key] = _clean(
                        props["content"], DESCRIPTION_MAX_CHARS
                        if "description" in key else TITLE_MAX_CHARS
                    )

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title and sum(map(len, self.title_fragments)) < TITLE_MAX_CHARS:
            self.title_fragments.append(data[:TITLE_MAX_CHARS])

    def title(self) -> str:
        return (self.data.get("og:title") or self.data.get("twitter:title")
                or _clean("".join(self.title_fragments), TITLE_MAX_CHARS))

    def description(self) -> str:
        return self.data.get("og:description") or self.data.get("description", "")


def extract_metadata(html: str, username: str) -> tuple[str, str, str]:
    """Retourne (nom affiché, titre, description), sans supposer le vrai nom."""
    parser = _MetaParser()
    parser.feed(html[:MAX_HTML_BYTES])
    page_title = parser.title()
    description = parser.description()
    declared_name = ""
    # Exige la mention explicite du pseudonyme exact dans un titre de profil.
    title_candidates = [
        parser.data.get("og:title", ""),
        parser.data.get("twitter:title", ""),
        page_title,
    ]
    pattern = re.compile(
        r"^(.{1,160}?)\s*\(@" + re.escape(username)
        + r"\)(?:\s*[·•|\-].*)?$", re.IGNORECASE
    )
    for title in title_candidates:
        match = pattern.fullmatch(title.strip())
        if match:
            name = _clean(match.group(1), 160)
            if name.casefold() not in {"instagram", "log in", "login", "connexion"}:
                declared_name = name
                break
    return declared_name, page_title, description


@dataclass(frozen=True)
class PublicProfileResult:
    username: str
    canonical_url: str
    checked_at: str
    status: str
    display_name: str = ""
    page_title: str = ""
    public_description: str = ""
    http_status: int | None = None
    message: str = ""


def _result(username: str, url: str, timestamp: str, status: str,
            message: str, code: int | None = None,
            name: str = "", title: str = "", description: str = "") -> PublicProfileResult:
    return PublicProfileResult(
        username=username, canonical_url=url, checked_at=timestamp,
        status=status, display_name=name, page_title=title,
        public_description=description, http_status=code, message=message
    )


def lookup_public_profile(value: str, *, transport=None) -> PublicProfileResult:
    """Lecture opportuniste du document public ; échec explicite si bloqué.

    `transport` sert à injecter une fausse réponse dans les tests.
    """
    username, url = normalize_instagram(value)
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    get = transport if transport is not None else requests.get
    try:
        response = get(
            url,
            headers={
                "Accept": "text/html",
                "User-Agent": "Mozilla/5.0 (compatible; FinestalkProfilePreview/1.0)",
            },
            stream=True,
            allow_redirects=False,
            timeout=(4, 10),
        )
        with response:
            code = response.status_code
            if code in (301, 302, 303, 307, 308):
                return _result(username, url, timestamp, "redirection",
                               "La plateforme a redirigé la consultation ; aucune redirection n'a été suivie.", code)
            if code in (401, 403, 429):
                return _result(username, url, timestamp, "acces_limite",
                               "Instagram limite ou bloque les consultations automatisées non connectées.", code)
            if code == 404:
                return _result(username, url, timestamp, "indisponible",
                               "Ce profil n'est pas accessible à cette adresse.", code)
            if code != 200:
                return _result(username, url, timestamp, "erreur",
                               "Instagram n'a pas renvoyé de page consultable.", code)
            if "text/html" not in response.headers.get("Content-Type", "").lower():
                return _result(username, url, timestamp, "format_inattendu",
                               "La réponse reçue n'est pas une page HTML.", code)

            buffer = bytearray()
            for chunk in response.iter_content(chunk_size=16384):
                if len(buffer) + len(chunk) > MAX_HTML_BYTES:
                    return _result(username, url, timestamp, "page_trop_grande",
                                   "La page dépasse la limite de lecture prudente.", code)
                buffer.extend(chunk)
            encoding = response.encoding or "utf-8"
            try:
                html = buffer.decode(encoding, errors="replace")
            except LookupError:
                html = buffer.decode("utf-8", errors="replace")
            displayed, title, description = extract_metadata(html, username)

            if displayed:
                return _result(username, url, timestamp, "metadonnees_publiques",
                               "Informations publiques affichées par le compte, sans vérification d'identité.",
                               code, displayed, title, description)
            if re.search(r"\b(log ?in|sign ?up|connexion|se connecter)\b", title, re.I):
                return _result(username, url, timestamp, "connexion_requise",
                               "Instagram affiche un écran de connexion.", code)
            if username.casefold() in title.casefold() or username.casefold() in description.casefold():
                return _result(username, url, timestamp, "metadonnees_partielles",
                               "Un titre ou une description publique a été retrouvé sans nom explicite.",
                               code, "", title, description)
            return _result(username, url, timestamp, "aucune_donnee",
                           "Aucune métadonnée fiable associée à ce compte n'a pu être lue.", code)
    except requests.RequestException:
        return _result(username, url, timestamp, "erreur_reseau",
                       "Instagram ne répond pas ou refuse cette consultation. Essayez directement sur son site.")
