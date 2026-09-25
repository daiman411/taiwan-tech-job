"""Optional Supabase sync through its REST API (PostgREST) — no SDK needed.

Enabled only when SUPABASE_URL and SUPABASE_SERVICE_KEY are set (GitHub Actions secrets).
The public site never queries Supabase directly: it reads the static JSON on GitHub
Pages, so visitor traffic never counts against the free-tier quota.
"""
from __future__ import annotations

import logging
import os
from datetime import date, timedelta

import requests

log = logging.getLogger(__name__)

COLUMNS = ["id", "source", "source_id", "title", "company", "url", "description", "location", "country", "city",
           "remote", "category", "seniority", "years_min", "education", "skills", "tags", "salary", "posted_at",
           "lang", "last_seen"]


class SupabaseStore:
    def __init__(self, url: str, key: str):
        self.base = url.rstrip("/") + "/rest/v1"
        self.s = requests.Session()
        self.s.headers.update({"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"})

    @classmethod
    def from_env(cls) -> "SupabaseStore | None":
        url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY")
        return cls(url, key) if url and key else None

    def upsert_jobs(self, jobs: list[dict], batch: int = 300) -> int:
        rows = [{k: (j.get(k) or None) if k == "posted_at" else j.get(k) for k in COLUMNS} for j in jobs]
        for i in range(0, len(rows), batch):
            r = self.s.post(
                f"{self.base}/jobs",
                params={"on_conflict": "id"},
                headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
                json=rows[i : i + batch],
                timeout=60,
            )
            r.raise_for_status()
        return len(rows)

    def prune(self, keep_days: int = 60) -> None:
        """Delete postings not seen for `keep_days` so the free 500 MB never fills up."""
        cutoff = (date.today() - timedelta(days=keep_days)).isoformat()
        r = self.s.delete(f"{self.base}/jobs", params={"last_seen": f"lt.{cutoff}"}, timeout=60)
        r.raise_for_status()

    def record_stats(self, stats: dict[str, dict]) -> None:
        today = date.today().isoformat()
        rows = [{"day": today, "source": k, "count": v.get("count", 0), "ok": v.get("ok", False)} for k, v in stats.items()]
        r = self.s.post(
            f"{self.base}/daily_stats",
            params={"on_conflict": "day,source"},
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
            json=rows,
            timeout=60,
        )
        r.raise_for_status()
