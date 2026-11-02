"""Tests de la recherche unique, sans requêtes vers Instagram."""
import requests
import pytest

from instagram_lookup import extract_metadata, lookup_public_profile
from profile_review import normalize_instagram


class FakeResponse:
    def __init__(self, status=200, html="", content_type="text/html", encoding="utf-8"):
        self.status_code = status
        self.body = html.encode("utf-8")
        self.headers = {"Content-Type": content_type}
        self.encoding = encoding

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def iter_content(self, chunk_size=16384):
        for index in range(0, len(self.body), chunk_size):
            yield self.body[index : index + chunk_size]


def fake_request(response):
    def request(url, **kwargs):
        assert url == "https://www.instagram.com/compte.test/"
        assert kwargs["allow_redirects"] is False
        assert kwargs["stream"] is True
        assert kwargs["timeout"][0] > 0
        assert kwargs["timeout"][1] <= 15
        return response
    return request


def test_metadata_only_for_matching_handle():
    html = """<html><head>
        <title>Instagram</title>
        <meta property="og:title" content="Nom Publiquement Affiché (@compte.test) • Instagram photos">
        <meta property="og:description" content="Description visible &amp; publique">
        </head></html>"""
    name, title, description = extract_metadata(html, "compte.test")
    assert name == "Nom Publiquement Affiché"
    assert description == "Description visible & publique"
    assert "@compte.test" in title


def test_other_account_is_not_attributed():
    html = """<meta property="og:title" content="Personne X (@autre.compte) • Instagram">"""
    name, _, _ = extract_metadata(html, "compte.test")
    assert name == ""


def test_matching_name_is_only_displayed_name():
    html = """<meta property="og:title" content="Nom d'affichage (@compte.test) • Instagram">
              <meta name="description" content="Présentation publique">"""
    result = lookup_public_profile("@compte.test", transport=fake_request(FakeResponse(html=html)))
    assert result.status == "metadonnees_publiques"
    assert result.display_name == "Nom d'affichage"
    assert result.public_description == "Présentation publique"
    assert result.canonical_url == "https://www.instagram.com/compte.test/"
    assert "sans vérification d'identité" in result.message


@pytest.mark.parametrize("status,expected", [
    (301, "redirection"), (302, "redirection"),
    (401, "acces_limite"), (403, "acces_limite"),
    (429, "acces_limite"), (404, "indisponible"),
    (500, "erreur"),
])
def test_unavailable_profiles(status, expected):
    result = lookup_public_profile("compte.test", transport=fake_request(FakeResponse(status)))
    assert result.status == expected
    assert result.display_name == ""


def test_non_html_and_large_response():
    bad = lookup_public_profile(
        "compte.test", transport=fake_request(FakeResponse(content_type="application/json")))
    assert bad.status == "format_inattendu"
    large = lookup_public_profile(
        "compte.test", transport=fake_request(FakeResponse(html="x" * 540000)))
    assert large.status == "page_trop_grande"


def test_login_page_not_mistaken_for_profile():
    result = lookup_public_profile("compte.test", transport=fake_request(
        FakeResponse(html="<html><head><title>Instagram Log in</title></head></html>")))
    assert result.status == "connexion_requise"
    assert not result.display_name


def test_partial_metadata_without_name():
    html = """<meta name="description" content="Compte @compte.test sur Instagram">"""
    result = lookup_public_profile("compte.test", transport=fake_request(FakeResponse(html=html)))
    assert result.status == "metadonnees_partielles"
    assert not result.display_name


def test_unrelated_page_has_no_verified_metadata():
    result = lookup_public_profile(
        "compte.test", transport=fake_request(FakeResponse(html="<title>Instagram</title>")))
    assert result.status == "aucune_donnee"
    assert not result.display_name


def test_network_error_is_caught():
    def timeout(*args, **kwargs):
        raise requests.Timeout("délai dépassé")
    result = lookup_public_profile("compte.test", transport=timeout)
    assert result.status == "erreur_reseau"


@pytest.mark.parametrize("value", [
    "https://127.0.0.1/admin", "https://evil.example/compte.test",
    "https://instagram.com/accounts/login/",
    "https://instagram.com/compte.test/p/post",
    "file:///etc/passwd", "a..b", "x" * 31,
])
def test_untrusted_targets_rejected(value):
    with pytest.raises(ValueError):
        normalize_instagram(value)
