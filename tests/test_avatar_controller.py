import json
from pathlib import Path

import pytest

from avatar import audit_assets, load_manifest
from brain.emotion_parser import VALID_EMOTIONS


def test_manifest_maps_every_emotion():
    manifest = load_manifest()
    assert set(manifest.emotions) == VALID_EMOTIONS
    assert manifest.emotions["angry"].preview_required


def test_audit_missing_asset_is_actionable(tmp_path):
    report = audit_assets(load_manifest(), tmp_path)
    assert any("smile.exp3.json" in error for error in report["errors"])


def test_manifest_rejects_outfit_in_emotion_mapping(tmp_path):
    data = json.loads(Path("avatar/ulvm2_0001.json").read_text())
    data["emotions"]["happy"]["expression"] = "costume_v0000.exp3.json"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="never an outfit"):
        load_manifest(path)
