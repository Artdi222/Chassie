"""Explicit expression files and read-only validation of the bundled avatar."""
from dataclasses import dataclass
import json
from pathlib import Path

from brain.emotion_parser import VALID_EMOTIONS

DEFAULT_MANIFEST = Path(__file__).with_name("ulvm2_0001.json")


@dataclass(frozen=True)
class ExpressionMapping:
    expression: str | None
    fx: str | None
    preview_required: bool
    note: str

    @property
    def files(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(f for f in (self.expression, self.fx) if f))


@dataclass(frozen=True)
class AvatarManifest:
    model_id: str
    model_file: str
    emotions: dict[str, ExpressionMapping]

    @property
    def managed_files(self) -> frozenset[str]:
        return frozenset(f for mapping in self.emotions.values() for f in mapping.files)


def load_manifest(path: str | Path = DEFAULT_MANIFEST) -> AvatarManifest:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("version") != 1 or not data.get("model_id"):
        raise ValueError("Avatar manifest requires version 1 and an explicit model_id")
    if set(data["emotions"]) != VALID_EMOTIONS:
        raise ValueError("Avatar manifest must map exactly all 16 supported emotions")
    emotions = {}
    for emotion, item in data["emotions"].items():
        mapping = ExpressionMapping(**item)
        for filename in mapping.files:
            if (not filename.endswith(".exp3.json") or "/" in filename or "\\" in filename
                    or filename.startswith("costume_")):
                raise ValueError(f"{emotion}: expected expression basename, never an outfit: {filename}")
        emotions[emotion] = mapping
    if emotions["neutral"].files:
        raise ValueError("Neutral must clear managed expressions without activating an asset")
    model_file = data["model_file"]
    if Path(model_file).name != model_file or not model_file.endswith(".model3.json"):
        raise ValueError("model_file must be a model3.json basename")
    return AvatarManifest(data["model_id"], model_file, emotions)


def audit_assets(manifest: AvatarManifest, model_dir: str | Path) -> dict:
    """No model mutation or live renderer access; preview notes are not visual approval."""
    model_dir = Path(model_dir)
    errors, warnings, assets = [], [], {}
    inventory: dict[str, list[Path]] = {}
    for path in sorted(model_dir.rglob("*.exp3.json")):
        inventory.setdefault(path.name, []).append(path)
    for filename, paths in inventory.items():
        if len(paths) != 1:
            errors.append(f"Ambiguous expression basename: {filename}")
            continue
        try:
            data = json.loads(paths[0].read_text(encoding="utf-8"))
            parameters = data["Parameters"]
            if not isinstance(parameters, list):
                raise ValueError("Parameters must be an array")
            ids = [p["Id"] for p in parameters]
            assets[filename] = {"path": str(paths[0].relative_to(model_dir)), "parameters": ids}
            if not parameters:
                warnings.append(f"Empty expression: {filename}")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"Invalid expression {filename}: {exc}")
    for filename in sorted(manifest.managed_files):
        if filename not in assets:
            errors.append(f"Mapped expression missing or invalid: {filename}")
    try:
        model = json.loads((model_dir / manifest.model_file).read_text(encoding="utf-8"))
        if not model.get("FileReferences", {}).get("Expressions"):
            warnings.append("model3 manifest lacks Expressions; a standalone renderer needs explicit bindings")
        for group in model.get("Groups", []):
            if group.get("Name") in {"EyeBlink", "LipSync"} and not group.get("Ids"):
                warnings.append(f"Empty {group['Name']} group; standalone parameter binding required")
    except (OSError, ValueError) as exc:
        errors.append(f"Cannot read model manifest: {exc}")
    entries = {}
    for emotion, mapping in manifest.emotions.items():
        overlapping = []
        if mapping.expression in assets and mapping.fx in assets:
            overlapping = sorted(set(assets[mapping.expression]["parameters"]) & set(assets[mapping.fx]["parameters"]))
        entries[emotion] = {
            "files": list(mapping.files), "preview_required": mapping.preview_required,
            "note": mapping.note, "shared_parameters": overlapping,
        }
    return {"model_id": manifest.model_id, "emotion_count": len(entries), "emotions": entries,
            "assets": assets, "errors": errors, "warnings": warnings}
