"""International sources that publish free, public JSON APIs intended for reuse.

- Remotive  https://remotive.com/api/remote-jobs  (asks for <= 4 calls/day and a link back)
- RemoteOK  https://remoteok.com/api              (asks for a link back to the job URL)
- Arbeitnow https://www.arbeitnow.com/api/job-board-api
- Himalayas https://himalayas.app/jobs/api
- Hacker News "Who is hiring?" via the Algolia HN API

LinkedIn/Indeed/Glassdoor forbid scraping in their terms and have no free public
job API, so they are intentionally not crawled here. The frontend links out to
their search pages instead.
"""
from __future__ import annotations

import html
import re
from typing import Iterable

from ..normalize import Job, html_to_text, is_tech_job, to_iso_date
from .base import Source


class Remotive(Source):
    name, label = "remotive", "Remotive"
    CATEGORIES = ["software-dev", "data", "devops", "qa", "product"]

    def fetch(self) -> Iterable[Job]:
        n = 0
        for cat in self.CATEGORIES:
            data = self.get("https://remotive.com/api/remote-jobs", params={"category": cat}).json()
            for raw in data.get("jobs", []):
                yield self.parse(raw)
                n += 1
                if n >= self.max_items:
                    return

    @staticmethod
    def parse(raw: dict) -> Job:
        return Job(
            source="remotive",
            source_id=str(raw.get("id")),
            title=raw.get("title", ""),
            company=raw.get("company_name", ""),
            url=raw.get("url", ""),
            description=raw.get("description", ""),
            location=f"Remote ({raw.get('candidate_required_location') or 'Worldwide'})",
            salary=raw.get("salary") or "",
            posted_at=to_iso_date(raw.get("publication_date")),
            tags=list(raw.get("tags") or []) + [raw.get("category") or ""],
            remote=True,
        )


class RemoteOK(Source):
    name, label = "remoteok", "RemoteOK"

    def fetch(self) -> Iterable[Job]:
        data = self.get("https://remoteok.com/api").json()
        n = 0
        for raw in data:
            if not isinstance(raw, dict) or "id" not in raw or "position" not in raw:
                continue  # first element is the legal notice
            job = self.parse(raw)
            if is_tech_job(job.title, job.tags):
                yield job
                n += 1
                if n >= self.max_items:
                    return

    @staticmethod
    def parse(raw: dict) -> Job:
        smin, smax = raw.get("salary_min") or 0, raw.get("salary_max") or 0
        salary = f"USD {smin:,}–{smax:,} / 年" if smin and smax else ""
        return Job(
            source="remoteok",
            source_id=str(raw.get("id")),
            title=raw.get("position", ""),
            company=raw.get("company", ""),
            url=raw.get("url") or raw.get("apply_url", ""),
            description=raw.get("description", ""),
            location=f"Remote ({raw.get('location') or 'Worldwide'})",
            salary=salary,
            posted_at=to_iso_date(raw.get("date") or raw.get("epoch")),
            tags=list(raw.get("tags") or []),
            remote=True,
        )


class Arbeitnow(Source):
    name, label = "arbeitnow", "Arbeitnow"
    PAGES = 5

    def fetch(self) -> Iterable[Job]:
        n = 0
        url = "https://www.arbeitnow.com/api/job-board-api"
        for _ in range(self.PAGES):
            data = self.get(url).json()
            for raw in data.get("data", []):
                job = self.parse(raw)
                if is_tech_job(job.title, job.tags, job.description):
                    yield job
                    n += 1
                    if n >= self.max_items:
                        return
            url = (data.get("links") or {}).get("next")
            if not url:
                return

    @staticmethod
    def parse(raw: dict) -> Job:
        return Job(
            source="arbeitnow",
            source_id=raw.get("slug", ""),
            title=raw.get("title", ""),
            company=raw.get("company_name", ""),
            url=raw.get("url", ""),
            description=raw.get("description", ""),
            location=raw.get("location", "") + (" (Remote)" if raw.get("remote") else ""),
            posted_at=to_iso_date(raw.get("created_at")),
            tags=list(raw.get("tags") or []) + list(raw.get("job_types") or []),
            remote=bool(raw.get("remote")),
        )


class Himalayas(Source):
    name, label = "himalayas", "Himalayas"
    PAGE = 20

    def fetch(self) -> Iterable[Job]:
        n, offset = 0, 0
        while n < self.max_items and offset < 2000:
            data = self.get("https://himalayas.app/jobs/api", params={"limit": self.PAGE, "offset": offset}).json()
            jobs = data.get("jobs", [])
            if not jobs:
                return
            for raw in jobs:
                job = self.parse(raw)
                if is_tech_job(job.title, job.tags):
                    yield job
                    n += 1
            offset += len(jobs)

    @staticmethod
    def parse(raw: dict) -> Job:
        smin, smax, cur = raw.get("minSalary"), raw.get("maxSalary"), raw.get("currency") or "USD"
        salary = f"{cur} {smin:,}–{smax:,} / 年" if smin and smax else ""
        locs = raw.get("locationRestrictions") or []
        seniority = raw.get("seniority") or []
        return Job(
            source="himalayas",
            source_id=str(raw.get("guid") or raw.get("applicationLink", "")),
            title=raw.get("title", ""),
            company=raw.get("companyName", ""),
            url=raw.get("applicationLink") or raw.get("guid", ""),
            description=raw.get("description") or raw.get("excerpt", ""),
            location="Remote (" + (", ".join(locs) if locs else "Worldwide") + ")",
            salary=salary,
            posted_at=to_iso_date(raw.get("pubDate")),
            tags=list(raw.get("categories") or []) + list(seniority if isinstance(seniority, list) else [seniority]),
            remote=True,
        )


class HackerNewsHiring(Source):
    """Top-level comments of the latest monthly 'Ask HN: Who is hiring?' thread."""

    name, label = "hn", "HN Who's Hiring"
    delay = 0.3

    def fetch(self) -> Iterable[Job]:
        hits = self.get(
            "https://hn.algolia.com/api/v1/search_by_date",
            params={"tags": "story,author_whoishiring", "hitsPerPage": 5},
        ).json().get("hits", [])
        story = next((h for h in hits if "who is hiring" in (h.get("title") or "").lower()), None)
        if not story:
            return
        item = self.get(f"https://hn.algolia.com/api/v1/items/{story['objectID']}").json()
        n = 0
        for child in item.get("children", []):
            job = self.parse(child)
            if job:
                yield job
                n += 1
                if n >= self.max_items:
                    return

    @staticmethod
    def parse(raw: dict) -> Job | None:
        text_html = raw.get("text") or ""
        if not text_html:
            return None
        first = html.unescape(re.split(r"<p>|\n", text_html, maxsplit=1)[0])
        first = re.sub(r"<[^>]+>", "", first)
        parts = [p.strip() for p in first.split("|") if p.strip()]
        if len(parts) < 2:
            return None
        company = parts[0][:80]
        title = next((p for p in parts[1:] if is_tech_job(p)), parts[1])[:120]
        location = next(
            (p for p in parts[1:] if re.search(r"remote|onsite|on-site|hybrid|,|\b[A-Z]{2}\b", p) and p != title), ""
        )
        salary = next((p for p in parts if re.search(r"[$€£]\s?\d|\d+k", p, re.I)), "")
        return Job(
            source="hn",
            source_id=str(raw.get("id")),
            title=title,
            company=company,
            url=f"https://news.ycombinator.com/item?id={raw.get('id')}",
            description=html_to_text(text_html),
            location=location,
            salary=salary[:60],
            posted_at=to_iso_date(raw.get("created_at_i") or raw.get("created_at")),
            tags=[],
        )
