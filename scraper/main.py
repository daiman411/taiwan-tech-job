"""Daily pipeline: crawl every enabled source, normalize, merge with yesterday's data,
write the static JSON the website reads, and optionally sync to Supabase.

    python -m scraper.main --out site/data --previous-url https://<user>.github.io/<repo>/data/
    python -m scraper.main --out site/data --previous-url ... --reuse   # no crawl, just republish
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

from .normalize import finalize
from .skills import export_for_frontend
from .sources import ALL_SOURCES
from .supabase_store import SupabaseStore

log = logging.getLogger("scraper")

SHARDS = 64
SUMMARY_LEN = 220
INDEX_FIELDS = ["id", "source", "title", "company", "url", "location", "country", "city", "remote", "category",
                "seniority", "years_min", "education", "skills", "salary", "posted_at", "first_seen", "last_seen", "lang"]


def shard_of(job_id: str) -> str:
    return f"{int(job_id[:4], 16) % SHARDS:02d}"


# ---------- previous data ----------

def load_previous(base_url: str | None) -> list[dict]:
    """Download the currently published data so jobs keep `first_seen` and survive a source outage."""
    if not base_url:
        return []
    base = base_url.rstrip("/") + "/"
    try:
        r = requests.get(base + "jobs.json", timeout=30)
        if r.status_code != 200:
            log.info("no previous data at %s (%s)", base, r.status_code)
            return []
        index = r.json().get("jobs", [])
    except (requests.RequestException, ValueError) as e:
        log.warning("could not load previous data: %s", e)
        return []
    descs: dict[str, str] = {}

    def fetch_shard(n: int) -> dict:
        try:
            resp = requests.get(f"{base}desc/{n:02d}.json", timeout=30)
            return resp.json() if resp.status_code == 200 else {}
        except (requests.RequestException, ValueError):
            return {}

    with ThreadPoolExecutor(8) as ex:
        for part in ex.map(fetch_shard, range(SHARDS)):
            descs.update(part)
    for j in index:
        j["description"] = descs.get(j["id"], "")
    log.info("loaded %d previous jobs", len(index))
    return index


# ---------- crawl ----------

def crawl(config: dict, only: list[str] | None = None) -> tuple[list[dict], dict]:
    jobs: list[dict] = []
    stats: dict[str, dict] = {}
    for name, cfg in config["sources"].items():
        if only and name not in only:
            continue
        if not cfg.get("enabled", True) or name not in ALL_SOURCES:
            continue
        src = ALL_SOURCES[name](max_items=cfg.get("max_items", 300))
        got: list[dict] = []
        error = ""
        try:
            for job in src.fetch():
                if job and job.title:
                    got.append(finalize(job).to_dict())
        except Exception as e:  # one broken source must not break the run
            error = f"{type(e).__name__}: {e}"[:300]
            log.warning("source %s failed after %d jobs: %s", name, len(got), error)
        stats[name] = {"label": src.label, "region": src.region, "count": len(got), "ok": bool(got), "error": error}
        log.info("%-10s %4d jobs %s", name, len(got), error)
        jobs.extend(got)
    return jobs, stats


def _dedupe_key(j: dict) -> str:
    return re.sub(r"\W+", "", f"{j['title']}|{j['company']}".lower())


def merge(today_jobs: list[dict], previous: list[dict], stats: dict, retention_days: int, today: str) -> list[dict]:
    prev_by_id = {j["id"]: j for j in previous}
    out: dict[str, dict] = {}
    for j in today_jobs:
        old = prev_by_id.get(j["id"])
        j["first_seen"] = (old or {}).get("first_seen") or today
        j["last_seen"] = today
        if not j.get("posted_at"):
            j["posted_at"] = j["first_seen"]
        out[j["id"]] = j
    # Carry over jobs from sources that failed today, until they get too old.
    cutoff = (date.fromisoformat(today) - timedelta(days=retention_days)).isoformat()
    for j in previous:
        if j["id"] in out:
            continue
        st = stats.get(j["source"])
        if st is not None and st["ok"]:
            continue  # source worked and no longer lists it: the job is closed
        if (j.get("last_seen") or "") >= cutoff:
            out[j["id"]] = j
    # Cross-source de-duplication: keep the richer description.
    best: dict[str, dict] = {}
    for j in out.values():
        k = _dedupe_key(j)
        if k not in best or len(j.get("description", "")) > len(best[k].get("description", "")):
            best[k] = j
    return sorted(best.values(), key=lambda j: (j.get("posted_at") or "", j["id"]), reverse=True)


# ---------- output ----------

def write_site_data(jobs: list[dict], stats: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "desc").mkdir(exist_ok=True)
    index = []
    shards: dict[str, dict] = {f"{n:02d}": {} for n in range(SHARDS)}
    for j in jobs:
        row = {k: j.get(k) for k in INDEX_FIELDS}
        desc = j.get("description") or ""
        row["summary"] = re.sub(r"\s+", " ", desc)[:SUMMARY_LEN]
        index.append(row)
        shards[shard_of(j["id"])][j["id"]] = desc
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(out_dir / "jobs.json", "w", encoding="utf-8") as f:
        json.dump({"updated_at": now, "jobs": index}, f, ensure_ascii=False, separators=(",", ":"))
    for n, part in shards.items():
        with open(out_dir / "desc" / f"{n}.json", "w", encoding="utf-8") as f:
            json.dump(part, f, ensure_ascii=False, separators=(",", ":"))
    meta = {"updated_at": now, "total": len(jobs), "sources": stats, "shards": SHARDS}
    with open(out_dir / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    export_for_frontend(str(out_dir / "skills.json"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/data")
    ap.add_argument("--config", default="sources.json")
    ap.add_argument("--previous-url", default=os.getenv("PREVIOUS_DATA_URL"))
    ap.add_argument("--reuse", action="store_true", help="skip crawling, republish previous data")
    ap.add_argument("--only", nargs="*", help="crawl only these sources")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    today = date.today().isoformat()
    previous = load_previous(args.previous_url)

    if args.reuse and previous:
        prev_meta = {}
        try:
            prev_meta = requests.get(args.previous_url.rstrip("/") + "/meta.json", timeout=30).json().get("sources", {})
        except (requests.RequestException, ValueError):
            pass
        write_site_data(previous, prev_meta, Path(args.out))
        log.info("republished %d previous jobs", len(previous))
        return 0

    today_jobs, stats = crawl(config, args.only)
    jobs = merge(today_jobs, previous, stats, config.get("retention_days", 14), today)
    write_site_data(jobs, stats, Path(args.out))
    log.info("wrote %d jobs (%d crawled today)", len(jobs), len(today_jobs))

    store = SupabaseStore.from_env()
    if store:
        try:
            store.upsert_jobs([j for j in jobs if j.get("last_seen") == today])
            store.record_stats(stats)
            store.prune()
            log.info("supabase sync done")
        except requests.RequestException as e:
            log.error("supabase sync failed: %s", e)
    if not today_jobs and not previous:
        log.error("no jobs at all — every source failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
