"""导出聚合 FastAPI OpenAPI JSON（供前端 openapi-typescript 生成）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "services"
OUT = ROOT / "openapi.json"


def main() -> None:
    sys.path.insert(0, str(SERVICES))
    from main import app

    schema = app.openapi()
    OUT.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written {OUT}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
