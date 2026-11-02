"""Historique des attributs publics observés d'un compte Instagram."""
import json
from account_characteristics import normalize_snapshot, changes_between


class CharacteristicsStore:
    def __init__(self, store):
        self.store = store
        with self.store.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS account_snapshots (
                    observation_id TEXT PRIMARY KEY REFERENCES profile_observations(id),
                    attributes_json TEXT NOT NULL
                );
            """)

    def record(self, case_id: str, observation_id: str, attributes: dict) -> None:
        details = normalize_snapshot(attributes)
        with self.store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            record = conn.execute(
                "SELECT handle FROM profile_observations WHERE id=? AND case_id=?",
                (observation_id, case_id)).fetchone()
            if record is None:
                raise ValueError("Observation absente du dossier.")
            if conn.execute(
                    "SELECT 1 FROM account_snapshots WHERE observation_id=?",
                    (observation_id,)).fetchone():
                raise ValueError("Cette observation possède déjà une fiche non modifiable.")
            conn.execute(
                "INSERT INTO account_snapshots(observation_id,attributes_json) VALUES (?,?)",
                (observation_id, json.dumps(details, ensure_ascii=False, sort_keys=True)))
            self.store._audit(conn, "caracteristiques_profil",
                {"case_id": case_id, "observation_id": observation_id})

    def for_case(self, case_id: str) -> dict:
        with self.store.connect() as conn:
            rows = conn.execute("""
                SELECT p.id, a.attributes_json FROM profile_observations p
                JOIN account_snapshots a ON p.id=a.observation_id
                WHERE p.case_id=?
                """, (case_id,)).fetchall()
        return {row["id"]: json.loads(row["attributes_json"]) for row in rows}

    def timeline_changes(self, observations: list[dict]) -> list[dict]:
        changes = []
        for before, after in zip(observations, observations[1:]):
            for diff in changes_between(before.get("attributes"), after.get("attributes", {})):
                changes.append({
                    "de": before["observed_at"], "a": after["observed_at"], **diff
                })
            if (before.get("display_name") and after.get("display_name")
                    and before["display_name"] != after["display_name"]):
                changes.append({
                    "de": before["observed_at"], "a": after["observed_at"],
                    "champ": "Nom affiché",
                    "avant": before["display_name"], "après": after["display_name"],
                })
        return changes
