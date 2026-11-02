"""Fiches documentaires de profils Instagram observés par un utilisateur.

Aucune recherche d'identité, collecte de coordonnées, requête web ou
corrélation automatique entre personnes n'est effectuée dans ce module.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
import uuid
from urllib.parse import urlsplit

INSTAGRAM_HANDLE = re.compile(r"^[A-Za-z0-9._]{1,30}$")
RESERVED = {"accounts", "about", "direct", "explore", "p", "reels",
            "reel", "stories", "api", "oauth", "developer", "tv"}


def normalize_instagram(value: str) -> tuple[str, str]:
    """Convertit un pseudonyme ou une URL exacte en lien de profil canonique."""
    raw = (value or "").strip()
    if len(raw) > 2048 or not raw:
        raise ValueError("Saisissez un pseudonyme Instagram valide.")
    if raw.startswith("@"):
        raw = raw[1:]
    if raw.casefold().startswith(("instagram.com/", "www.instagram.com/")):
        raw = "https://" + raw
    if "://" in raw:
        parsed = urlsplit(raw)
        if (parsed.scheme != "https" or parsed.hostname not in
                {"instagram.com", "www.instagram.com"} or parsed.username or parsed.password):
            raise ValueError("Seules les URLs HTTPS de profils Instagram sont acceptées.")
        if parsed.port not in (None, 443):
            raise ValueError("Port non standard refusé.")
        raw = parsed.path.strip("/")
        if "/" in raw:
            raise ValueError("L'adresse doit correspondre au profil, pas à une publication.")
    if (not INSTAGRAM_HANDLE.fullmatch(raw)
            or raw.startswith(".") or raw.endswith(".") or ".." in raw
            or raw.casefold() in RESERVED):
        raise ValueError("Pseudonyme non valide.")
    return raw, f"https://www.instagram.com/{raw}/"


class ProfileLog:
    """Journal d'observations de noms affichés, lié aux preuves du dossier."""

    def __init__(self, store):
        self.store = store
        with store.connect() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS profile_observations (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES cases(id),
                profile_id TEXT NOT NULL REFERENCES profiles(id),
                evidence_id TEXT NOT NULL REFERENCES evidence(id),
                handle TEXT NOT NULL,
                url TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                context TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS profile_obs_case
                ON profile_observations(case_id, handle, observed_at);
            """)

    def add(self, case_id: str, raw_handle: str, displayed_name: str,
            observed_at: str, context: str = "",
            files: list[tuple[str, bytes, str]] | None = None) -> str:
        if not self.store.get_case(case_id):
            raise ValueError("Dossier introuvable.")
        handle, url = normalize_instagram(raw_handle)
        name = displayed_name.strip()
        if len(name) > 160:
            raise ValueError("Nom affiché trop long.")
        if len(context) > 5000:
            raise ValueError("Contexte trop long.")
        if not name and not files and not context.strip():
            raise ValueError("Fournissez un nom affiché, une observation publique ou une capture du profil.")
        try:
            dt = datetime.fromisoformat(observed_at)
        except (ValueError, TypeError):
            raise ValueError("Date d'observation invalide.") from None
        if dt.tzinfo is None:
            raise ValueError("La date doit comporter un fuseau horaire.")
        seen = None
        for p in self.store.list_profiles(case_id):
            if p["platform"] == "Instagram" and p["handle"].casefold() == handle.casefold():
                seen = p["id"]
                break
        if seen is None:
            seen = self.store.add_profile(case_id, "Instagram", handle, url, name,
                                          "Nom affiché déclaré, identité du titulaire non vérifiée.")
        transcript = (f"Profil observé : @{handle}\n"
                      f"Nom tel qu'affiché : {name or 'non relevé'}\n"
                      "Information de profil déclarée, sans authentification de l'identité civile.")
        evidence_id = self.store.add_evidence(
            case_id, seen, "Instagram - observation de profil",
            observed_at, handle, url, transcript, context, files or [])
        obs_id = str(uuid.uuid4())
        with self.store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""INSERT INTO profile_observations
                (id,case_id,profile_id,evidence_id,handle,url,observed_at,display_name,context)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (obs_id, case_id, seen, evidence_id, handle, url, observed_at, name, context))
            self.store._audit(conn, "observation_profil",
                {"observation_id": obs_id, "case_id": case_id, "evidence_id": evidence_id})
        return obs_id

    def list(self, case_id: str) -> list[dict]:
        with self.store.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM profile_observations WHERE case_id=? "
                "ORDER BY observed_at DESC, id DESC", (case_id,)).fetchall()
            return [dict(r) for r in rows]

    def timeline(self, case_id: str, handle: str) -> list[dict]:
        username, _ = normalize_instagram(handle)
        return [r for r in reversed(self.list(case_id))
                if r["handle"].casefold() == username.casefold()]

    def names_observed(self, case_id: str, handle: str) -> list[str]:
        return sorted({r["display_name"] for r in self.timeline(case_id, handle)
                       if r["display_name"]})
