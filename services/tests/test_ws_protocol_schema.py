"""WS 协议契约：protocol/interview_ws.schema.json 与前后端类型对齐。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from interview_service.constants import WSClientEvent, WSServerEvent

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "protocol" / "interview_ws.schema.json"
FRONTEND_WS_TS = ROOT / "apps" / "web" / "src" / "types" / "domains" / "interview_ws.ts"


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _extract_ts_event_types(ts_path: Path) -> tuple[set[str], set[str]]:
    text = ts_path.read_text(encoding="utf-8")
    client_idx = text.find("export type ClientEvent")
    server_part = text[:client_idx] if client_idx > 0 else text
    client_part = text[client_idx:] if client_idx > 0 else ""
    server_types = set(re.findall(r"type:\s*\"([a-z_]+)\"", server_part))
    client_types = set(re.findall(r"type:\s*\"([a-z_]+)\"", client_part))
    return server_types, client_types


def test_ws_schema_matches_backend_enums() -> None:
    schema = _load_schema()
    server_schema = set(schema["serverEventTypes"])
    client_schema = set(schema["clientEventTypes"])

    enum_server = {e.value for e in WSServerEvent}
    enum_client = {e.value for e in WSClientEvent}

    assert enum_server <= server_schema
    assert enum_client <= client_schema


def test_ws_schema_covers_frontend_types() -> None:
    schema = _load_schema()
    ts_server, ts_client = _extract_ts_event_types(FRONTEND_WS_TS)
    ts_server.add("error")

    server_schema = set(schema["serverEventTypes"])
    client_schema = set(schema["clientEventTypes"])

    assert ts_server <= server_schema
    assert client_schema == ts_client
