"""Consultation minimale de métadonnées publiquement retournées par Instagram.

Une consultation HTTPS limitée aux hôtes Instagram autorisés et au chemin
exact du profil, sans connexion, navigation automatisée, recherche de personnes
ni corrélation entre pseudonymes. Ne conclut jamais à une identité civile.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlsplit

import requests

from profile_review import normalize_instagram


MAX_HTML_BYTES = 512 * 1024
TITLE_MAX_CHARS = 240
DESCRIPTION_MAX_CHARS = 700
MAX_SAFE_REDIRECTS = 3
REDIRECT_CODES = (301, 302, 303, 307, 308)
SAFE_HOSTS = frozenset({"www.instagram.com", "instagram.com", "m.instagram.com"})


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


def _safe_redirect(current_url: str, location: str, username: str) -> tuple[str, str]:
    """Vérifie une redirection sans jamais visiter une destination arbitraire.

    On accepte uniquement le même profil exact sur un domaine Instagram
    prédéfini en HTTPS. Les routes de connexion sont reconnues, non visitées.
    """
    if not location or len(location) > 4096:
        return "", "redirection_bloquee"
    target = urljoin(current_url, location)
    try:
        parsed = urlsplit(target)
        port = parsed.port
    except ValueError:
        return "", "redirection_bloquee"
    if (parsed.scheme != "https" or parsed.hostname not in SAFE_HOSTS
            or parsed.username or parsed.password or port not in (None, 443)):
        return "", "redirection_bloquee"
    path = parsed.path.casefold().rstrip("/")
    if path in {"/accounts/login", "/accounts/signup", "/challenge",
                "/accounts/onetap"} or any(
                path.startswith(prefix + "/") for prefix in
                ("/accounts/login", "/accounts/signup", "/challenge",
                 "/accounts/onetap")):
        return "", "connexion_requise"
    if path != "/" + username.casefold():
        return "", "redirection_autre_page"
    return target, "profil"


def lookup_public_profile(value: str, *, transport=None) -> PublicProfileResult:
    """Lit la page publique ; suit au maximum trois redirections vérifiées.

    Si Instagram exige une connexion, la consultation s'arrête : aucune
    authentification automatisée, aucun contournement, aucune donnée supposée.
    Le paramètre transport sert exclusivement aux tests hors réseau.
    """
    username, canonical_url = normalize_instagram(value)
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    get = transport if transport is not None else requests.get
    current_url = canonical_url
    visited = set()
    redirects = 0
    try:
        while True:
            if current_url in visited:
                return _result(username, canonical_url, timestamp, "boucle_redirection",
                               "Instagram renvoie en boucle vers la même adresse.")
            visited.add(current_url)
            response = get(
                current_url,
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
                if code in REDIRECT_CODES:
                    new_url, kind = _safe_redirect(
                        current_url, response.headers.get("Location", ""), username
                    )
                    if kind == "connexion_requise":
                        return _result(username, canonical_url, timestamp, kind,
                            "Instagram demande une connexion pour consulter ce profil depuis le serveur. "
                            "Finestalk ne contourne pas cette restriction.", code)
                    if kind == "redirection_autre_page":
                        return _result(username, canonical_url, timestamp, kind,
                            "Instagram redirige vers une autre page que ce profil. "
                            "Aucune information sur le compte ne peut être confirmée.", code)
                    if kind != "profil":
                        return _result(username, canonical_url, timestamp, "redirection_bloquee",
                            "Instagram a proposé une redirection extérieure au profil autorisé ; "
                            "elle a été bloquée par sécurité.", code)
                    if redirects >= MAX_SAFE_REDIRECTS:
                        return _result(username, canonical_url, timestamp,
                            "trop_de_redirections",
                            "Trop de redirections successives pour ouvrir le profil.", code)
                    current_url = new_url
                    redirects += 1
                    continue

                if code in (401, 403, 429):
                    return _result(username, canonical_url, timestamp, "acces_limite",
                                   "Instagram limite l'accès non connecté depuis ce serveur.", code)
                if code == 404:
                    return _result(username, canonical_url, timestamp, "indisponible",
                                   "Ce profil n'est pas accessible à cette adresse.", code)
                if code != 200:
                    return _result(username, canonical_url, timestamp, "erreur",
                                   "Instagram n'a pas renvoyé de page consultable.", code)
                if "text/html" not in response.headers.get("Content-Type", "").lower():
                    return _result(username, canonical_url, timestamp, "format_inattendu",
                                   "La réponse reçue n'est pas une page HTML.", code)

                buffer = bytearray()
                for chunk in response.iter_content(chunk_size=16384):
                    if len(buffer) + len(chunk) > MAX_HTML_BYTES:
                        return _result(username, canonical_url, timestamp, "page_trop_grande",
                                       "La page dépasse la limite de lecture prudente.", code)
                    buffer.extend(chunk)
                encoding = response.encoding or "utf-8"
                try:
                    html = buffer.decode(encoding, errors="replace")
                except LookupError:
                    html = buffer.decode("utf-8", errors="replace")
                displayed, title, description = extract_metadata(html, username)

                if re.search(r"\b(log ?in|sign ?up|connexion|se connecter)\b", title, re.I):
                    return _result(username, canonical_url, timestamp, "connexion_requise",
                                   "Instagram affiche un écran de connexion.", code)
                if displayed:
                    return _result(username, canonical_url, timestamp, "metadonnees_publiques",
                                   "Informations publiquement affichées, sans vérification d'identité.",
                                   code, displayed, title, description)
                if username.casefold() in title.casefold() or username.casefold() in description.casefold():
                    return _result(username, canonical_url, timestamp, "metadonnees_partielles",
                                   "Titre ou description publique retrouvés sans nom explicite.",
                                   code, "", title, description)
                return _result(username, canonical_url, timestamp, "aucune_donnee",
                               "Aucune métadonnée fiable associée à ce compte n'a pu être lue.", code)
    except requests.RequestException:
        return _result(username, canonical_url, timestamp, "erreur_reseau",
                       "Instagram ne répond pas ou refuse cette consultation. "
                       "Ouvrez le profil directement sur son site.")
