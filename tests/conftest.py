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


# Live2D models are not shipped with the repo; tests that render the bundled-in-dev
# Tian Muzi package run only where it has been installed locally under model/Model_4.
HAS_TEST_MODEL = (Path(__file__).resolve().parents[1] / 'model' / 'Model_4').is_dir()


def pytest_runtest_setup(item):
    if item.get_closest_marker('requires_model') and not HAS_TEST_MODEL:
        pytest.skip('needs a local Live2D model in model/Model_4 (models are not shipped)')
