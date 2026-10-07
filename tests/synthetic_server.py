"""tests/synthetic_server.py — Lightweight HTTP server serving synthetic test fixtures."""

from __future__ import annotations

import functools
import http.server
import os
import threading
from typing import Optional

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


class SyntheticServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 18099):
        self.host = host
        self.port = port
        self.server: Optional[http.server.ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> str:
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=FIXTURES_DIR)
        self.server = http.server.ThreadingHTTPServer((self.host, self.port), handler)
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()
        return f"http://{self.host}:{self.port}"

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None


if __name__ == "__main__":
    srv = SyntheticServer()
    url = srv.start()
    print(f"Synthetic test server running at {url}/synthetic.html (Ctrl+C to stop)")
    try:
        while True:
            threading.Event().wait(1)
    except KeyboardInterrupt:
        srv.stop()
