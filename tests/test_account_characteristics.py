"""Tests pour les seules caractéristiques publiques du compte."""
import io
import zipfile

import pytest

from account_characteristics import (
    changes_between, format_public_snapshot, has_public_observation,
    normalize_public_url, normalize_snapshot, parse_visible_count
)
from account_characteristics_store import CharacteristicsStore
from finestalk_core import Store, make_zip
from profile_review import ProfileLog


@pytest.mark.parametrize("value,expected", [
    ("", None), ("0", 0), ("1 240", 1240),
    ("2.345", 2345), ("999999", 999999)
])
def test_counter_valid(value, expected):
    assert parse_visible_count(value) == expected


@pytest.mark.parametrize("value", ["12k", "-1", "1,5", "1e5", "NaN", "1234567890123"])
def test_counter_invalid(value):
    with pytest.raises(ValueError):
        parse_visible_count(value)


@pytest.mark.parametrize("address", [
    "http://example.org", "https://localhost/",
    "https://127.0.0.1/", "file:///etc/passwd",
    "https://user:pass@example.org/", "https://example.org:8443/",
    "https://home.internal/"])
def test_only_public_https(address):
    with pytest.raises(ValueError):
        normalize_public_url(address)


def test_snapshot_validation():
    data = normalize_snapshot({
        "biography": "Compte de démonstration",
        "category": "Artiste",
        "visibility": "Public",
        "account_kind": "Créateur",
        "verified_badge": "Aucun badge visible",
        "direct_messages": "Messagerie accessible",
        "public_website": "https://example.org/",
        "posts": "20",
        "followers": "5 000",
        "following": "31",
        "source_description": "Capture d'écran",
    })
    assert data["followers"] == 5000
    assert "Biographie visible" in format_public_snapshot(data)
    assert has_public_observation(data)
    assert not has_public_observation(normalize_snapshot({}))
    with pytest.raises(ValueError):
        normalize_snapshot({"home_address": "adresse privée"})
    with pytest.raises(ValueError):
        normalize_snapshot({"visibility": "une valeur inconnue"})
    assert normalize_public_url("https://example.org/contact") == "https://example.org/contact"


def test_same_account_changes():
    before = normalize_snapshot({"biography": "Avant", "followers": "5"})
    after = normalize_snapshot({"biography": "Après", "followers": "6"})
    diffs = changes_between(before, after)
    assert {d["champ"] for d in diffs} == {
        "Biographie visible", "Abonnés affichés (compteur)"}


def test_stored_with_evidence_and_exports(tmp_path):
    store = Store(tmp_path / "data")
    review = ProfileLog(store)
    details = CharacteristicsStore(store)
    case = store.create_case("Dossier de test")
    snap = normalize_snapshot({
        "biography": "Présentation visible",
        "public_website": "https://example.org/",
        "followers": 42,
        "source_description": "Capture du profil."
    })
    obs = review.add(
        case, "profil_demo", "", "2026-11-02T22:00:00+01:00",
        "Caractéristiques visibles :\n" + format_public_snapshot(snap),
        [("profil.png", b"demo", "image/png")])
    details.record(case, obs, snap)
    observed = details.for_case(case)
    assert observed[obs]["followers"] == 42
    assert len(review.timeline(case, "profil_demo")) == 1
    assert store.verify_audit()["ok"]
    assert store.verify_attachments(case)[0]["etat"] == "Intègre"
    assert "Biographie visible" in store.list_evidence(case)[0]["context"]
    with zipfile.ZipFile(io.BytesIO(make_zip(store, case))) as archive:
        assert "rapport.pdf" in archive.namelist()
        assert any(path.endswith("profil.png") for path in archive.namelist())
    with pytest.raises(ValueError, match="déjà"):
        details.record(case, obs, snap)


def test_history_and_isolation(tmp_path):
    store = Store(tmp_path / "data")
    review = ProfileLog(store)
    details = CharacteristicsStore(store)
    c1 = store.create_case("Première affaire")
    c2 = store.create_case("Deuxième affaire")
    observations = []
    for text, moment in [
        ("Bio A", "2026-10-31T15:00:00+01:00"),
        ("Bio B", "2026-11-02T15:00:00+01:00")]:
        obs = review.add(c1, "@profil_demo", "", moment, text)
        details.record(c1, obs, {"biography": text})
        observations.append(obs)
    other = review.add(c2, "@profil_demo", "", "2026-11-02T18:00:00+01:00", "Autre")
    details.record(c2, other, {"biography": "Autre"})
    attrs = details.for_case(c1)
    assert set(attrs) == set(observations)
    rows = [{**item, "attributes": attrs.get(item["id"], {})}
            for item in review.timeline(c1, "profil_demo")]
    differences = details.timeline_changes(rows)
    assert len(differences) == 1
    assert differences[0]["avant"] == "Bio A"
    assert differences[0]["après"] == "Bio B"
    with pytest.raises(ValueError):
        details.record(c1, other, {"biography": "Intrusion"})
