"""Turn raw source records into one normalized job schema."""
from __future__ import annotations

import hashlib
import html
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from .skills import extract_skills


@dataclass
class Job:
    source: str
    source_id: str
    title: str
    company: str
    url: str
    description: str = ""
    location: str = ""
    salary: str = ""
    posted_at: str = ""  # ISO date (YYYY-MM-DD)
    tags: list[str] = field(default_factory=list)
    remote: bool | None = None
    years_min: int | None = None
    education: str = ""
    # derived
    id: str = ""
    country: str = ""
    city: str = ""
    category: str = ""
    seniority: str = ""
    skills: list[str] = field(default_factory=list)
    lang: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ---------- text helpers ----------

_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<\s*(?:br|/p|/li|/div|/h\d)\s*/?>", re.I)
_LI_RE = re.compile(r"<\s*li[^>]*>", re.I)


def html_to_text(s: str) -> str:
    if not s:
        return ""
    s = _BR_RE.sub("\n", s)
    s = _LI_RE.sub("\n• ", s)
    s = _TAG_RE.sub("", s)
    s = html.unescape(s).replace("\r", "")
    s = re.sub(r"[ \t ]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    return s.strip()


def to_iso_date(value) -> str:
    """Accept epoch seconds, ISO strings, 'YYYY/MM/DD' or 'YYYYMMDD'."""
    if value in (None, ""):
        return ""
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit() and len(value) >= 9):
            return datetime.fromtimestamp(int(value), tz=timezone.utc).date().isoformat()
        v = str(value).strip()
        if re.fullmatch(r"\d{8}", v):
            return f"{v[:4]}-{v[4:6]}-{v[6:]}"
        m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", v)
        if m:
            return f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}"
    except (ValueError, OSError):
        pass
    return ""


def is_cjk(text: str) -> bool:
    if not text:
        return False
    sample = text[:600]
    cjk = sum(1 for ch in sample if "一" <= ch <= "鿿")
    return cjk > len(sample) * 0.15


# ---------- years / seniority ----------

_YEAR_PATTERNS = [
    re.compile(r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?(?:years?|yrs?)(?:'|’)?\s*(?:of\s+)?(?:\w+\s+){0,4}?(?:experience|exp)", re.I),
    re.compile(r"(?:minimum|at least|min\.?)\s*(?:of\s*)?(\d{1,2})\s*\+?\s*(?:years?|yrs?)", re.I),
    re.compile(r"(\d{1,2})\s*年(?:以上)?(?:相關)?(?:工作)?經驗"),
    re.compile(r"(\d{1,2})\s*年以上"),
    re.compile(r"經驗\s*[:：]?\s*(\d{1,2})\s*年"),
]


def parse_years(text: str) -> int | None:
    if not text:
        return None
    found = None
    for pat in _YEAR_PATTERNS:
        vals = [int(m.group(1)) for m in pat.finditer(text)]
        vals = [v for v in vals if 0 <= v <= 20]
        if vals:
            found = min(vals) if found is None else min(found, min(vals))
    if found is None and re.search(r"經驗不拘|no experience required|entry[- ]level|new grad|應屆", text, re.I):
        return 0
    return found


def infer_seniority(title: str, years: int | None) -> str:
    t = title.lower()
    if re.search(r"intern|實習", t):
        return "實習"
    if re.search(r"\b(?:head|director|vp|principal|staff|architect)\b|總監|架構師|處長|協理", t):
        return "資深/主管"
    if re.search(r"\b(?:lead|manager)\b|主管|經理|組長|課長", t):
        return "資深/主管"
    if re.search(r"\b(?:senior|sr\.?)\b|資深", t):
        return "資深"
    if re.search(r"\b(?:junior|jr\.?|entry|graduate)\b|初階|助理|新鮮人", t):
        return "初階"
    if years is None:
        return ""
    if years == 0:
        return "初階"
    if years <= 2:
        return "初階"
    if years <= 4:
        return "中階"
    if years <= 7:
        return "資深"
    return "資深/主管"


# ---------- category ----------

CATEGORY_RULES: list[tuple[str, str]] = [
    ("資安", r"security|資安|penetration|soc analyst|red team|blue team"),
    ("資料/AI", r"machine learning|\bml\b|\bai\b|data scien|data engineer|data analy|\bnlp\b|computer vision|llm|演算法|algorithm|資料|數據|人工智慧|深度學習|機器學習|影像"),
    ("DevOps/雲端", r"devops|\bsre\b|site reliability|cloud|platform engineer|infrastructure|雲端|維運|系統管理|mis|網管|network engineer"),
    ("嵌入式/韌體", r"embedded|firmware|嵌入式|韌體|bsp|driver|驅動|kernel|mcu"),
    ("硬體/IC", r"hardware|\bic\b|asic|fpga|verilog|layout|硬體|電子|電機|電路|半導體|製程|設備工程|rf engineer|pcb"),
    ("行動開發", r"\bios\b|android|mobile|flutter|react native|\bapp\b"),
    ("前端", r"front[- ]?end|前端|ui engineer|web developer"),
    ("後端", r"back[- ]?end|後端|server|api engineer"),
    ("全端", r"full[- ]?stack|全端"),
    ("測試/QA", r"\bqa\b|\bqc\b|test|測試|quality assurance|\bsdet\b"),
    ("產品/設計", r"product manager|product owner|\bpm\b|產品經理|ui/ux|ux|designer|設計師"),
    ("遊戲", r"game|遊戲|unity|unreal"),
    ("軟體工程", r"software|engineer|developer|programmer|工程師|軟體|程式"),
]
_CATEGORY_COMPILED = [(name, re.compile(p, re.I)) for name, p in CATEGORY_RULES]

TECH_TITLE_RE = re.compile(
    r"engineer|developer|programmer|software|devops|\bsre\b|data|machine learning|\bml\b|\bai\b|"
    r"architect|security|firmware|embedded|hardware|cloud|qa\b|test|frontend|front-end|backend|back-end|"
    r"full[- ]?stack|ios|android|mobile|product manager|technical|it\b|infrastructure|platform|analyst|scientist|"
    r"工程師|開發|軟體|韌體|硬體|資料|數據|演算法|資安|架構師|程式|系統|網管|研發|IC|半導體|產品經理|測試|設計師",
    re.I,
)


def infer_category(title: str, description: str = "") -> str:
    for name, pat in _CATEGORY_COMPILED:
        if pat.search(title):
            return name
    for name, pat in _CATEGORY_COMPILED[:-1]:
        if pat.search(description[:800]):
            return name
    return "其他"


def is_tech_job(title: str, tags: list[str] | None = None, description: str = "") -> bool:
    if TECH_TITLE_RE.search(title or ""):
        return True
    if tags and any(TECH_TITLE_RE.search(t) for t in tags):
        return True
    return len(extract_skills(f"{title} {description[:1500]}")) >= 3


# ---------- location ----------

TW_CITIES = ["台北市", "新北市", "桃園市", "新竹市", "新竹縣", "台中市", "台南市", "高雄市", "基隆市", "苗栗縣",
             "彰化縣", "南投縣", "雲林縣", "嘉義市", "嘉義縣", "屏東縣", "宜蘭縣", "花蓮縣", "台東縣", "澎湖縣", "金門縣", "連江縣"]
_TW_EN = {
    "taipei": "台北市", "new taipei": "新北市", "taoyuan": "桃園市", "hsinchu": "新竹市", "taichung": "台中市",
    "tainan": "台南市", "kaohsiung": "高雄市", "keelung": "基隆市", "miaoli": "苗栗縣", "changhua": "彰化縣",
    "yilan": "宜蘭縣", "hualien": "花蓮縣", "chiayi": "嘉義市", "pingtung": "屏東縣", "nantou": "南投縣", "yunlin": "雲林縣",
}
COUNTRY_RULES: list[tuple[str, str]] = [
    ("台灣", r"taiwan|台灣|臺灣|taipei|hsinchu|taichung|kaohsiung|tainan|taoyuan|" + "|".join(c[:2] for c in TW_CITIES)),
    ("日本", r"japan|日本|tokyo|osaka|東京"),
    ("新加坡", r"singapore|新加坡"),
    ("香港", r"hong kong|香港"),
    ("中國", r"china|中國|大陸|shanghai|beijing|shenzhen|上海|北京|深圳"),
    ("美國", r"\busa?\b|united states|u\.s\.|america|california|new york|san francisco|seattle|texas|remote[- ]us|\bca\b|\bny\b|\bwa\b"),
    ("加拿大", r"canada|toronto|vancouver"),
    ("英國", r"\buk\b|united kingdom|london|england"),
    ("德國", r"germany|deutschland|berlin|munich|münchen|hamburg|frankfurt"),
    ("歐洲", r"europe|\beu\b|\bemea\b|netherlands|amsterdam|france|paris|spain|poland|sweden|ireland|portugal|switzerland|austria|italy"),
    ("澳洲", r"australia|sydney|melbourne|new zealand"),
    ("亞太", r"\bapac\b|\basia\b|korea|seoul|vietnam|philippines|malaysia|thailand|indonesia|india"),
]
_COUNTRY_COMPILED = [(n, re.compile(p, re.I)) for n, p in COUNTRY_RULES]
_REMOTE_RE = re.compile(r"remote|anywhere|worldwide|遠端|在家工作|wfh|work from home", re.I)


def normalize_tw(s: str) -> str:
    return s.replace("臺", "台")


def parse_location(location: str) -> tuple[str, str, bool]:
    """Return (country, city, remote)."""
    loc = normalize_tw(location or "")
    remote = bool(_REMOTE_RE.search(loc))
    city = ""
    for c in TW_CITIES:
        if c in loc or c[:2] in loc:
            city = c
            break
    if not city:
        low = loc.lower()
        for en, zh in sorted(_TW_EN.items(), key=lambda kv: -len(kv[0])):
            if en in low:
                city = zh
                break
    country = "台灣" if city else ""
    if not country:
        for name, pat in _COUNTRY_COMPILED:
            if pat.search(loc):
                country = name
                break
    if not country:
        country = "全球遠端" if remote or re.search(r"worldwide|anywhere|global", loc, re.I) else ("其他" if loc else "")
    if not city and not remote:
        city = loc.split(",")[0].strip()[:30]
    return country, city, remote


# ---------- entry point ----------

def make_id(source: str, source_id: str) -> str:
    return hashlib.sha1(f"{source}:{source_id}".encode()).hexdigest()[:16]


def finalize(job: Job) -> Job:
    job.title = html.unescape(job.title or "").strip()
    job.company = html.unescape(job.company or "").strip()
    job.description = html_to_text(job.description) if "<" in (job.description or "") else (job.description or "").strip()
    job.id = make_id(job.source, str(job.source_id))
    country, city, remote = parse_location(job.location)
    job.country = job.country or country
    job.city = job.city or city
    if job.remote is None:
        job.remote = remote or bool(_REMOTE_RE.search(job.title))
    text = f"{job.title}\n{' '.join(job.tags)}\n{job.description}"
    if job.years_min is None:
        job.years_min = parse_years(job.description)
    job.seniority = infer_seniority(job.title, job.years_min)
    job.category = infer_category(job.title, job.description)
    job.skills = extract_skills(text)
    job.lang = "zh" if is_cjk(job.title + job.description) else "en"
    return job
