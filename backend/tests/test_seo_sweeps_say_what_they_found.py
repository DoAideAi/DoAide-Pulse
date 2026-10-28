"""The SEO sweeps leave a line saying what they found (C105 M11).

The meta audit stored a site whose sitemap could not be read with its error on
the row and logged nothing: the audit then covered the homepage alone and
reported it clean. Neither sweep wrote a summary either, so the journal said a
task finished and not what it saw. Both now do, and a site with an error is
named at WARNING the way the sitemap sweep already named its problems.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from app.tasks import seo_tasks


@pytest.fixture
def no_db(monkeypatch):
    monkeypatch.setattr(seo_tasks, "SessionLocal", lambda: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(seo_tasks.seo_history, "record_snapshot", lambda db: None)
    monkeypatch.setattr(seo_tasks.seo_history, "record_run", lambda db, kind, rows: None)


def _lines(caplog, level):
    return [r.getMessage() for r in caplog.records if r.levelno == level and r.name == seo_tasks.__name__]


def test_a_site_the_meta_audit_could_not_read_is_named(no_db, monkeypatch, caplog):
    rows = [
        SimpleNamespace(site_key="pulse", issue_count=2, error=None),
        SimpleNamespace(site_key="emibuddy", issue_count=0, error="sitemap: HTTP 502"),
    ]
    monkeypatch.setattr(seo_tasks.meta_audit, "run", lambda db: rows)

    with caplog.at_level(logging.INFO, logger=seo_tasks.__name__):
        assert seo_tasks.audit_meta_tags() == {"audited": 2, "issues": 2}

    assert _lines(caplog, logging.WARNING) == ["meta audit: problems on emibuddy"]
    assert _lines(caplog, logging.INFO) == ["meta audit: 2 site(s), 2 issue(s), 1 with problems"]


def test_a_clean_meta_audit_writes_its_summary_only(no_db, monkeypatch, caplog):
    rows = [SimpleNamespace(site_key="pulse", issue_count=0, error=None)]
    monkeypatch.setattr(seo_tasks.meta_audit, "run", lambda db: rows)

    with caplog.at_level(logging.INFO, logger=seo_tasks.__name__):
        seo_tasks.audit_meta_tags()

    assert _lines(caplog, logging.WARNING) == []
    assert _lines(caplog, logging.INFO) == ["meta audit: 1 site(s), 0 issue(s), 0 with problems"]


def test_the_sitemap_sweep_writes_a_summary_when_all_is_well(no_db, monkeypatch, caplog):
    rows = [SimpleNamespace(site_key="pulse", fetch_error=None, submit_status="submitted")]
    monkeypatch.setattr(seo_tasks.sitemaps, "check", lambda db: rows)

    with caplog.at_level(logging.INFO, logger=seo_tasks.__name__):
        assert seo_tasks.submit_sitemaps() == {"checked": 1, "problems": []}

    assert _lines(caplog, logging.INFO) == ["sitemaps: 1 checked, 0 with problems"]
