"""Interprétation déterministe des quatre types de saisie."""
import pytest

from query_types import Query, interpret, public_search_links


@pytest.mark.parametrize("raw,kind,normalized", [
    ("@quentinlably", "username", "quentinlably"),
    ("quentinlably", "username", "quentinlably"),
    ("https://www.instagram.com/quentinlably/", "username", "quentinlably"),
    ("Jean Dupont", "name", "Jean Dupont"),
    ("Marie-Claire Le Gall", "name", "Marie-Claire Le Gall"),
    ("Élodie D’Artagnan", "name", "Élodie D’Artagnan"),
    ("prenom.nom@example.org", "email", "prenom.nom@example.org"),
    ("06 12 34 56 78", "phone", "06 12 34 56 78"),
    ("+33 6 12 34 56 78", "phone", "+33 6 12 34 56 78"),
    ("0033 6 12 34 56 78", "phone", "0033 6 12 34 56 78"),
    ("1234567890", "username", "1234567890"),
    ("012345", "username", "012345"),
])
def test_detect_input(raw, kind, normalized):
    result = interpret(raw)
    assert result == Query(kind, normalized)


@pytest.mark.parametrize("raw", [
    "", " ", "\n", "x" * 255, "Jean 123",
    "http://malicious.example/path", "https://evil.example/user",
    "nom..prenom@example.org", "a@example", "a@b..com",
    "not an insta handle! 42",
])
def test_reject_bad_input(raw):
    with pytest.raises(ValueError):
        interpret(raw)


def test_only_public_names_and_handles_generate_external_search_links():
    for kind in ("username", "name"):
        result = public_search_links(Query(kind, "Exemple"))
        assert set(result) == {"Google", "Bing", "DuckDuckGo"}
        assert all(url.startswith("https://") for url in result.values())
        assert all("Exemple" in url for url in result.values())
    for kind in ("email", "phone"):
        assert public_search_links(Query(kind, "contact@example.org")) == {}


def test_queries_are_kept_local_without_external_io(monkeypatch):
    import requests

    def raise_request(*args, **kwargs):
        raise AssertionError("Aucun appel réseau n'est autorisé lors de l'analyse")
    monkeypatch.setattr(requests, "get", raise_request)
    assert interpret("marie@example.fr").kind == "email"
    assert interpret("06 12 34 56 78").kind == "phone"
    assert interpret("Marie Dupont").kind == "name"
