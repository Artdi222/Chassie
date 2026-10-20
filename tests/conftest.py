"""Fail fast when browser tests are collected but Playwright's browser is missing.

Without this, every UI test fails with a long launch error that reads like an
application regression.
"""
from pathlib import Path

import pytest

FIX = '.venv/bin/python -m playwright install chromium-headless-shell'


def _uses_playwright(item):
    return 'async_playwright' in Path(str(item.fspath)).read_text(encoding='utf-8')


def pytest_collection_modifyitems(session, config, items):
    if not any(_uses_playwright(item) for item in items):
        return
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            pw.chromium.launch(args=['--no-sandbox']).close()
    except Exception as exc:
        pytest.exit(f'UI tests cannot start a browser ({type(exc).__name__}). Fix: {FIX}', returncode=4)
