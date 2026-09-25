import json
from pathlib import Path

from scraper.normalize import finalize
from scraper.sources.global_apis import HackerNewsHiring, Himalayas, RemoteOK, Remotive
from scraper.sources.taiwan import Job104, Yourator

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_104_list_and_detail():
    rows, last = Job104.parse_list_response(load("104_list.json"))
    assert last == 12 and len(rows) == 1
    job = Job104.parse_list(rows[0])
    assert job.source_id == "8abcd" and job.url == "https://www.104.com.tw/job/8abcd"
    assert job.salary == "月薪 50,000–80,000"
    Job104.apply_detail(job, load("104_detail.json"))
    job = finalize(job)
    assert job.years_min == 3 and job.city == "新北市"
    assert "Python" in job.skills and "Linux" in job.skills
    assert "【條件要求】" in job.description


def test_104_legacy_list():
    rows, last = Job104.parse_list_response({"data": {"list": [{"jobName": "x"}], "totalPage": 3}})
    assert last == 3 and rows == [{"jobName": "x"}]


def test_remotive():
    j = finalize(Remotive.parse(load("remotive.json")["jobs"][0]))
    assert j.remote and j.country == "全球遠端" and "Django" in j.skills and j.posted_at == "2026-09-20"


def test_remoteok():
    data = load("remoteok.json")
    j = finalize(RemoteOK.parse(data[1]))
    assert j.salary.startswith("USD 100,000") and "Kubernetes" in j.skills


def test_himalayas():
    j = finalize(Himalayas.parse(load("himalayas.json")["jobs"][0]))
    assert j.company == "Acme" and j.country in ("亞太", "全球遠端") and "Go" in j.skills


def test_hn():
    j = HackerNewsHiring.parse({"id": 1, "created_at_i": 1758000000,
        "text": "Acme Robotics | Senior Firmware Engineer | Taipei, Taiwan | ONSITE | $90k-$120k<p>We use C/C++ and FreeRTOS on ARM Cortex-M."})
    j = finalize(j)
    assert j.company == "Acme Robotics" and j.title == "Senior Firmware Engineer"
    assert j.city == "台北市" and {"C", "C++", "RTOS", "ARM"} <= set(j.skills)
    assert HackerNewsHiring.parse({"id": 2, "text": "just a comment"}) is None


def test_jsonld_board():
    html = (FIX / "yourator_job.html").read_text(encoding="utf-8")
    j = Yourator.parse_page("https://www.yourator.co/companies/foo/jobs/123", html)
    j = finalize(j)
    assert j.title == "後端工程師 Backend Engineer" and j.company == "Foo 科技"
    assert j.salary == "TWD 60,000–90,000 / 月" and j.years_min == 2
    assert "Node.js" in j.skills and j.city == "台北市"


def test_taiwanjobs_csv():
    from scraper.sources.taiwan import TaiwanJobs
    rows = TaiwanJobs.parse_csv((FIX / "taiwanjobs.csv").read_text(encoding="utf-8-sig"))
    jobs = [j for j in (TaiwanJobs.parse_row(r) for r in rows) if j]
    assert len(jobs) == 1  # the caregiver row is filtered out
    j = finalize(jobs[0])
    assert j.source_id == "14700001" and j.company == "範例精密股份有限公司"
    assert j.salary == "月薪 45,000–70,000" and j.years_min == 2 and j.city == "新竹市"
    assert {"C#", ".NET", "MS SQL"} <= set(j.skills) and j.posted_at == "2026-09-23"
