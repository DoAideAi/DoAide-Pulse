"""Journey: a piece is translated, the translation is held for review, the
reviewer is stopped once for reading an out-of-date copy, accepts the fresh
one, and the French is what reaches the platform.

A destination can publish in another language, and a translation that fails
Pulse's structural checks is held as ``needs_review`` rather than sent. This
walks the whole of that loop through the API, with the model and the platform
stubbed: the held translation is not used, an edit to the piece makes it stale
and acceptance is refused for it, a re-translation is held again, acceptance
makes it ``ready``, and publishing then sends the French title and body — not
the English the destination would otherwise fall back to.
"""
from __future__ import annotations

import json

import httpx
import pytest

from app.services import ai, llm_router
from app.services.publishers import base

API = "/api/v1"

ENGLISH = (
    "# Publishing with Pulse\n\n"
    "Pulse turns your repository activity into finished posts. Connect an "
    "account, choose the repository to watch, and every release becomes a "
    "complete draft waiting for your review before anything goes out.\n\n"
    "See the [documentation](https://pulse.example.com/docs) for the full "
    "configuration reference. Nothing is published without your approval.\n"
)
#: The French, minus the documentation link — the kind of loss the checks are
#: there for, so the translation is held rather than trusted.
FRENCH = (
    "# Publier avec Pulse\n\n"
    "Pulse transforme l'activité de votre dépôt en articles terminés. "
    "Connectez un compte, choisissez le dépôt à surveiller, et chaque version "
    "devient un brouillon complet qui attend votre relecture avant tout envoi.\n\n"
    "Consultez la documentation pour la référence de configuration complète. "
    "Rien n'est publié sans votre accord.\n"
)


@pytest.fixture
def world(monkeypatch, task_session):
    """The model translates (dropping the link); Buttondown records what it was sent."""
    from app.config import settings
    from app.services import link_check
    from app.tasks import publish_tasks

    monkeypatch.setattr(
        ai,
        "json_completion",
        lambda *a, **k: (
            {
                "title": "Publier avec Pulse",
                "body_markdown": FRENCH,
                "excerpt": "Comment Pulse publie.",
                "meta_description": "Publier avec Pulse, de la version au billet.",
            },
            llm_router.Completion(text="", provider="stub", model="stub-model"),
        ),
    )
    monkeypatch.setattr(base, "_sleep", lambda _seconds: None)
    monkeypatch.setattr(publish_tasks, "SessionLocal", task_session)
    monkeypatch.setattr(settings, "link_check_enabled", False)
    monkeypatch.setattr(link_check, "_unreachable_for_a_reader", lambda _url: None)
    sent: list[dict] = []

    def platform(method, url, **kwargs):
        if method == "GET":
            return httpx.Response(200, json={"username": "fr"}, request=httpx.Request(method, url))
        payload = kwargs.get("json")
        if payload is None and kwargs.get("content"):
            payload = json.loads(kwargs["content"])
        sent.append(payload or {})
        return httpx.Response(
            201,
            json={"id": "em_fr", "absolute_url": "https://buttondown.com/fr/publier"},
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(base, "_exchange", platform)
    return sent


def test_a_held_translation_is_reviewed_accepted_and_published(client, auth, project, world):
    # A French-language destination.
    assert client.put(
        f"{API}/settings/connections",
        headers=auth,
        json={"platform": "buttondown", "credentials": {"api_key": "bd"}, "language": "fr"},
    ).status_code == 200

    piece = client.post(
        f"{API}/content",
        headers=auth,
        json={"project_id": project.id, "title": "Publishing with Pulse", "body_markdown": ENGLISH},
    )
    assert piece.status_code == 201, piece.text
    piece_id = piece.json()["id"]
    url = f"{API}/content/{piece_id}/translations"

    # 1. Translated — and held, because the link did not survive.
    held = client.post(url, headers=auth, json={"language": "fr"})
    assert held.status_code == 201, held.text
    assert held.json()["status"] == "needs_review"
    assert held.json()["publishable"] is False
    assert any(i["code"] == "links_changed" for i in held.json()["quality_issues"])

    # 2. The piece is edited before anyone reviews it: the held copy is now of
    #    words the piece no longer has, and accepting it is refused.
    assert client.patch(
        f"{API}/content/{piece_id}", headers=auth, json={"title": "Publishing with Pulse, revised"}
    ).status_code == 200
    stale = client.post(f"{url}/fr/accept", headers=auth)
    assert stale.status_code == 409
    assert "edited since" in stale.json()["detail"]

    # 3. Translated again, still held; read and accepted this time.
    again = client.post(url, headers=auth, json={"language": "fr"})
    assert again.status_code == 201, again.text
    assert again.json()["status"] == "needs_review" and again.json()["stale"] is False
    accepted = client.post(f"{url}/fr/accept", headers=auth)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "ready"
    assert accepted.json()["publishable"] is True

    # 4. Published: the French is what the platform receives.
    published = client.post(
        f"{API}/content/{piece_id}/publish", headers=auth, json={"platforms": ["buttondown"]}
    )
    assert published.status_code == 200, published.text
    detail = client.get(f"{API}/content/{piece_id}", headers=auth).json()
    assert detail["status"] == "published"
    assert world, "nothing reached the platform"
    body = json.dumps(world[-1], ensure_ascii=False)
    assert "Publier avec Pulse" in body
    assert "Publishing with Pulse" not in body
