"""Vérifications hors réseau du moteur de présence publique."""
from concurrent.futures import ThreadPoolExecutor
import json

import pytest
import requests

from public_presence import (
    MAX_BODY, PLATFORMS, _endpoint, check_platform, check_public_presence,
    search_links,
)


class FakeResponse:
    def __init__(self, status=200, body=None, content_type="application/json"):
        self.status_code = status
        self.headers = {"Content-Type": content_type}
        self.body = (json.dumps(body).encode("utf-8")
                     if not isinstance(body, bytes) else body)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def iter_content(self, chunk_size=8192):
        for i in range(0, len(self.body), chunk_size):
            yield self.body[i:i + chunk_size]


def fake_get(response):
    def fn(url, **kwargs):
        assert url.startswith("https://")
        assert kwargs["allow_redirects"] is False
        assert kwargs["stream"] is True
        assert kwargs["timeout"][1] <= 10
        return response
    return fn


@pytest.mark.parametrize("platform,handle,payload", [
    ("GitHub", "octocat", {"login": "octocat", "name": "pas utilisé"}),
    ("GitLab", "octocat", [{"username": "OCTOCAT"}]),
    ("DEV Community", "ben", {"username": "ben"}),
    ("Chess.com", "hikaru", {"username": "Hikaru"}),
    ("Hacker News", "pg", {"id": "pg"}),
])
def test_exact_positive(platform, handle, payload):
    result = check_platform(platform, handle, http_get=fake_get(FakeResponse(body=payload)))
    assert result.state == "found"
    assert result.profile_url.startswith("https://")
    assert result.http_status == 200
    assert "identité" not in result.description


@pytest.mark.parametrize("platform,handle,payload", [
    ("GitLab", "octocat", []),
    ("Hacker News", "pg", None),
])
def test_proven_absence_of_public_record(platform, handle, payload):
    result = check_platform(platform, handle, http_get=fake_get(FakeResponse(body=payload)))
    assert result.state == "absent"


def test_mismatch_does_not_count_as_found():
    result = check_platform(
        "GitHub", "octocat",
        http_get=fake_get(FakeResponse(body={"login": "someone_else"}))
    )
    assert result.state == "unknown"


@pytest.mark.parametrize("status,expected", [
    (404, "absent"), (401, "unknown"), (403, "unknown"),
    (429, "unknown"), (500, "unknown"), (302, "unknown"),
])
def test_http_status_handling(status, expected):
    result = check_platform("GitHub", "octocat", http_get=fake_get(FakeResponse(status)))
    assert result.state == expected


def test_bad_responses_are_not_proof():
    for response in (
        FakeResponse(200, b"not json"),
        FakeResponse(200, {"login": "octocat"}, "text/html"),
        FakeResponse(200, b"a" * (MAX_BODY + 1)),
    ):
        result = check_platform("GitHub", "octocat", http_get=fake_get(response))
        assert result.state == "unknown"


def test_network_failure_nonfatal():
    def error(*args, **kwargs):
        raise requests.Timeout("network unavailable")
    results = check_public_presence("quentinlably", http_get=error)
    assert len(results) == len(PLATFORMS)
    assert all(item.state in {"unknown", "unsupported"} for item in results)


def test_source_urls_fixed_and_escaped():
    assert _endpoint("GitHub", "octocat")[0] == "https://api.github.com/users/octocat"
    assert _endpoint("DEV Community", "ben")[0] == "https://dev.to/api/users/by_username?url=ben"
    assert _endpoint("Chess.com", "hikaru")[0] == "https://api.chess.com/pub/player/hikaru"
    assert _endpoint("Hacker News", "pg")[1] == "https://news.ycombinator.com/user?id=pg"
    assert _endpoint("GitHub", "some.user") is None
    with pytest.raises(ValueError):
        check_public_presence("https://evil.example/hack", http_get=fake_get(FakeResponse()))


def test_search_engines_are_links_not_scraped():
    links = search_links("@quentinlably")
    assert set(links) == {"Google", "Bing", "DuckDuckGo"}
    assert all("quentinlably" in link for link in links.values())
    assert all(link.startswith("https://") for link in links.values())


def test_exact_match_not_cross_platform_attribution():
    def reply(url, **kwargs):
        if "github.com/users/" in url:
            return FakeResponse(body={"login": "quelquun"})
        if "gitlab.com/api/v4/users" in url:
            return FakeResponse(body=[{"username": "quelquun"}])
        return FakeResponse(status=404)
    results = check_public_presence("quelquun", http_get=reply)
    assert sum(item.state == "found" for item in results) == 2
    assert all(not hasattr(item, "real_name") and not hasattr(item, "probability")
               for item in results)
