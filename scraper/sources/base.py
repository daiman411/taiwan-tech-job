from __future__ import annotations

import logging
import time
from typing import Iterable

import requests

from ..normalize import Job

log = logging.getLogger(__name__)

USER_AGENT = "TaiwanTechJobBot/1.0 (+https://github.com/daiman411/taiwan-tech-job; daily job digest)"


class Source:
    """A job source. Subclasses implement `fetch()` and yield `Job`s.

    `parse_*` helpers are kept pure (dict in, Job out) so they can be unit-tested
    against fixtures without network access.
    """

    name: str = "base"
    label: str = "Base"
    region: str = "global"  # "tw" or "global"
    delay: float = 1.0  # seconds between requests, be polite

    def __init__(self, max_items: int = 500, session: requests.Session | None = None):
        self.max_items = max_items
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self._last = 0.0

    def get(self, url: str, **kw) -> requests.Response:
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        kw.setdefault("timeout", 30)
        for attempt in range(3):
            try:
                resp = self.session.get(url, **kw)
                self._last = time.monotonic()
                if resp.status_code in (429, 502, 503, 504) and attempt < 2:
                    time.sleep(5 * (attempt + 1))
                    continue
                resp.raise_for_status()
                return resp
            except requests.RequestException:
                if attempt == 2:
                    raise
                time.sleep(3 * (attempt + 1))
        raise RuntimeError("unreachable")

    def fetch(self) -> Iterable[Job]:  # pragma: no cover - network
        raise NotImplementedError
