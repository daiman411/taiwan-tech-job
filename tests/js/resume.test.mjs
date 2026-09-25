import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { buildMatchers, canonicalSkills, extractSkills, tailorResume, renderResumeHTML, renderResumeMarkdown, quickMatch } from "../../docs/js/resume-core.js";

const groups = JSON.parse(readFileSync(new URL("../../docs/data/skills.json", import.meta.url)));
const matchers = buildMatchers(groups);

const profile = {
  name: "王小明", headline: "後端工程師", years: 5, email: "a@b.c",
  summary: "專注於高流量系統。熱愛貓咪。擅長以 Python 與 Kubernetes 建構可擴展服務。",
  skills: ["python", "k8s", "React", "Photoshop"],
  experiences: [{ title: "Senior Engineer", company: "ACME", start: "2021", end: "",
    bullets: ["帶領前端團隊改版官網", "以 Python/FastAPI 重構訂單 API，延遲降低 40%", "導入 Docker 與 Kubernetes 部署"] }],
  projects: [{ name: "Side project", description: "React 小工具" }, { name: "ETL pipeline", description: "用 Airflow 與 PostgreSQL 建立資料管線" }],
  education: [{ school: "台大", degree: "資工碩士", start: "2015", end: "2017" }],
};
const job = { title: "後端工程師", company: "Foo", lang: "zh", skills: ["Python", "Kubernetes", "PostgreSQL", "Go"],
  description: "負責 Python 後端與 PostgreSQL，熟悉 Docker、Kubernetes 佳，會 Go 加分" };

test("same skill extraction as the Python scraper", () => {
  assert.deepEqual(extractSkills("熟悉C語言與C++，會SQL語法、Python、Go語言、Docker/K8s，有機器學習經驗", matchers),
    ["Python", "C++", "Go", "SQL", "C", "Docker", "Kubernetes", "Machine Learning"]);
});

test("canonicalizes typed skills", () => {
  assert.deepEqual(canonicalSkills(["python", "k8s", "Photoshop", "Python"], matchers), ["Python", "Kubernetes", "Photoshop"]);
});

test("tailors without inventing content", () => {
  const r = tailorResume(profile, job, { matchers });
  assert.deepEqual(r.skills.matched.sort(), ["Docker", "Kubernetes", "PostgreSQL", "Python"].sort());
  assert.deepEqual(r.missing, ["Go"]);
  assert.notEqual(r.experiences[0].bullets[0], "帶領前端團隊改版官網");
  assert.equal(r.experiences[0].bullets.at(-1), "帶領前端團隊改版官網");
  assert.equal(r.projects[0].name, "ETL pipeline");
  assert.match(r.summary, /5 年以上後端工程師經驗/);
  assert.match(r.summary, /Kubernetes 建構/);
  assert.doesNotMatch(r.summary, /貓咪/);
  const allUserText = JSON.stringify(profile);
  for (const e of r.experiences) for (const b of e.bullets) assert.ok(allUserText.includes(b));
  const html = renderResumeHTML(r, matchers);
  assert.match(html, /<strong>Python<\/strong>/);
  assert.match(renderResumeMarkdown(r), /## 工作經歷/);
});

test("english output for english jobs", () => {
  const r = tailorResume(profile, { ...job, lang: "en", title: "Backend Engineer" }, { matchers });
  assert.match(r.summary, /with 5\+ years of experience in/);
});

test("quickMatch", () => {
  assert.equal(quickMatch(new Set(["Python", "Go"]), ["Python", "Go", "Rust", "C"]), 50);
  assert.equal(quickMatch(new Set(), ["Python"]), null);
});
