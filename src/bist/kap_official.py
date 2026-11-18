"""Minimal client for the official KAP VYK REST API (MKK API Portal).

Credentials are read from <project>/.env and are never printed or logged.
"""
import time
from pathlib import Path

import requests

from .paths import ROOT


def load_env(path: Path = ROOT / ".env") -> dict[str, str]:
    env = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


class KapClient:
    def __init__(self, min_interval: float = 10.5):
        e = load_env()
        self.base = e.get("MKK_BASE_URL", "https://apigwdev.mkk.com.tr/api/vyk").rstrip("/")
        self.s = requests.Session()
        self.s.auth = (e["MKK_API_KEY"], e.get("MKK_API_SECRET", ""))  # HTTP Basic per OpenAPI spec
        self.s.headers.update({"Accept": "application/json"})
        self.min_interval = min_interval
        self._last = 0.0

    def get(self, path: str, **params):
        wait = self.min_interval - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        r = self.s.get(f"{self.base}{path}", params=params or None, timeout=60)
        self._last = time.time()
        return r
