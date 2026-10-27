"""Tests for ``python -m remon_home_integration``."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from remon_home_integration.__main__ import main

from .conftest import load_fixture


class _Device(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        raw = load_fixture("saltbuddy.json")
        self.send_response(200 if self.path == "/api/status" else 404)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_: object) -> None:
        pass


@pytest.fixture
def device_port() -> Iterator[int]:
    # main() runs its own event loop, so the fake device lives in a plain thread.
    server = HTTPServer(("127.0.0.1", 0), _Device)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


def test_prints_status(device_port: int, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["127.0.0.1", "--port", str(device_port)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["id"] == "SaltBuddy-a1b2c3d4e5f6"
    assert out["salt_level"] == 64
    assert out["display_name"] == "SaltBuddy"
    assert out["mac"] == "a1:b2:c3:d4:e5:f6"


@pytest.mark.parametrize("host", ["bad host", "does-not-exist.invalid"])
def test_error_exit_code(host: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([host, "--timeout", "5"]) == 1
    assert capsys.readouterr().err.startswith("error: ")
