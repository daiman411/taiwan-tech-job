// Pure résumé-tailoring logic. No network, no LLM tokens: everything is keyword and
// skill matching against the job text. It only selects, reorders and highlights the
// user's own content — it never invents experience the user did not enter.

const EN_STOP = new Set(`a an and are as at be but by for from has have in into is it its of on or our that the their
this to we will with you your who what when where which while about across all also any can able work working team
teams experience experiences years year strong good great new plus more other using use used within via etc role job
must should would including include includes based well such like help build develop development ability skills skill
knowledge requirements required preferred responsibilities responsibility candidate company join products product`.split(/\s+/));

export function buildMatchers(skillGroups) {
  const out = [];
  for (const [group, skills] of Object.entries(skillGroups)) {
    for (const [name, aliases] of Object.entries(skills)) {
      try {
        out.push({ name, group, re: new RegExp(aliases.map((a) => `(?:${a})`).join("|"), "i") });
      } catch (e) {
        console.warn("bad skill pattern", name, e);
      }
    }
  }
  return out;
}

export function extractSkills(text, matchers) {
  if (!text) return [];
  return matchers.filter((m) => m.re.test(text)).map((m) => m.name);
}

/** Map what the user typed ("k8s", "reactjs") to canonical names; keep unknown ones as typed. */
export function canonicalSkills(list, matchers) {
  const out = [];
  for (const raw of list) {
    const s = raw.trim();
    if (!s) continue;
    const hit = matchers.find((m) => m.name.toLowerCase() === s.toLowerCase()) || matchers.find((m) => m.re.test(s));
    const name = hit ? hit.name : s;
    if (!out.some((x) => x.toLowerCase() === name.toLowerCase())) out.push(name);
  }
  return out;
}

export function isCJK(text) {
  const sample = (text || "").slice(0, 600);
  const n = [...sample].filter((c) => c >= "一" && c <= "鿿").length;
  return n > sample.length * 0.15;
}

/** Weighted keywords of the job text: English words and CJK bigrams. */
export function jobKeywords(text) {
  const freq = new Map();
  const add = (k, w = 1) => freq.set(k, (freq.get(k) || 0) + w);
  const lower = (text || "").toLowerCase();
  for (const w of lower.match(/[a-z][a-z0-9+#.\-]{2,}/g) || []) {
    const t = w.replace(/[.\-]+$/, "");
    if (!EN_STOP.has(t)) add(t);
  }
  for (const run of lower.match(/[一-鿿]{2,}/g) || []) {
    for (let i = 0; i < run.length - 1; i++) add(run.slice(i, i + 2), 0.6);
  }
  return freq;
}

function keywordScore(text, kw) {
  if (!text) return 0;
  const own = jobKeywords(text);
  let s = 0;
  for (const [k, w] of own) if (kw.has(k)) s += Math.min(kw.get(k), 3) * Math.min(w, 2);
  return s;
}

export function scoreText(text, ctx) {
  const skills = extractSkills(text, ctx.matchers).filter((s) => ctx.jobSkillSet.has(s));
  return skills.length * 4 + keywordScore(text, ctx.keywords) * 0.5;
}

const L = {
  zh: {
    summary: "個人摘要", skills: "專業技能", matchedSkills: "與職缺相關", otherSkills: "其他技能",
    experience: "工作經歷", projects: "專案經歷", education: "學歷", certs: "證照", languages: "語言",
    present: "至今", contact: "聯絡方式",
  },
  en: {
    summary: "Summary", skills: "Skills", matchedSkills: "Relevant to this role", otherSkills: "Additional",
    experience: "Experience", projects: "Projects", education: "Education", certs: "Certifications",
    languages: "Languages", present: "Present", contact: "Contact",
  },
};
export const labels = (lang) => L[lang] || L.zh;

function splitSentences(text) {
  return (text || "").split(/(?<=[。！？!?])\s*|(?<=\.)\s+|\n+/).map((s) => s.trim()).filter(Boolean);
}

/**
 * @param profile  user profile (see app.js defaultProfile)
 * @param job      job index row + `description`
 * @param opts     { matchers, lang?: 'zh'|'en', maxBullets?: number, semantic?: Map<string, number> }
 */
export function tailorResume(profile, job, opts) {
  const { matchers } = opts;
  const jobText = `${job.title}\n${(job.skills || []).join(" ")}\n${job.description || job.summary || ""}`;
  const jobSkills = [...new Set([...(job.skills || []), ...extractSkills(jobText, matchers)])];
  const jobSkillSet = new Set(jobSkills);
  const ctx = { matchers, jobSkillSet, keywords: jobKeywords(jobText) };
  const semantic = opts.semantic || new Map();
  const score = (t) => scoreText(t, ctx) + (semantic.get(t) || 0) * 10;
  const lang = opts.lang || (job.lang === "en" ? "en" : "zh");
  const maxBullets = opts.maxBullets ?? 5;

  const userSkills = canonicalSkills(profile.skills || [], matchers);
  const userSkillLower = new Set(userSkills.map((s) => s.toLowerCase()));
  // skills mentioned anywhere in the user's own experience count as "has it" too
  const evidenceText = [
    profile.summary,
    ...(profile.experiences || []).flatMap((e) => [e.title, ...(e.bullets || [])]),
    ...(profile.projects || []).flatMap((p) => [p.name, p.description, ...(p.bullets || [])]),
  ].join("\n");
  const evidenceSkills = new Set(extractSkills(evidenceText, matchers));
  const has = (s) => userSkillLower.has(s.toLowerCase()) || evidenceSkills.has(s);

  const matched = jobSkills.filter(has);
  const missing = jobSkills.filter((s) => !has(s));
  const matchedSet = new Set(matched);
  const otherSkills = userSkills.filter((s) => !matchedSet.has(s));
  const matchScore = jobSkills.length ? Math.round((matched.length / jobSkills.length) * 100) : null;

  const experiences = (profile.experiences || []).map((e) => {
    const bullets = (e.bullets || []).filter(Boolean).map((b, i) => ({ text: b, score: score(b), i }));
    const ranked = [...bullets].sort((a, b) => b.score - a.score || a.i - b.i);
    const keep = ranked.slice(0, maxBullets);
    return { ...e, bullets: keep.map((b) => b.text), relevance: bullets.reduce((s, b) => s + b.score, 0) + score(e.title || "") };
  });

  const projects = (profile.projects || [])
    .map((p, i) => ({ ...p, relevance: score(`${p.name}\n${p.description || ""}\n${(p.bullets || []).join("\n")}`), i }))
    .sort((a, b) => b.relevance - a.relevance || a.i - b.i)
    .slice(0, opts.maxProjects ?? 3);

  const headline = buildHeadline(profile, job, matched);
  const summary = buildSummary(profile, job, matched, lang, score);

  return {
    lang, headline, summary, matchScore, jobSkills, matched, missing,
    skills: { matched, other: otherSkills },
    experiences, projects,
    education: profile.education || [],
    certifications: profile.certifications || [],
    languages: profile.languages || [],
    basics: {
      name: profile.name, email: profile.email, phone: profile.phone, location: profile.location,
      links: (profile.links || []).filter(Boolean),
    },
    job: { title: job.title, company: job.company, url: job.url },
  };
}

function buildHeadline(profile, job, matched) {
  const role = (profile.headline || "").trim() || job.title;
  const top = matched.slice(0, 3).join(" · ");
  return top ? `${role} | ${top}` : role;
}

function buildSummary(profile, job, matched, lang, score) {
  const years = Number(profile.years) || 0;
  const top = matched.slice(0, 4);
  const own = splitSentences(profile.summary)
    .map((s, i) => ({ s, sc: score(s), i }))
    .sort((a, b) => b.sc - a.sc || a.i - b.i)
    .slice(0, 2)
    .sort((a, b) => a.i - b.i)
    .map((x) => x.s);
  const role = (profile.headline || "").trim();
  let opening;
  if (lang === "en") {
    opening = [
      years ? `${role || "Engineer"} with ${years}+ years of experience` : role || "Engineer",
      top.length ? ` in ${top.join(", ")}.` : ".",
    ].join("");
    const closing = job.company ? `Looking to bring these strengths to the ${job.title} role at ${job.company}.` : "";
    return [opening, ...own, closing].filter(Boolean).join(" ");
  }
  opening = `${years ? `具備 ${years} 年以上${role || "相關"}經驗` : role || "工程背景"}${top.length ? `，熟悉 ${top.join("、")}` : ""}。`;
  const closing = job.company ? `期望以上述能力投入${job.company}「${job.title}」職務。` : "";
  return [opening, ...own, closing].filter(Boolean).join("");
}

// ---------- rendering ----------

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

export function highlight(text, terms, matchers) {
  let html = esc(text);
  const ms = matchers.filter((m) => terms.includes(m.name));
  for (const m of ms) {
    const g = new RegExp(m.re.source, "gi");
    html = html.replace(g, (x) => (x.length > 1 ? `<strong>${x}</strong>` : x));
  }
  return html.replace(/<strong>([^<]*)<strong>([^<]*)<\/strong>([^<]*)<\/strong>/g, "<strong>$1$2$3</strong>");
}

function period(x, t) {
  const a = x.start || "", b = x.end || (x.start ? t.present : "");
  return a || b ? `${esc(a)}${a && b ? " – " : ""}${esc(b)}` : "";
}

export function renderResumeHTML(r, matchers) {
  const t = labels(r.lang);
  const hl = (s) => highlight(s, r.skills.matched, matchers);
  const b = r.basics;
  const contact = [b.email, b.phone, b.location, ...b.links].filter(Boolean).map(esc).join(" · ");
  const section = (title, body) => (body ? `<section><h2>${title}</h2>${body}</section>` : "");
  const exp = r.experiences.map((e) => `
    <div class="r-item"><div class="r-row"><strong>${esc(e.title)}</strong>${e.company ? ` · ${esc(e.company)}` : ""}<span class="r-date">${period(e, t)}</span></div>
    ${e.bullets.length ? `<ul>${e.bullets.map((x) => `<li>${hl(x)}</li>`).join("")}</ul>` : ""}</div>`).join("");
  const proj = r.projects.map((p) => `
    <div class="r-item"><div class="r-row"><strong>${esc(p.name)}</strong>${p.link ? ` · <span>${esc(p.link)}</span>` : ""}</div>
    ${p.description ? `<p>${hl(p.description)}</p>` : ""}
    ${(p.bullets || []).length ? `<ul>${p.bullets.filter(Boolean).map((x) => `<li>${hl(x)}</li>`).join("")}</ul>` : ""}</div>`).join("");
  const edu = r.education.map((e) => `
    <div class="r-item"><div class="r-row"><strong>${esc(e.school)}</strong>${e.degree ? ` · ${esc(e.degree)}` : ""}<span class="r-date">${period(e, t)}</span></div></div>`).join("");
  const skills = `
    ${r.skills.matched.length ? `<p><span class="r-k">${t.matchedSkills}：</span>${r.skills.matched.map(esc).join("、")}</p>` : ""}
    ${r.skills.other.length ? `<p><span class="r-k">${t.otherSkills}：</span>${r.skills.other.map(esc).join("、")}</p>` : ""}`;
  return `<article class="resume" lang="${r.lang === "en" ? "en" : "zh-Hant"}">
    <header><h1>${esc(b.name || "")}</h1><div class="r-headline">${esc(r.headline)}</div>${contact ? `<div class="r-contact">${contact}</div>` : ""}</header>
    ${section(t.summary, r.summary ? `<p>${hl(r.summary)}</p>` : "")}
    ${section(t.skills, skills.trim())}
    ${section(t.experience, exp)}
    ${section(t.projects, proj)}
    ${section(t.education, edu)}
    ${section(t.certs, r.certifications.length ? `<p>${r.certifications.map(esc).join("、")}</p>` : "")}
    ${section(t.languages, r.languages.length ? `<p>${r.languages.map(esc).join("、")}</p>` : "")}
  </article>`;
}

export function renderResumeMarkdown(r) {
  const t = labels(r.lang);
  const b = r.basics;
  const lines = [`# ${b.name || ""}`, `**${r.headline}**`, [b.email, b.phone, b.location, ...b.links].filter(Boolean).join(" · "), ""];
  if (r.summary) lines.push(`## ${t.summary}`, r.summary, "");
  lines.push(`## ${t.skills}`);
  if (r.skills.matched.length) lines.push(`- ${t.matchedSkills}: ${r.skills.matched.join(", ")}`);
  if (r.skills.other.length) lines.push(`- ${t.otherSkills}: ${r.skills.other.join(", ")}`);
  lines.push("");
  if (r.experiences.length) {
    lines.push(`## ${t.experience}`);
    for (const e of r.experiences) {
      lines.push(`### ${e.title}${e.company ? ` · ${e.company}` : ""}  (${[e.start, e.end || t.present].filter(Boolean).join(" – ")})`);
      for (const x of e.bullets) lines.push(`- ${x}`);
      lines.push("");
    }
  }
  if (r.projects.length) {
    lines.push(`## ${t.projects}`);
    for (const p of r.projects) {
      lines.push(`### ${p.name}`);
      if (p.description) lines.push(p.description);
      for (const x of (p.bullets || []).filter(Boolean)) lines.push(`- ${x}`);
      lines.push("");
    }
  }
  if (r.education.length) {
    lines.push(`## ${t.education}`);
    for (const e of r.education) lines.push(`- ${e.school}${e.degree ? `, ${e.degree}` : ""} (${[e.start, e.end].filter(Boolean).join(" – ")})`);
    lines.push("");
  }
  if (r.certifications.length) lines.push(`## ${t.certs}`, r.certifications.join(", "), "");
  if (r.languages.length) lines.push(`## ${t.languages}`, r.languages.join(", "), "");
  return lines.join("\n");
}

/** Skill overlap between a profile and a job index row, 0–100 (null when the job lists no skills). */
export function quickMatch(profileSkillSet, jobSkills) {
  if (!jobSkills || !jobSkills.length || !profileSkillSet.size) return null;
  let n = 0;
  for (const s of jobSkills) if (profileSkillSet.has(s)) n++;
  return Math.round((n / jobSkills.length) * 100);
}
