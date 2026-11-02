import io
import json
import zipfile

import pytest

from finestalk_core import Store, classify, make_pdf, make_zip, sha256


def make_store(tmp_path):
    store = Store(tmp_path / "vault")
    case = store.create_case("Messages répétés", "Contexte de démonstration")
    profile = store.add_profile(case, "Instagram", "exemple", "https://instagram.com/exemple")
    return store, case, profile


def test_record_and_review(tmp_path):
    store, case, profile = make_store(tmp_path)
    evid = store.add_evidence(
        case, profile, "Instagram - DM", "2026-10-31T12:30:00+01:00",
        "exemple", "https://instagram.com/p/test", "Je vais te frapper, connard.",
        "Capture reçue", [("screen.png", b"fake-example-png", "image/png")])
    items = store.list_evidence(case)
    assert len(items) == 1
    assert "Menaces explicites" in items[0]["categories"]
    assert "Insultes" in items[0]["categories"]
    assert store.verify_attachments(case)[0]["etat"] == "Intègre"
    store.add_note(evid, "Contexte ajouté ultérieurement.")
    assert len(store.list_notes(evid)) == 1
    store.mark_reviewed(evid)
    assert store.list_evidence(case)[0]["confirmed"] == 1
    assert store.verify_audit()["ok"]


def test_tamper_detection(tmp_path):
    store, case, profile = make_store(tmp_path)
    evid = store.add_evidence(case, profile, "Test", "", "auteur", "", "",
                              "Contexte", [("capture.txt", b"original", "text/plain")])
    att = store.list_attachments(evid)[0]
    (store.root / att["relative_path"]).write_bytes(b"modified")
    assert store.verify_attachments(case)[0]["etat"] == "Empreinte différente"
    with pytest.raises(ValueError):
        make_zip(store, case)


def test_unsupported_extension_and_case_isolation(tmp_path):
    store, case, profile = make_store(tmp_path)
    other = store.create_case("Autre dossier")
    with pytest.raises(ValueError):
        store.add_evidence(other, profile, "DM", "", "", "", "exemple", "Contexte", [])
    with pytest.raises(ValueError):
        store.add_evidence(case, profile, "DM", "", "", "", "test", "Contexte",
                           [("malware.exe", b"x", "application/octet-stream")])
    assert store.list_evidence(case) == []


def test_report_export(tmp_path):
    store, case, profile = make_store(tmp_path)
    store.add_evidence(case, profile, "DM", "2026-10-31", "compte", "", "salope",
                       "Contexte", [("message.txt", b"texte", "text/plain")])
    report = store.build_report(case)
    assert report["dossier"]["title"] == "Messages répétés"
    assert make_pdf(report).startswith(b"%PDF")
    exported = make_zip(store, case)
    with zipfile.ZipFile(io.BytesIO(exported)) as archive:
        files = archive.namelist()
        assert "rapport.pdf" in files
        assert "rapport.json" in files
        assert "manifest_sha256.json" in files
        manifest = json.loads(archive.read("manifest_sha256.json"))
        for f in manifest["fichiers"]:
            assert sha256(archive.read(f["chemin"])) == f["sha256"]


def test_empty_and_classification(tmp_path):
    store, case, _ = make_store(tmp_path)
    score, criteria = store.completeness(case)
    assert score == 5
    assert not criteria["Au moins un élément"]["satisfait"]
    assert classify("Bonjour, bonne journée.") == []
    assert "Intimidation" in classify("Je sais où tu habites")


def test_audit_chain_change(tmp_path):
    store, case, _ = make_store(tmp_path)
    assert store.verify_audit()["ok"]
    with store.connect() as conn:
        conn.execute("UPDATE audit SET action='modifiee' WHERE id=1")
    assert store.verify_audit()["ok"] is False
