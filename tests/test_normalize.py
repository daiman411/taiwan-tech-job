from scraper.normalize import Job, finalize, infer_category, parse_location, parse_years
from scraper.skills import extract_skills


def test_extract_skills_mixed_language():
    s = extract_skills("熟悉C語言與C++，會SQL語法、Python、Go語言、Docker/K8s，有機器學習經驗")
    for k in ["C", "C++", "SQL", "Python", "Go", "Docker", "Kubernetes", "Machine Learning"]:
        assert k in s
    assert "Java" not in extract_skills("JavaScript and TypeScript")
    assert "C" not in extract_skills("a c-level executive")


def test_parse_years():
    assert parse_years("3年以上工作經驗") == 3
    assert parse_years("工作經歷：5年以上") == 5
    assert parse_years("You have 4+ years of professional experience in Go") == 4
    assert parse_years("At least 2 years with React") == 2
    assert parse_years("經驗不拘") == 0
    assert parse_years("We love dogs") is None


def test_parse_location():
    assert parse_location("台北市內湖區") == ("台灣", "台北市", False)
    assert parse_location("臺中市西屯區")[1] == "台中市"
    assert parse_location("Hsinchu, Taiwan")[:2] == ("台灣", "新竹市")
    assert parse_location("Remote (Worldwide)")[0] == "全球遠端"
    assert parse_location("Berlin, Germany")[0] == "德國"


def test_category():
    assert infer_category("Senior Backend Engineer") == "後端"
    assert infer_category("韌體工程師") == "嵌入式/韌體"
    assert infer_category("Machine Learning Engineer") == "資料/AI"


def test_finalize():
    j = finalize(Job(source="x", source_id="1", title="資深前端工程師", company="A", url="u",
                     description="<p>需具備 3 年以上 React 經驗</p><ul><li>TypeScript</li></ul>", location="台北市信義區"))
    assert j.id and len(j.id) == 16
    assert j.years_min == 3 and j.seniority == "資深" and j.category == "前端"
    assert {"React", "TypeScript"} <= set(j.skills)
    assert j.lang == "zh" and j.city == "台北市"
    assert "<" not in j.description
