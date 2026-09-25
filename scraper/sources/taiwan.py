"""Taiwan job boards.

These sites do not offer an official public API. The crawler therefore:
- only reads public listing pages / the JSON the site's own search page uses,
- runs once a day with a delay between requests and a small page budget,
- links every job back to the original posting.
Disable any source in `sources.json` if its terms change or the owner objects.
"""
from __future__ import annotations

import logging
import re
from typing import Iterable
from urllib.parse import quote

from ..normalize import Job, html_to_text, is_tech_job, parse_years, to_iso_date
from . import jsonld
from .base import Source

log = logging.getLogger(__name__)


class Job104(Source):
    name, label, region = "104", "104 人力銀行", "tw"
    delay = 1.5
    # 2007000000 = 資訊軟體系統類; 2008000000 = 研發相關類 (IC/硬體/韌體 等)
    JOBCATS = ["2007000000", "2008000000"]
    MAX_PAGES = 8
    MAX_DETAILS = 400
    REFERER = "https://www.104.com.tw/jobs/search/"

    def fetch(self) -> Iterable[Job]:
        seen: set[str] = set()
        details = 0
        for cat in self.JOBCATS:
            for page in range(1, self.MAX_PAGES + 1):
                try:
                    rows, last_page = self._list_page(cat, page)
                except Exception as e:  # keep other categories going
                    log.warning("104 list %s p%s failed: %s", cat, page, e)
                    break
                for raw in rows:
                    job = self.parse_list(raw)
                    if not job or job.source_id in seen:
                        continue
                    seen.add(job.source_id)
                    if details < self.MAX_DETAILS:
                        try:
                            self.enrich(job)
                            details += 1
                        except Exception as e:
                            log.info("104 detail %s failed: %s", job.source_id, e)
                    yield job
                    if len(seen) >= self.max_items:
                        return
                if page >= last_page:
                    break

    def _list_page(self, cat: str, page: int) -> tuple[list[dict], int]:
        params = {"jobcat": cat, "order": 15, "page": page, "pagesize": 30, "mode": "s", "jobsource": "index_s"}
        resp = self.get("https://www.104.com.tw/jobs/search/api/jobs", params=params, headers={"Referer": self.REFERER})
        return self.parse_list_response(resp.json())

    @staticmethod
    def parse_list_response(data: dict) -> tuple[list[dict], int]:
        body = data.get("data")
        if isinstance(body, dict) and "list" in body:  # legacy /jobs/search/list
            return body.get("list") or [], int(body.get("totalPage") or 1)
        rows = body if isinstance(body, list) else []
        pag = (data.get("metadata") or {}).get("pagination") or {}
        return rows, int(pag.get("lastPage") or 1)

    @staticmethod
    def job_code(raw: dict) -> str:
        link = (raw.get("link") or {}).get("job", "") if isinstance(raw.get("link"), dict) else ""
        m = re.search(r"/job/(\w+)", link)
        return m.group(1) if m else str(raw.get("jobNo") or "")

    @classmethod
    def parse_list(cls, raw: dict) -> Job | None:
        code = cls.job_code(raw)
        if not code:
            return None
        lo, hi = raw.get("salaryLow") or 0, raw.get("salaryHigh") or 0
        if lo and hi and hi < 9999999:
            salary = f"月薪 {int(lo):,}–{int(hi):,}"
        elif lo:
            salary = f"月薪 {int(lo):,} 以上"
        else:
            salary = raw.get("salaryDesc") or "面議"
        period = raw.get("periodDesc") or ""
        tags = [t if isinstance(t, str) else (t.get("desc") or "") for t in (raw.get("tags") or [])]
        if isinstance(raw.get("tags"), dict):
            tags = [v.get("desc", "") for v in raw["tags"].values() if isinstance(v, dict)]
        return Job(
            source="104",
            source_id=code,
            title=raw.get("jobName", ""),
            company=raw.get("custName", ""),
            url=f"https://www.104.com.tw/job/{code}",
            description=raw.get("description") or raw.get("descWithoutHighlight") or "",
            location=raw.get("jobAddrNoDesc") or raw.get("jobAddress") or "",
            salary=salary,
            posted_at=to_iso_date(raw.get("appearDate")),
            tags=[t for t in tags if t],
            years_min=0 if "不拘" in period else parse_years(period),
            education=raw.get("optionEdu") or "",
        )

    def enrich(self, job: Job) -> None:
        resp = self.get(
            f"https://www.104.com.tw/job/ajax/content/{job.source_id}",
            headers={"Referer": f"https://www.104.com.tw/job/{job.source_id}"},
        )
        self.apply_detail(job, resp.json())

    @staticmethod
    def apply_detail(job: Job, data: dict) -> None:
        d = data.get("data") or {}
        detail, cond = d.get("jobDetail") or {}, d.get("condition") or {}
        parts = [detail.get("jobDescription") or job.description]
        specialty = [s.get("description", "") for s in cond.get("specialty") or [] if isinstance(s, dict)]
        skills = [s.get("description", "") for s in cond.get("skill") or [] if isinstance(s, dict)]
        req = []
        if cond.get("workExp"):
            req.append(f"工作經歷：{cond['workExp']}")
        if cond.get("edu"):
            req.append(f"學歷要求：{cond['edu']}")
        if specialty:
            req.append("擅長工具：" + "、".join(specialty))
        if skills:
            req.append("工作技能：" + "、".join(skills))
        if cond.get("other"):
            req.append("其他條件：\n" + cond["other"])
        if req:
            parts.append("【條件要求】\n" + "\n".join(req))
        job.description = "\n\n".join(p for p in parts if p)
        job.tags = list(dict.fromkeys(job.tags + specialty + skills))
        exp = cond.get("workExp") or ""
        if exp:
            job.years_min = 0 if "不拘" in exp else parse_years(exp)
        if cond.get("edu"):
            job.education = cond["edu"]
        if detail.get("addressRegion"):
            job.location = detail["addressRegion"] + (detail.get("addressDetail") or "")
        remote = detail.get("remoteWork")
        if isinstance(remote, dict) and remote.get("type"):
            job.remote = True
            job.tags.append("遠端工作")


class _JsonLdBoard(Source):
    """Boards where a listing page links to job pages carrying JobPosting JSON-LD."""

    region = "tw"
    delay = 2.0
    LIST_URLS: list[str] = []
    LINK_RE: re.Pattern
    BASE = ""

    def fetch(self) -> Iterable[Job]:
        links: list[str] = []
        for url in self.LIST_URLS:
            try:
                page = self.get(url).text
            except Exception as e:
                log.warning("%s list %s failed: %s", self.name, url, e)
                continue
            for path in self.LINK_RE.findall(page):
                full = path if path.startswith("http") else self.BASE + path
                if full not in links:
                    links.append(full)
            if len(links) >= self.max_items:
                break
        for url in links[: self.max_items]:
            try:
                job = self.parse_page(url, self.get(url).text)
            except Exception as e:
                log.info("%s page %s failed: %s", self.name, url, e)
                continue
            if job and is_tech_job(job.title, job.tags, job.description):
                yield job

    @classmethod
    def parse_page(cls, url: str, page_html: str) -> Job | None:
        posting = jsonld.find_job_posting(page_html)
        if not posting:
            return None
        skills = posting.get("skills") or []
        if isinstance(skills, str):
            skills = [s.strip() for s in re.split(r"[,、，]", skills) if s.strip()]
        desc = html_to_text(posting.get("description", ""))
        qual = posting.get("qualifications") or posting.get("experienceRequirements")
        if isinstance(qual, str) and qual.strip():
            desc += "\n\n【條件要求】\n" + html_to_text(qual)
        return Job(
            source=cls.name,
            source_id=url.split("?")[0].rstrip("/").split("/", 3)[-1],
            title=posting.get("title", ""),
            company=jsonld.org_name(posting),
            url=url,
            description=desc,
            location=jsonld.location_text(posting),
            salary=jsonld.salary_text(posting),
            posted_at=to_iso_date(posting.get("datePosted")),
            tags=[str(s) for s in skills],
            remote=True if posting.get("jobLocationType") == "TELECOMMUTE" else None,
            years_min=jsonld.experience_years(posting),
        )


class Yourator(_JsonLdBoard):
    name, label = "yourator", "Yourator"
    BASE = "https://www.yourator.co"
    LIST_URLS = [
        f"https://www.yourator.co/jobs?category[]={quote(c)}&sort=recent_updated"
        for c in ["後端工程", "前端工程", "全端工程", "軟體工程", "資料科學", "資料分析", "機器學習", "DevOps / SRE",
                  "iOS 開發", "Android 開發", "韌體工程", "硬體工程", "資訊安全", "測試工程"]
    ]
    LINK_RE = re.compile(r'href="(/companies/[^/"]+/jobs/\d+)"')


class Cake(_JsonLdBoard):
    name, label = "cake", "Cake"
    BASE = "https://www.cake.me"
    LIST_URLS = [
        f"https://www.cake.me/jobs/{quote(k)}?location_list%5B0%5D=Taiwan&order=latest"
        for k in ["software engineer", "backend", "frontend", "data", "machine learning", "devops", "firmware", "工程師"]
    ]
    LINK_RE = re.compile(r'href="(/companies/[^/"]+/jobs/[^"?#/]+)"')


class TaiwanJobs(Source):
    """台灣就業通職缺清單 — Ministry of Labor open data (政府資料開放授權條款), data.gov.tw dataset 44062.

    The CSV holds the most recently updated ~1,000 postings across all industries; we keep the tech ones.
    """

    name, label, region = "taiwanjobs", "台灣就業通", "tw"
    URL = "https://apiservice.mol.gov.tw/OdService/download/A17000000J-030144-MKw"
    TECH_CATEGORY_RE = re.compile(r"資訊|軟體|系統|研發|電子|電機|半導體|工程")

    def fetch(self) -> Iterable[Job]:
        resp = self.get(self.URL, timeout=120)
        n = 0
        for row in self.parse_csv(resp.content.decode("utf-8-sig", errors="replace")):
            job = self.parse_row(row)
            if job:
                yield job
                n += 1
                if n >= self.max_items:
                    return

    @staticmethod
    def parse_csv(text: str) -> list[dict]:
        import csv
        import io

        reader = csv.reader(io.StringIO(text))
        header = next(reader, [])
        # headers look like "OCCU_DESC（職務名稱）"; keep the English key
        keys = [re.split(r"[（(]", h, maxsplit=1)[0].strip() for h in header]
        return [dict(zip(keys, r)) for r in reader if r]

    @classmethod
    def parse_row(cls, r: dict) -> Job | None:
        title = r.get("OCCU_DESC", "").strip()
        cats = f"{r.get('CJOB_NAME1', '')} {r.get('CJOB_NAME2', '')}"
        detail = r.get("JOB_DETAIL", "")
        if not title or not (cls.TECH_CATEGORY_RE.search(cats) and is_tech_job(title, [cats], detail)):
            return None
        url = r.get("URL_QUERY", "")
        m = re.search(r"HIRE_ID=(\d+)", url)
        lo, hi = (r.get("NT_L") or "").strip(), (r.get("NT_U") or "").strip()
        unit = r.get("SALARYCD", "")
        if lo.isdigit() and hi.isdigit():
            salary = f"{unit} {int(lo):,}–{int(hi):,}"
        elif lo.isdigit():
            salary = f"{unit} {int(lo):,} 以上"
        else:
            salary = ""
        exp = r.get("EXPERIENCE", "")
        req = [f"工作經驗：{exp}" if exp else "", f"學歷要求：{r['EDGRDESC']}" if r.get("EDGRDESC") else "",
               f"工作時間：{r['WKTIME']}" if r.get("WKTIME") else "", f"應徵截止：{to_iso_date(r.get('STOP_DATE'))}" if r.get("STOP_DATE") else ""]
        desc = detail.strip() + ("\n\n【條件要求】\n" + "\n".join(x for x in req if x) if any(req) else "")
        return Job(
            source="taiwanjobs",
            source_id=m.group(1) if m else url,
            title=title,
            company=r.get("COMPNAME", ""),
            url=url,
            description=desc,
            location=r.get("CITYNAME", ""),
            salary=salary.strip(),
            posted_at=to_iso_date(r.get("TRANDATE")),
            tags=[t for t in (r.get("CJOB_NAME2"), r.get("WK_TYPE")) if t],
            years_min=0 if exp in ("無", "不拘", "") else parse_years(exp),
            education=r.get("EDGRDESC", ""),
        )
