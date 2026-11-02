"""Finestalk - registre local de preuves et gestion de dossiers."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import uuid
import zipfile
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

MAX_FILE_BYTES = 25 * 1024 * 1024
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf",
                      ".txt", ".csv", ".json", ".html", ".eml", ".mp4",
                      ".mov", ".wav", ".m4a", ".zip"}
CATEGORIES = {
    "Insultes": [r"\b(?:connard(?:e)?|conna(?:ss)?e|salope|abruti(?:e)?|ordure|merdeux|encul(?:e|ee)|imbecile|idiot(?:e)?)\b"],
    "Menaces explicites": [r"\b(?:je vais|j'vais|on va)\s+(?:te|vous)\s+(?:tuer|frapper|buter|tabasser|agresser)\b",
                            r"\b(?:je vais|j'vais)\s+(?:te|vous)\s+faire\s+du\s+mal\b"],
    "Intimidation": [r"\bje sais (?:ou|où) tu habites\b",
                      r"\b(?:tu vas|vous allez) le regretter\b"],
    "Chantage ou pression": [r"\bsi tu (?:ne |n')?.{0,55}(?:je vais|je publie|j'envoie)\b",
                              r"\b(?:je vais|je peux) publier (?:tes|vos) (?:photos|messages)\b"],
    "Divulgation annoncée": [r"\b(?:je publie|je vais publier|je diffuse|je vais diffuser) (?:ton|ta|tes|votre|vos) (?:adresse|numero|numéro|photos|coordonnees|coordonnées)\b"],
}
SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS cases (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'Ouvert', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS profiles (
 id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id),
 platform TEXT NOT NULL, handle TEXT NOT NULL, url TEXT NOT NULL DEFAULT '',
 public_name TEXT NOT NULL DEFAULT '', observations TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence (
 id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id),
 profile_id TEXT REFERENCES profiles(id), source TEXT NOT NULL,
 occurred_at TEXT NOT NULL DEFAULT '', collected_at TEXT NOT NULL,
 author_display TEXT NOT NULL DEFAULT '', url TEXT NOT NULL DEFAULT '',
 transcript TEXT NOT NULL DEFAULT '', context TEXT NOT NULL DEFAULT '',
 categories TEXT NOT NULL DEFAULT '[]', confirmed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS attachments (
 id TEXT PRIMARY KEY, evidence_id TEXT NOT NULL REFERENCES evidence(id),
 original_name TEXT NOT NULL, relative_path TEXT NOT NULL UNIQUE,
 mime TEXT NOT NULL, sha256 TEXT NOT NULL, size INTEGER NOT NULL,
 collected_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
 id TEXT PRIMARY KEY, evidence_id TEXT NOT NULL REFERENCES evidence(id),
 text TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, action TEXT NOT NULL,
 payload TEXT NOT NULL, prev_hash TEXT NOT NULL, entry_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_case ON evidence(case_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_profiles_case ON profiles(case_id);
"""

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def _row(row):
    return dict(row) if row is not None else None

def classify(text: str) -> list[str]:
    """Repérage lexical indicatif, sans qualification juridique."""
    normalized = text.casefold()
    return [label for label, patterns in CATEGORIES.items()
            if any(re.search(pattern, normalized, re.IGNORECASE) for pattern in patterns)]

def safe_filename(name: str) -> str:
    value = str(name).replace("\\", "/").split("/")[-1]
    value = re.sub(r"[^\w. -]", "_", value, flags=re.UNICODE).strip(". ")
    return value[:140] or "piece"

class Store:
    def __init__(self, directory: str | Path):
        self.root = Path(directory).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "pieces").mkdir(exist_ok=True)
        self.db = self.root / "finestalk.sqlite3"
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def connect(self):
        conn = sqlite3.connect(str(self.db), timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        return conn

    def _audit(self, conn, action: str, payload: dict):
        previous = conn.execute("SELECT entry_hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
        prev = previous["entry_hash"] if previous else "0" * 64
        ts = now_utc()
        encoded = _json(payload)
        digest = sha256(f"{prev}|{ts}|{action}|{encoded}".encode("utf-8"))
        conn.execute("INSERT INTO audit(ts,action,payload,prev_hash,entry_hash) VALUES(?,?,?,?,?)",
                     (ts, action, encoded, prev, digest))

    def create_case(self, title: str, description: str = "") -> str:
        title = title.strip()
        if not title:
            raise ValueError("Le titre est obligatoire.")
        case_id = str(uuid.uuid4())
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO cases VALUES(?,?,?,?,?)",
                         (case_id, title[:200], description[:12000], "Ouvert", now_utc()))
            self._audit(conn, "creation_dossier", {"case_id": case_id, "title": title[:200]})
        return case_id

    def list_cases(self) -> list[dict]:
        with self.connect() as conn:
            return [_row(r) for r in conn.execute(
                "SELECT * FROM cases ORDER BY created_at DESC, title").fetchall()]

    def get_case(self, case_id: str) -> dict | None:
        with self.connect() as conn:
            return _row(conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone())

    def set_status(self, case_id: str, status: str):
        if status not in {"Ouvert", "En cours de signalement", "Transmis", "Clôturé"}:
            raise ValueError("Statut non valide.")
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if not conn.execute("SELECT 1 FROM cases WHERE id=?", (case_id,)).fetchone():
                raise ValueError("Dossier introuvable.")
            conn.execute("UPDATE cases SET status=? WHERE id=?", (status, case_id))
            self._audit(conn, "statut_dossier", {"case_id": case_id, "status": status})

    def add_profile(self, case_id: str, platform: str, handle: str,
                    url: str = "", public_name: str = "", observations: str = "") -> str:
        if not self.get_case(case_id):
            raise ValueError("Dossier introuvable.")
        if not handle.strip():
            raise ValueError("Le pseudonyme est obligatoire.")
        profile_id = str(uuid.uuid4())
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO profiles VALUES(?,?,?,?,?,?,?,?)",
                         (profile_id, case_id, platform[:80], handle.strip()[:150],
                          url.strip()[:2000], public_name.strip()[:200],
                          observations.strip()[:12000], now_utc()))
            self._audit(conn, "ajout_profil", {"case_id": case_id, "profile_id": profile_id,
                                              "platform": platform, "handle": handle.strip()[:150]})
        return profile_id

    def list_profiles(self, case_id: str) -> list[dict]:
        with self.connect() as conn:
            return [_row(r) for r in conn.execute(
                "SELECT * FROM profiles WHERE case_id=? ORDER BY created_at", (case_id,))]

    def add_evidence(self, case_id: str, profile_id: str | None, source: str,
                     occurred_at: str, author_display: str, url: str,
                     transcript: str, context: str, files: list[tuple[str, bytes, str]] | None = None,
                     manual_categories: list[str] | None = None) -> str:
        if not self.get_case(case_id):
            raise ValueError("Dossier introuvable.")
        if not transcript.strip() and not files:
            raise ValueError("Ajoutez au moins un texte ou une pièce.")
        if len(transcript) > 100_000:
            raise ValueError("Texte trop long (100 000 caractères maximum).")
        if profile_id:
            if profile_id not in {p["id"] for p in self.list_profiles(case_id)}:
                raise ValueError("Ce profil n'appartient pas au dossier.")
        files = files or []
        if len(files) > 15:
            raise ValueError("15 fichiers maximum par élément.")
        for name, content, mime in files:
            if Path(safe_filename(name)).suffix.lower() not in ALLOWED_EXTENSIONS:
                raise ValueError(f"Type de fichier non accepté : {name}")
            if len(content) > MAX_FILE_BYTES:
                raise ValueError(f"Fichier trop volumineux : {name}")
        evidence_id = str(uuid.uuid4())
        categories = sorted(set(classify(transcript)) | set(manual_categories or []))
        written = []
        try:
            with self.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("""INSERT INTO evidence
                (id,case_id,profile_id,source,occurred_at,collected_at,author_display,url,transcript,context,categories,confirmed)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,0)""",
                (evidence_id, case_id, profile_id, source[:100], occurred_at[:100],
                 now_utc(), author_display[:200], url[:2500], transcript, context[:12000], _json(categories)))
                for name, content, mime in files:
                    file_id = str(uuid.uuid4())
                    base = safe_filename(name)
                    dest = self.root / "pieces" / (file_id + Path(base).suffix.lower())
                    # Exclusif: une pièce déjà écrite n'est jamais écrasée.
                    with dest.open("xb") as stream:
                        stream.write(content)
                    written.append(dest)
                    relative = dest.relative_to(self.root).as_posix()
                    conn.execute("INSERT INTO attachments VALUES(?,?,?,?,?,?,?,?)",
                                 (file_id, evidence_id, base, relative, mime[:150],
                                  sha256(content), len(content), now_utc()))
                self._audit(conn, "ajout_preuve",
                            {"case_id": case_id, "evidence_id": evidence_id,
                             "attachment_hashes": [sha256(content) for _, content, _ in files]})
        except Exception:
            for path in written:
                path.unlink(missing_ok=True)
            raise
        return evidence_id

    def list_evidence(self, case_id: str) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("""SELECT e.*,p.handle AS profile_handle,
                p.platform AS profile_platform FROM evidence e
                LEFT JOIN profiles p ON e.profile_id=p.id
                WHERE e.case_id=? ORDER BY e.occurred_at DESC, e.collected_at DESC""",
                (case_id,)).fetchall()
        return [dict(r, categories=json.loads(r["categories"])) for r in rows]

    def list_attachments(self, evidence_id: str) -> list[dict]:
        with self.connect() as conn:
            return [_row(r) for r in conn.execute(
                "SELECT * FROM attachments WHERE evidence_id=? ORDER BY collected_at", (evidence_id,))]

    def attachment_bytes(self, attachment: dict) -> bytes:
        path = (self.root / attachment["relative_path"]).resolve()
        if not path.is_relative_to((self.root / "pieces").resolve()):
            raise ValueError("Chemin de pièce invalide.")
        return path.read_bytes()

    def add_note(self, evidence_id: str, text: str) -> str:
        text = text.strip()
        if not text:
            raise ValueError("Note vide.")
        note_id = str(uuid.uuid4())
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT case_id FROM evidence WHERE id=?", (evidence_id,)).fetchone()
            if not row:
                raise ValueError("Élément introuvable.")
            conn.execute("INSERT INTO notes VALUES(?,?,?,?)",
                         (note_id, evidence_id, text[:10000], now_utc()))
            self._audit(conn, "note_ajoutee", {"case_id": row["case_id"],
                                               "evidence_id": evidence_id, "note_id": note_id})
        return note_id

    def list_notes(self, evidence_id: str) -> list[dict]:
        with self.connect() as conn:
            return [_row(r) for r in conn.execute(
                "SELECT * FROM notes WHERE evidence_id=? ORDER BY created_at", (evidence_id,))]

    def mark_reviewed(self, evidence_id: str):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT case_id FROM evidence WHERE id=?", (evidence_id,)).fetchone()
            if not row:
                raise ValueError("Élément introuvable.")
            conn.execute("UPDATE evidence SET confirmed=1 WHERE id=?", (evidence_id,))
            self._audit(conn, "relecture_humaine", {"case_id": row["case_id"],
                                                    "evidence_id": evidence_id})

    def verify_attachments(self, case_id: str) -> list[dict]:
        output = []
        for event in self.list_evidence(case_id):
            for att in self.list_attachments(event["id"]):
                try:
                    raw = self.attachment_bytes(att)
                    valid = len(raw) == att["size"] and sha256(raw) == att["sha256"]
                    state = "Intègre" if valid else "Empreinte différente"
                except (OSError, ValueError):
                    state = "Manquant ou inaccessible"
                output.append({"element": event["id"], "fichier": att["original_name"],
                               "sha256": att["sha256"], "etat": state})
        return output

    def verify_audit(self) -> dict:
        prev = "0" * 64
        count = 0
        with self.connect() as conn:
            for row in conn.execute("SELECT * FROM audit ORDER BY id"):
                digest = sha256(f"{prev}|{row['ts']}|{row['action']}|{row['payload']}".encode("utf-8"))
                if row["prev_hash"] != prev or digest != row["entry_hash"]:
                    return {"ok": False, "entrees": count, "erreur": f"Rupture à l'entrée {row['id']}"}
                prev = digest
                count += 1
        return {"ok": True, "entrees": count, "dernier_hash": prev}

    def completeness(self, case_id: str) -> tuple[int, dict]:
        events = self.list_evidence(case_id)
        profiles = self.list_profiles(case_id)
        tests = {
            "Au moins un élément": (15, bool(events)),
            "Faits sur deux dates distinctes": (15, len({e["occurred_at"][:10] for e in events if e["occurred_at"]}) >= 2),
            "Au moins une pièce originale": (15, any(self.list_attachments(e["id"]) for e in events)),
            "Au moins une URL source": (15, any(e["url"].strip() for e in events)),
            "Date des faits renseignée partout": (15, bool(events) and all(e["occurred_at"] for e in events)),
            "Contexte documenté": (10, any(e["context"].strip() for e in events)),
            "Tous les éléments relus": (10, bool(events) and all(e["confirmed"] for e in events)),
            "Au moins un profil consigné": (5, bool(profiles)),
        }
        return sum(points for points, passed in tests.values() if passed), {
            label: {"points": points, "satisfait": passed}
            for label, (points, passed) in tests.items()
        }

    def build_report(self, case_id: str) -> dict:
        case = self.get_case(case_id)
        if not case:
            raise ValueError("Dossier introuvable.")
        events = self.list_evidence(case_id)
        attachments = {e["id"]: self.list_attachments(e["id"]) for e in events}
        notes = {e["id"]: self.list_notes(e["id"]) for e in events}
        score, checks = self.completeness(case_id)
        return {"dossier": case, "profils_observes": self.list_profiles(case_id),
                "elements": events, "pieces": attachments, "notes": notes,
                "integrite": self.verify_attachments(case_id),
                "journal": self.verify_audit(), "completude": score,
                "criteres_completude": checks, "genere_le": now_utc(),
                "avertissement": "Repérages lexicaux indicatifs; aucune inférence d'identité ni qualification juridique."}

def make_pdf(report: dict) -> bytes:
    """Rapport paginé, autoportant; pièces annexées séparément dans le ZIP."""
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    for font_path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                      "C:/Windows/Fonts/arial.ttf"):
        if Path(font_path).is_file():
            pdfmetrics.registerFont(TTFont("FinestalkFont", font_path))
            break
    font = "FinestalkFont" if "FinestalkFont" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=18*mm, leftMargin=18*mm,
                            topMargin=18*mm, bottomMargin=18*mm, title="Dossier Finestalk")
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(name="FTTitle", fontName=font, fontSize=17, leading=23, spaceAfter=12,
                         textColor=colors.HexColor("#183047")))
    s.add(ParagraphStyle(name="FTSection", fontName=font, fontSize=11, leading=16, spaceBefore=12,
                         spaceAfter=7, textColor=colors.HexColor("#18466c")))
    s.add(ParagraphStyle(name="FTBody", fontName=font, fontSize=8.5, leading=13, spaceAfter=5,
                         wordWrap="CJK"))
    story = []
    def p(value, style="FTBody"):
        text = escape(str(value or "Non renseigné")).replace("\n", "<br/>")
        story.append(Paragraph(text, s[style]))
    p("FINESTALK - Dossier de conservation des preuves", "FTTitle")
    case = report["dossier"]
    p("Dossier : " + case["title"])
    p("État : " + case["status"] + " | Créé : " + case["created_at"])
    p("Rapport généré : " + report["genere_le"])
    p(case["description"])
    p("Ce rapport conserve des déclarations et pièces fournies par l'utilisateur. Les catégories lexicales ne constituent ni une qualification pénale ni une identification.", "FTBody")
    story.append(HRFlowable(width="100%", thickness=.7, color=colors.grey))
    p("Profils et comptes mentionnés", "FTSection")
    for profile in report["profils_observes"]:
        p(f"{profile['platform']} / @{profile['handle']} | URL : {profile['url'] or 'non renseignée'}")
        p(f"Nom affiché (déclaration publique non vérifiée) : {profile['public_name'] or 'non renseigné'}")
        if profile["observations"]:
            p(profile["observations"])
    p("Chronologie des éléments", "FTSection")
    for i, event in enumerate(sorted(report["elements"], key=lambda x: x["occurred_at"] or x["collected_at"]), 1):
        p(f"{i}. Élément {event['id'][:8]} | Faits : {event['occurred_at'] or 'date inconnue'} | Collecte : {event['collected_at']}", "FTSection")
        p(f"Source : {event['source']} | Auteur indiqué : {event['author_display'] or 'inconnu'}")
        p(f"Compte associé : {event.get('profile_handle') or 'non associé'} | URL : {event['url'] or 'non renseignée'}")
        p("Transcription : " + (event["transcript"] or "(aucune)"))
        p("Contexte : " + (event["context"] or "(aucun)"))
        p("Catégories indicatives : " + (", ".join(event["categories"]) or "Aucune détection lexicale"))
        p("Relecture : " + ("effectuée" if event["confirmed"] else "à effectuer"))
        for attachment in report["pieces"][event["id"]]:
            p(f"Pièce : {attachment['original_name']} | SHA-256 : {attachment['sha256']}")
        for note in report["notes"][event["id"]]:
            p(f"Annotation ({note['created_at']}) : {note['text']}")
        story.append(Spacer(1, 5*mm))
    p("Contrôles d'intégrité", "FTSection")
    p("Journal d'audit : " + ("chaîne cohérente" if report["journal"]["ok"] else "incohérence détectée"))
    for item in report["integrite"]:
        p(f"{item['fichier']} : {item['etat']} | {item['sha256']}")
    p(f"Complétude documentaire : {report['completude']}/100 (ce n'est pas une probabilité d'identification)", "FTSection")
    for name, state in report["criteres_completude"].items():
        p(f"{name} : {'oui' if state['satisfait'] else 'non'} ({state['points']} points)")
    doc.build(story)
    return buf.getvalue()

def make_zip(store: Store, case_id: str) -> bytes:
    report = store.build_report(case_id)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        report_bytes = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
        pdf_bytes = make_pdf(report)
        archive.writestr("rapport.json", report_bytes)
        archive.writestr("rapport.pdf", pdf_bytes)
        manifest = {"format": "Finestalk 1", "dossier": case_id,
                    "fichiers": [{"chemin": "rapport.json", "sha256": sha256(report_bytes)},
                                 {"chemin": "rapport.pdf", "sha256": sha256(pdf_bytes)}]}
        for event in report["elements"]:
            for att in report["pieces"][event["id"]]:
                raw = store.attachment_bytes(att)
                if sha256(raw) != att["sha256"] or len(raw) != att["size"]:
                    raise ValueError(f"Pièce altérée ou introuvable : {att['original_name']}")
                filename = f"pieces/{event['id']}/{att['id']}_{att['original_name']}"
                archive.writestr(filename, raw)
                manifest["fichiers"].append({"chemin": filename, "sha256": att["sha256"]})
        archive.writestr("manifest_sha256.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return output.getvalue()
