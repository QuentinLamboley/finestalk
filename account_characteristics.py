"""Caractéristiques observables d'un compte public, sans recherche d'identité.

Les valeurs proviennent d'une observation fournie par l'utilisateur.
Aucun accès au réseau, recoupement inter-plateformes ou collecte de contacts.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

CATEGORIES = {
    "visibility": ("Non déterminé", "Public", "Privé"),
    "account_kind": ("Non déterminé", "Personnel", "Créateur", "Entreprise"),
    "verified_badge": ("Non déterminé", "Badge visible", "Aucun badge visible"),
    "direct_messages": ("Non déterminé", "Messagerie accessible", "Messagerie indisponible"),
}
FIELD_LABELS = {
    "biography": "Biographie visible",
    "category": "Catégorie affichée",
    "visibility": "Visibilité du compte",
    "account_kind": "Type de compte affiché",
    "verified_badge": "Badge affiché",
    "public_website": "Lien externe déclaré par le compte",
    "direct_messages": "Contact via la messagerie de la plateforme",
    "posts": "Publications visibles (compteur)",
    "followers": "Abonnés affichés (compteur)",
    "following": "Abonnements affichés (compteur)",
    "source_description": "Conditions d'observation",
}
LIMITS = {"biography": 1500, "category": 120, "source_description": 1000}
COUNTS = ("posts", "followers", "following")


def normalize_public_url(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    if len(value) > 2048 or any(c.isspace() for c in value):
        raise ValueError("Lien externe trop long ou contenant des espaces.")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Lien externe invalide.") from exc
    if (parsed.scheme != "https" or not parsed.hostname
            or parsed.username or parsed.password or port not in (None, 443)):
        raise ValueError("Seuls les liens externes publics HTTPS, sans identifiant, sont acceptés.")
    hostname = parsed.hostname
    if (hostname == "localhost" or hostname.endswith(".local")
            or hostname.endswith(".internal") or hostname.endswith(".test")
            or re.fullmatch(r"\d+(\.\d+){3}", hostname)
            or ":" in hostname):
        raise ValueError("Adresse de réseau local ou non publique refusée.")
    return value


def parse_visible_count(value) -> int | None:
    """Nombres exactement relevés, sans estimation ni suffixe k/M."""
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    if not re.fullmatch(r"\d{1,3}(?:[ .]\d{3})*|\d{1,10}", text):
        raise ValueError("Saisissez le compteur entier sans abréviation (ex. 12 345).")
    count = int(text.replace(" ", "").replace(".", ""))
    if count > 1_000_000_000:
        raise ValueError("Compteur hors plage.")
    return count


def normalize_snapshot(raw: dict | None) -> dict:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict) or set(raw).difference(FIELD_LABELS):
        raise ValueError("Champs de profil non reconnus.")
    output = {}
    for field in FIELD_LABELS:
        value = raw.get(field, "")
        if field in CATEGORIES:
            value = str(value or "Non déterminé").strip()
            if value not in CATEGORIES[field]:
                raise ValueError(f"Valeur non autorisée pour {FIELD_LABELS[field]}.")
        elif field in COUNTS:
            value = parse_visible_count(value)
        elif field == "public_website":
            value = normalize_public_url(value)
        else:
            value = str(value or "").strip()
            if len(value) > LIMITS[field]:
                raise ValueError(f"Champ trop long : {FIELD_LABELS[field]}.")
        output[field] = value
    return output


def has_public_observation(snapshot: dict) -> bool:
    """Exclut les champs non renseignés et le simple statut 'Non déterminé'."""
    return any(v is not None and v != "" and v != "Non déterminé"
               for v in snapshot.values())


def format_public_snapshot(snapshot: dict) -> str:
    lines = []
    for field, label in FIELD_LABELS.items():
        value = snapshot.get(field)
        if value not in (None, "", "Non déterminé"):
            lines.append(f"{label} : {value}")
    return "\n".join(lines)


def changes_between(previous: dict | None, current: dict) -> list[dict]:
    """Ne compare que deux observations successives du MÊME compte."""
    if not previous:
        return []
    changed = []
    for field, label in FIELD_LABELS.items():
        old = previous.get(field)
        new = current.get(field)
        if old is not None and new is not None and old != new and old not in ("", "Non déterminé") and new not in ("", "Non déterminé"):
            changed.append({"champ": label, "avant": old, "après": new})
    return changed
