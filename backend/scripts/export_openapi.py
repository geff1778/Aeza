#!/usr/bin/env python3
"""Export the live OpenAPI schema to openapi.json / openapi.yml.

Run from the backend directory so the committed spec always matches the code:

    python scripts/export_openapi.py

The file is regenerated from the real FastAPI app, so it cannot drift from the
implemented routes.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.main import create_app  # noqa: E402

OUT_DIR = pathlib.Path(__file__).resolve().parent.parent.parent


def main() -> int:
    schema = create_app().openapi()
    if not schema.get("paths"):
        print("refusing to write an empty spec", file=sys.stderr)
        return 1

    json_path = OUT_DIR / "openapi.json"
    json_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {json_path} ({len(schema['paths'])} paths)")

    try:
        import yaml
    except ImportError:
        print("PyYAML not installed — skipping openapi.yml")
        return 0

    yml_path = OUT_DIR / "openapi.yml"
    yml_path.write_text(
        yaml.safe_dump(schema, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    print(f"wrote {yml_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
