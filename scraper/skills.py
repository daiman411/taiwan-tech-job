"""Skill dictionary shared by the scraper and the frontend.

Each entry maps a canonical skill name to a list of regex aliases (case-insensitive).
`export_for_frontend()` writes the same dictionary as JSON so the browser-side
résumé generator extracts skills exactly the way the scraper does.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

# group -> {canonical: [aliases]}
SKILL_GROUPS: dict[str, dict[str, list[str]]] = {
    "語言": {
        "Python": [r"python"],
        "Java": [r"java(?!\s*script)"],
        "JavaScript": [r"javascript", r"\bjs\b", r"es6"],
        "TypeScript": [r"typescript", r"\bts\b"],
        "C++": [r"c\+\+", r"\bcpp\b"],
        "C#": [r"c#", r"c sharp"],
        "Go": [r"golang", r"\bgo\s*(?:lang|語言|developer|engineer)"],
        "Rust": [r"\brust\b"],
        "Kotlin": [r"kotlin"],
        "Swift": [r"\bswift\b"],
        "Objective-C": [r"objective-?c"],
        "PHP": [r"\bphp\b"],
        "Ruby": [r"\bruby\b"],
        "Scala": [r"\bscala\b"],
        "R": [r"\br\s*(?:語言|language|programming)", r"\brstudio\b"],
        "MATLAB": [r"matlab"],
        "Dart": [r"\bdart\b"],
        "Shell": [r"\bbash\b", r"shell script", r"\bshell\b"],
        "SQL": [r"\bsql\b"],
        "Verilog": [r"verilog", r"systemverilog"],
        "VHDL": [r"\bvhdl\b"],
        "Solidity": [r"solidity"],
    },
    "前端": {
        "React": [r"react(?:\.?js)?(?!\s*native)"],
        "Vue": [r"\bvue(?:\.?js)?\b", r"nuxt"],
        "Angular": [r"angular"],
        "Next.js": [r"next\.?js"],
        "Svelte": [r"svelte"],
        "HTML/CSS": [r"\bhtml5?\b", r"\bcss3?\b", r"\bscss\b", r"\bsass\b"],
        "Tailwind": [r"tailwind"],
        "Redux": [r"\bredux\b"],
        "Webpack": [r"webpack", r"\bvite\b"],
    },
    "後端": {
        "Node.js": [r"node\.?js", r"\bnode\b", r"express\.?js", r"nestjs"],
        "Django": [r"django"],
        "Flask": [r"\bflask\b"],
        "FastAPI": [r"fastapi"],
        "Spring": [r"spring\s*boot", r"\bspring\b"],
        ".NET": [r"\.net\b", r"asp\.net", r"dotnet"],
        "Laravel": [r"laravel"],
        "Rails": [r"ruby on rails", r"\brails\b"],
        "GraphQL": [r"graphql"],
        "REST API": [r"restful", r"rest\s*api"],
        "gRPC": [r"\bgrpc\b"],
        "Microservices": [r"microservices?", r"微服務"],
    },
    "行動": {
        "iOS": [r"\bios\b"],
        "Android": [r"android"],
        "Flutter": [r"flutter"],
        "React Native": [r"react\s*native"],
    },
    "資料庫": {
        "PostgreSQL": [r"postgres(?:ql)?"],
        "MySQL": [r"mysql", r"mariadb"],
        "MS SQL": [r"ms\s*sql", r"sql\s*server"],
        "Oracle DB": [r"\boracle\b"],
        "MongoDB": [r"mongo(?:db)?"],
        "Redis": [r"\bredis\b"],
        "Elasticsearch": [r"elastic\s*search", r"opensearch", r"\belk\b"],
        "Cassandra": [r"cassandra"],
        "BigQuery": [r"bigquery"],
        "Snowflake": [r"snowflake"],
    },
    "雲端/DevOps": {
        "AWS": [r"\baws\b", r"amazon web services", r"\bec2\b", r"\bs3\b", r"lambda"],
        "GCP": [r"\bgcp\b", r"google cloud"],
        "Azure": [r"\bazure\b"],
        "Docker": [r"docker", r"container"],
        "Kubernetes": [r"kubernetes", r"\bk8s\b", r"\beks\b", r"\bgke\b"],
        "Terraform": [r"terraform"],
        "Ansible": [r"ansible"],
        "CI/CD": [r"ci\s*/\s*cd", r"jenkins", r"github actions", r"gitlab ci", r"circleci"],
        "Linux": [r"linux", r"ubuntu", r"centos"],
        "Git": [r"\bgit\b", r"github", r"gitlab"],
        "Prometheus/Grafana": [r"prometheus", r"grafana"],
        "Nginx": [r"nginx"],
    },
    "資料/AI": {
        "Machine Learning": [r"machine learning", r"\bml\b", r"機器學習"],
        "Deep Learning": [r"deep learning", r"深度學習", r"neural network", r"神經網路"],
        "LLM": [r"\bllms?\b", r"large language model", r"大型語言模型", r"\brag\b", r"langchain", r"prompt engineering"],
        "NLP": [r"\bnlp\b", r"natural language processing", r"自然語言"],
        "Computer Vision": [r"computer vision", r"電腦視覺", r"影像辨識", r"影像處理", r"image processing"],
        "PyTorch": [r"pytorch", r"\btorch\b"],
        "TensorFlow": [r"tensorflow", r"\bkeras\b"],
        "OpenCV": [r"opencv"],
        "scikit-learn": [r"scikit-?learn", r"sklearn"],
        "Pandas": [r"pandas", r"numpy"],
        "Spark": [r"\bspark\b", r"pyspark"],
        "Hadoop": [r"hadoop", r"\bhive\b"],
        "Kafka": [r"kafka"],
        "Airflow": [r"airflow"],
        "Data Analysis": [r"data analy", r"資料分析", r"數據分析"],
        "Tableau/Power BI": [r"tableau", r"power\s*bi", r"looker"],
        "MLOps": [r"mlops", r"mlflow", r"kubeflow"],
        "CUDA": [r"\bcuda\b", r"tensorrt"],
    },
    "嵌入式/硬體": {
        "Embedded": [r"embedded", r"嵌入式"],
        "Firmware": [r"firmware", r"韌體"],
        "RTOS": [r"\brtos\b", r"freertos", r"zephyr"],
        "ARM": [r"\barm\b", r"cortex-?m"],
        "MCU": [r"\bmcu\b", r"微控制器", r"stm32"],
        "FPGA": [r"\bfpga\b"],
        "ASIC": [r"\basic\b", r"ic design", r"ic 設計", r"晶片設計"],
        "Linux Kernel": [r"linux kernel", r"device driver", r"驅動程式", r"\bdriver\b"],
        "PCB": [r"\bpcb\b", r"layout", r"電路設計"],
        "Semiconductor": [r"semiconductor", r"半導體", r"製程"],
        "IoT": [r"\biot\b", r"物聯網"],
        "Qt": [r"\bqt\b"],
    },
    "測試/資安": {
        "Automation Testing": [r"selenium", r"cypress", r"playwright", r"自動化測試", r"test automation"],
        "Unit Testing": [r"unit test", r"單元測試", r"pytest", r"jest", r"junit"],
        "Security": [r"security", r"資安", r"資訊安全", r"penetration", r"滲透測試", r"\bsoc\b", r"owasp"],
    },
    "其他": {
        "Agile/Scrum": [r"agile", r"scrum", r"敏捷"],
        "System Design": [r"system design", r"系統設計", r"distributed system", r"分散式"],
        "Blockchain": [r"blockchain", r"區塊鏈", r"web3", r"smart contract"],
        "Unity": [r"\bunity\b"],
        "Unreal": [r"unreal"],
        "UI/UX": [r"\bui\s*/\s*ux\b", r"\bux\b", r"figma"],
        "English": [r"english", r"英文", r"英語", r"toeic", r"多益"],
        "Japanese": [r"japanese", r"日文", r"日語", r"jlpt"],
    },
}

# "C" is too ambiguous as a free-standing letter; only match when clearly a language.
SKILL_GROUPS["語言"]["C"] = [r"(?<![\w#+.])c\s*(?:/|、|,|and)\s*c\+\+", r"\bc\s*語言", r"\bc language", r"\bansi c\b", r"\bembedded c\b"]


@lru_cache(maxsize=1)
def _compiled() -> list[tuple[str, re.Pattern]]:
    out = []
    for group in SKILL_GROUPS.values():
        for name, aliases in group.items():
            out.append((name, re.compile("|".join(f"(?:{a})" for a in aliases), re.IGNORECASE | re.ASCII)))
    return out


def extract_skills(text: str) -> list[str]:
    """Return canonical skill names found in text, in dictionary order."""
    if not text:
        return []
    return [name for name, pat in _compiled() if pat.search(text)]


def skill_group(name: str) -> str | None:
    for group, skills in SKILL_GROUPS.items():
        if name in skills:
            return group
    return None


def export_for_frontend(path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(SKILL_GROUPS, f, ensure_ascii=False, indent=1)
