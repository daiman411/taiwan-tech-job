import json

from scraper.main import merge, shard_of, write_site_data


def job(id_, source="104", title="t", company="c", desc="d", last_seen="2026-09-24", first_seen="2026-09-01"):
    return {"id": id_, "source": source, "title": title, "company": company, "description": desc, "url": "u",
            "posted_at": "", "first_seen": first_seen, "last_seen": last_seen, "skills": []}


def test_merge_keeps_first_seen_and_carries_failed_sources():
    prev = [job("aaaa000000000001", first_seen="2026-09-01"),
            job("aaaa000000000002", source="cake", title="x"),
            job("aaaa000000000003", title="closed"),
            job("aaaa000000000004", source="cake", title="old", last_seen="2026-08-01")]
    today = [job("aaaa000000000001")]
    stats = {"104": {"ok": True}, "cake": {"ok": False}}
    out = {j["id"]: j for j in merge(today, prev, stats, 14, "2026-09-25")}
    assert out["aaaa000000000001"]["first_seen"] == "2026-09-01"
    assert out["aaaa000000000001"]["last_seen"] == "2026-09-25"
    assert "aaaa000000000002" in out  # failed source -> carried over
    assert "aaaa000000000003" not in out  # source ok but job gone -> closed
    assert "aaaa000000000004" not in out  # too old


def test_merge_dedupes_across_sources():
    a = job("aaaa000000000001", source="104", title="Backend Engineer", company="Foo", desc="short")
    b = job("bbbb000000000001", source="cake", title="Backend  engineer", company="foo", desc="much longer text")
    out = merge([a, b], [], {}, 14, "2026-09-25")
    assert len(out) == 1 and out[0]["source"] == "cake"


def test_write_site_data(tmp_path):
    jobs = [dict(job("abcd000000000001", desc="hello world"), skills=["Python"])]
    write_site_data(jobs, {"104": {"ok": True, "count": 1}}, tmp_path)
    idx = json.loads((tmp_path / "jobs.json").read_text())
    assert idx["jobs"][0]["summary"] == "hello world" and "description" not in idx["jobs"][0]
    shard = json.loads((tmp_path / "desc" / f"{shard_of('abcd000000000001')}.json").read_text())
    assert shard["abcd000000000001"] == "hello world"
    assert (tmp_path / "skills.json").exists() and (tmp_path / "meta.json").exists()
