"""Write a small sample dataset to docs/data so the page works locally before the first Action run.

    python scripts/make_sample_data.py && python -m http.server -d docs 8000
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scraper.main import write_site_data  # noqa: E402
from scraper.normalize import Job, finalize  # noqa: E402

T = date.today()
d = lambda n: (T - timedelta(days=n)).isoformat()  # noqa: E731
SAMPLES = [
    ("104", "a1", "後端工程師 (Python)", "範例科技", "台北市內湖區", "月薪 60,000–90,000", 0,
     "1. 使用 Python / FastAPI 開發 RESTful API\n2. 維護 PostgreSQL 與 Redis\n3. 以 Docker、Kubernetes 部署於 GCP\n\n【條件要求】\n工作經歷：3年以上\n學歷要求：大學\n擅長工具：Python、Linux、Git"),
    ("104", "a2", "資深韌體工程師", "範例半導體", "新竹市東區", "月薪 70,000–110,000", 1,
     "負責 ARM Cortex-M MCU 韌體開發，使用 C/C++ 與 FreeRTOS，撰寫驅動程式。\n\n【條件要求】\n工作經歷：5年以上"),
    ("104", "a3", "前端工程師 React", "新創 A", "台北市信義區", "月薪 50,000–70,000", 0,
     "使用 React、TypeScript、Next.js 開發產品介面，需 2 年以上經驗，熟悉 Git 與 CI/CD。"),
    ("yourator", "a4", "Machine Learning Engineer", "AI 新創", "台北市大安區", "TWD 80,000–120,000 / 月", 2,
     "開發電腦視覺模型，使用 PyTorch、OpenCV、CUDA。3 年以上深度學習經驗，熟悉 MLOps 尤佳。"),
    ("cake", "a5", "DevOps / SRE", "電商 B", "台中市西屯區", "面議", 3,
     "維運 AWS 與 Kubernetes 平台，Terraform、Prometheus/Grafana，經驗不拘，歡迎新鮮人。"),
    ("remotive", "a6", "Senior Backend Engineer (Go)", "Globex", "Remote (Worldwide)", "USD 120,000–160,000 / 年", 0,
     "5+ years of experience building distributed systems in Golang. gRPC, PostgreSQL, Kafka, Kubernetes on AWS."),
    ("remoteok", "a7", "Full Stack Developer", "Initech", "Remote (Europe)", "", 1,
     "Node.js, React, TypeScript, MongoDB. 3+ years experience. English required."),
    ("himalayas", "a8", "Data Engineer", "Umbrella", "Remote (Asia)", "USD 70,000–100,000 / 年", 4,
     "Build data pipelines with Airflow, Spark and BigQuery. SQL and Python. At least 2 years of experience."),
    ("hn", "a9", "iOS Engineer", "Hooli", "Tokyo, Japan", "", 5,
     "Swift, SwiftUI, 4+ years of iOS experience. Japanese a plus."),
    ("arbeitnow", "a10", "Security Engineer", "Wayne Corp", "Berlin, Germany", "", 2,
     "Penetration testing, OWASP, cloud security on Azure. 3 years experience."),
    ("104", "a11", "軟體測試工程師", "範例軟體", "新北市板橋區", "月薪 40,000–55,000", 0,
     "撰寫自動化測試 (Selenium, pytest)，熟悉 Linux 與 SQL，經驗不拘。"),
    ("104", "a12", "AI 應用工程師 (LLM)", "範例資訊", "高雄市前鎮區", "月薪 65,000–95,000", 1,
     "開發 LLM / RAG 應用，使用 Python、LangChain、向量資料庫，2年以上工作經驗。"),
]


def main():
    jobs = []
    for src, sid, title, company, loc, salary, age, desc in SAMPLES:
        j = finalize(Job(source=src, source_id=sid, title=title, company=company, url="https://example.com/" + sid,
                         description=desc, location=loc, salary=salary, posted_at=d(age))).to_dict()
        j["first_seen"] = j["posted_at"]
        j["last_seen"] = T.isoformat()
        jobs.append(j)
    labels = {"104": "104 人力銀行", "yourator": "Yourator", "cake": "Cake", "remotive": "Remotive", "remoteok": "RemoteOK",
              "himalayas": "Himalayas", "hn": "HN Who's Hiring", "arbeitnow": "Arbeitnow"}
    stats = {k: {"label": v, "count": sum(j["source"] == k for j in jobs), "ok": True, "error": ""} for k, v in labels.items()}
    write_site_data(jobs, stats, Path(__file__).resolve().parents[1] / "docs" / "data")
    print(f"wrote {len(jobs)} sample jobs")


if __name__ == "__main__":
    main()
