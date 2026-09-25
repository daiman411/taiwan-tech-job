"""Parse schema.org JobPosting JSON-LD, which most job sites embed for Google Jobs."""
from __future__ import annotations

import html
import json
import re

_LD_RE = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)


def find_job_posting(page_html: str) -> dict | None:
    for block in _LD_RE.findall(page_html or ""):
        try:
            data = json.loads(html.unescape(block.strip()))
        except json.JSONDecodeError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                t = node.get("@type")
                if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
                    return node
                stack.extend(v for k, v in node.items() if k == "@graph" or isinstance(v, (list, dict)))
            elif isinstance(node, list):
                stack.extend(node)
    return None


def _first(v):
    return v[0] if isinstance(v, list) and v else v


def location_text(posting: dict) -> str:
    loc = _first(posting.get("jobLocation")) or {}
    addr = loc.get("address") if isinstance(loc, dict) else None
    if isinstance(addr, str):
        return addr
    if isinstance(addr, dict):
        parts = [addr.get("addressRegion"), addr.get("addressLocality"), addr.get("addressCountry")]
        parts = [p.get("name") if isinstance(p, dict) else p for p in parts]
        return ", ".join(p for p in parts if p)
    if posting.get("jobLocationType") == "TELECOMMUTE":
        return "Remote"
    return ""


def salary_text(posting: dict) -> str:
    bs = posting.get("baseSalary")
    if not isinstance(bs, dict):
        return ""
    cur = bs.get("currency", "")
    val = bs.get("value") or {}
    if isinstance(val, dict):
        lo, hi, unit = val.get("minValue"), val.get("maxValue"), val.get("unitText", "")
        unit = {"MONTH": "月", "YEAR": "年", "HOUR": "時"}.get(str(unit).upper(), unit)
        if lo and hi:
            return f"{cur} {int(float(lo)):,}–{int(float(hi)):,} / {unit}".strip()
        if lo or val.get("value"):
            return f"{cur} {int(float(lo or val.get('value'))):,}+ / {unit}".strip()
    return ""


def experience_years(posting: dict) -> int | None:
    exp = posting.get("experienceRequirements")
    if isinstance(exp, dict):
        months = exp.get("monthsOfExperience")
        if months is not None:
            try:
                return int(float(months)) // 12
            except (TypeError, ValueError):
                return None
    return None


def org_name(posting: dict) -> str:
    org = posting.get("hiringOrganization")
    if isinstance(org, dict):
        return org.get("name", "")
    return org or ""
