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
    (301, "redirection_bloquee"), (302, "redirection_bloquee"),
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


def fake_hops(hops):
    """Inspecte toutes les requêtes, sans ouverture de site réel."""
    expected = list(hops)
    def request(url, **kwargs):
        assert kwargs["allow_redirects"] is False
        assert kwargs["stream"] is True
        assert expected, "Une requête surnuméraire a été effectuée"
        expected_url, result = expected.pop(0)
        assert url == expected_url
        return result
    return request, expected


def test_safe_www_to_bare_domain():
    first = FakeResponse(301)
    first.headers["Location"] = "https://instagram.com/compte.test/"
    second = FakeResponse(200, html=(
        '<meta property="og:title" content="Nom déclaré (@compte.test) • Instagram">'
    ))
    fetch, remaining = fake_hops([
        ("https://www.instagram.com/compte.test/", first),
        ("https://instagram.com/compte.test/", second),
    ])
    result = lookup_public_profile("compte.test", transport=fetch)
    assert result.status == "metadonnees_publiques"
    assert result.display_name == "Nom déclaré"
    assert not remaining


def test_safe_relative_same_profile_redirect():
    first = FakeResponse(302)
    first.headers["Location"] = "/compte.test/?hl=fr"
    second = FakeResponse(200, html=(
        '<meta property="og:title" content="Nom déclaré (@compte.test) • Instagram">'
    ))
    fetch, remaining = fake_hops([
        ("https://www.instagram.com/compte.test/", first),
        ("https://www.instagram.com/compte.test/?hl=fr", second),
    ])
    result = lookup_public_profile("compte.test", transport=fetch)
    assert result.display_name == "Nom déclaré"
    assert not remaining


@pytest.mark.parametrize("redirect", [
    "https://evil.example/compte.test/",
    "http://www.instagram.com/compte.test/",
    "https://www.instagram.com.evil.example/compte.test/",
    "https://attacker:pass@www.instagram.com/compte.test/",
    "https://www.instagram.com:444/compte.test/",
    "//localhost/internal",
    "file:///etc/passwd",
    "/another-account/",
    "/accounts/profile/",
])
def test_never_follow_unsafe_redirects(redirect):
    response = FakeResponse(302)
    response.headers["Location"] = redirect
    fetch, remaining = fake_hops([
        ("https://www.instagram.com/compte.test/", response)
    ])
    result = lookup_public_profile("compte.test", transport=fetch)
    assert result.status in ("redirection_bloquee", "redirection_autre_page")
    assert result.display_name == ""
    assert not remaining


@pytest.mark.parametrize("login_location", [
    "/accounts/login/?next=%2Fcompte.test%2F",
    "https://www.instagram.com/accounts/login/",
    "/accounts/signup/",
    "/challenge/",
])
def test_login_redirect_is_reported_without_following(login_location):
    response = FakeResponse(302)
    response.headers["Location"] = login_location
    fetch, remaining = fake_hops([
        ("https://www.instagram.com/compte.test/", response)
    ])
    result = lookup_public_profile("compte.test", transport=fetch)
    assert result.status == "connexion_requise"
    assert "connexion" in result.message
    assert not remaining


def test_redirect_loop_is_detected():
    first = FakeResponse(301)
    first.headers["Location"] = "/compte.test/?hl=fr"
    second = FakeResponse(301)
    second.headers["Location"] = "/compte.test/"
    fetch, remaining = fake_hops([
        ("https://www.instagram.com/compte.test/", first),
        ("https://www.instagram.com/compte.test/?hl=fr", second),
    ])
    result = lookup_public_profile("compte.test", transport=fetch)
    assert result.status == "boucle_redirection"
    assert not remaining


def test_three_redirect_limit():
    urls = [
        "https://www.instagram.com/compte.test/",
        "https://www.instagram.com/compte.test/?hl=fr",
        "https://www.instagram.com/compte.test/?hl=en",
        "https://www.instagram.com/compte.test/?hl=es",
    ]
    hops = []
    for index, url in enumerate(urls):
        fake = FakeResponse(302)
        fake.headers["Location"] = (
            urls[index + 1] if index + 1 < len(urls)
            else "https://www.instagram.com/compte.test/?hl=de"
        )
        hops.append((url, fake))
    fetch, remaining = fake_hops(hops)
    result = lookup_public_profile("compte.test", transport=fetch)
    assert result.status == "trop_de_redirections"
    assert not remaining
