"""Tests de validation et de traçabilité des observations de profils."""
import io
import zipfile
import pytest
from finestalk_core import Store, make_zip
from profile_review import ProfileLog, normalize_instagram

@pytest.mark.parametrize("value,expected", [
    ("@exemple", "exemple"),
    ("https://instagram.com/Exemple/", "Exemple"),
    ("www.instagram.com/demo.test/", "demo.test"),
    ("_test_01", "_test_01"),
])
def test_valid_handles(value, expected):
    handle, url = normalize_instagram(value)
    assert handle == expected
    assert url == f"https://www.instagram.com/{expected}/"

@pytest.mark.parametrize("value", [
    "", "@", "../../etc/passwd", "https://localhost/test",
    "https://instagram.com/p/publication", "https://evil.example/profile",
    "http://instagram.com/exemple", "https://instagram.com/accounts/",
    "hello..world", ".wrong", "bad.", "a" * 31,
    "https://username:password@instagram.com/victim/",
])
def test_invalid_handles(value):
    with pytest.raises(ValueError):
        normalize_instagram(value)

def test_observation_and_export(tmp_path):
    store = Store(tmp_path / "data")
    case = store.create_case("Situation signalée")
    review = ProfileLog(store)
    obs = review.add(case, "@exemple", "Nom affiché",
        "2026-11-02T11:42:00+01:00",
        "Consultation directe du profil public.",
        [("capture.png", b"capture-demo", "image/png")])
    assert obs
    history = review.timeline(case, "exemple")
    assert len(history) == 1
    assert history[0]["display_name"] == "Nom affiché"
    assert store.list_evidence(case)[0]["id"] == history[0]["evidence_id"]
    assert store.verify_attachments(case)[0]["etat"] == "Intègre"
    assert store.verify_audit()["ok"]
    with zipfile.ZipFile(io.BytesIO(make_zip(store, case))) as archive:
        assert any(x.endswith("capture.png") for x in archive.namelist())

def test_history_and_case_separation(tmp_path):
    store = Store(tmp_path / "data")
    c1 = store.create_case("Dossier 1")
    c2 = store.create_case("Dossier 2")
    review = ProfileLog(store)
    review.add(c1, "exemple", "Nom A", "2026-10-31T10:00:00+01:00")
    review.add(c1, "exemple", "Nom B", "2026-11-02T10:00:00+01:00")
    review.add(c2, "exemple", "Autre", "2026-11-02T11:00:00+01:00")
    assert review.names_observed(c1, "exemple") == ["Nom A", "Nom B"]
    assert len(review.timeline(c1, "exemple")) == 2
    assert len(review.list(c2)) == 1
    assert len(store.list_profiles(c1)) == 1
    assert store.verify_audit()["ok"]

def test_invalid_observations(tmp_path):
    store = Store(tmp_path / "data")
    case = store.create_case("Dossier")
    review = ProfileLog(store)
    with pytest.raises(ValueError, match="Fournissez"):
        review.add(case, "exemple", "", "2026-11-02T10:00:00+01:00")
    with pytest.raises(ValueError, match="fuseau"):
        review.add(case, "exemple", "Nom", "2026-11-02T10:00:00")
    with pytest.raises(ValueError, match="invalide"):
        review.add(case, "exemple", "Nom", "bad")
    assert store.list_evidence(case) == []
