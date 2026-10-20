"""Run with: python tools/audit_avatar.py [--model-dir model] [--json]."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from avatar import audit_assets, load_manifest
from avatar.manifest import DEFAULT_MANIFEST


def main():
    parser = argparse.ArgumentParser(description="Read-only avatar asset and mapping audit")
    parser.add_argument("--model-dir", type=Path, default=Path(__file__).resolve().parents[1] / "model" / "Model_1")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = audit_assets(load_manifest(args.manifest), args.model_dir)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{report['emotion_count']} emotions; {len(report['assets'])} expression assets")
        for emotion, mapping in report["emotions"].items():
            print(f"{emotion}: {', '.join(mapping['files']) or '(reset)'}")
        for level in ("errors", "warnings"):
            for message in report[level]:
                print(f"{level.upper()}: {message}")
        print("Visual preview is still required for candidate mappings.")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
