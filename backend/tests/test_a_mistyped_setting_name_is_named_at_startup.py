"""A key in .env that Pulse does not read is named at startup, with a suggestion.

``Settings`` loads ``.env`` with ``extra="ignore"``, so a misspelled key is
accepted and does nothing: ``SMTP_HOTS=`` leaves mail unconfigured, and
``RATE_LIMIT_LOGN=`` leaves the default in force. A typo is a different key,
so no value check ever saw it, and nothing said the setting had not taken.

Startup now lists the keys in the env files that are neither a setting nor a
known non-Settings key (Postgres, seed and deploy variables), with the setting
each was probably meant to be. Key names only — never a value.

The backup directory had the same split in another form: the health probe
read ``BACKUP_DIR`` while backup.sh reads ``PULSE_BACKUP_DIR``, so moving the
backups with the one the script documents left the probe looking at the old
place, reporting stale forever. ``backup_dir`` accepts both.
"""
from __future__ import annotations

import logging

from app.config import Settings, unknown_env_keys, warn_about_unknown_env_keys


def _env(tmp_path, text):
    path = tmp_path / ".env"
    path.write_text(text)
    return [path]


def test_a_typo_is_found_and_the_meant_setting_suggested(tmp_path):
    text = "SMTP_HOTS=mail.example.com\nRATE_LIMIT_LOGN=5/hour\n"
    found = dict(unknown_env_keys(_env(tmp_path, text)))

    assert found["SMTP_HOTS"] == "SMTP_HOST"
    assert found["RATE_LIMIT_LOGN"] == "RATE_LIMIT_LOGIN"


def test_real_settings_and_known_extras_are_not_flagged(tmp_path):
    text = (
        "SMTP_HOST=mail\n"
        "smtp_port=587\n"
        "POSTGRES_PASSWORD=x\nSEED_EMAIL=a@b.c\nPULSE_BACKUP_RETENTION_DAYS=14\n"
        "# COMMENTED_OUT=1\nexport DEBUG=true\n\n"
    )
    assert unknown_env_keys(_env(tmp_path, text)) == []


def test_a_missing_file_is_not_an_error(tmp_path):
    assert unknown_env_keys([tmp_path / "absent.env"]) == []


def test_the_warning_names_keys_and_never_values(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="app.config"):
        warn_about_unknown_env_keys(_env(tmp_path, "SMTP_HOTS=s3cret-value\n"))

    text = caplog.text
    assert "SMTP_HOTS" in text and "SMTP_HOST" in text
    assert "s3cret-value" not in text


def test_the_backup_directory_answers_to_the_name_backup_sh_documents(monkeypatch):
    monkeypatch.setenv("PULSE_BACKUP_DIR", "/srv/elsewhere")
    monkeypatch.delenv("BACKUP_DIR", raising=False)

    assert Settings(_env_file=None).backup_dir == "/srv/elsewhere"
