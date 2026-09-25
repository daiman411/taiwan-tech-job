import {
  buildMatchers, canonicalSkills, extractSkills, quickMatch, renderResumeHTML, renderResumeMarkdown, tailorResume,
} from "./resume-core.js";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } },
};

const PAGE = 40;
const state = {
  jobs: [], meta: null, matchers: [], shards: 64, descCache: new Map(),
  filtered: [], shown: 0, current: null,
  f: { q: "", myYears: "", includeNoYears: true, days: "0", remoteOnly: false, newOnly: false,
       country: [], city: [], category: [], seniority: [], skills: [], skillMode: "any", source: [], sort: "new" },
  saved: new Set(store.get("ttj.saved", [])),
  profile: store.get("ttj.profile", null) || defaultProfile(),
  semantic: null,
};

function defaultProfile() {
  return { name: "", headline: "", email: "", phone: "", location: "", years: "", links: [], summary: "",
           skills: [], experiences: [], projects: [], education: [], certifications: [], languages: [] };
}

// ---------------------------------------------------------------- data
async function loadData() {
  const [jobsRes, metaRes, skillsRes] = await Promise.all([
    fetch("data/jobs.json", { cache: "no-cache" }), fetch("data/meta.json", { cache: "no-cache" }), fetch("data/skills.json"),
  ]);
  const data = await jobsRes.json();
  state.jobs = data.jobs || [];
  state.meta = metaRes.ok ? await metaRes.json() : null;
  state.shards = state.meta?.shards || 64;
  state.matchers = buildMatchers(await skillsRes.json());
  const upd = data.updated_at ? new Date(data.updated_at) : null;
  $("#updatedAt").textContent = upd ? `更新於 ${upd.toLocaleString("zh-TW", { hour12: false })} · 共 ${state.jobs.length} 筆` : "";
  renderSourceStatus();
}

function shardOf(id) { return String(parseInt(id.slice(0, 4), 16) % state.shards).padStart(2, "0"); }

async function loadDescription(job) {
  const shard = shardOf(job.id);
  if (!state.descCache.has(shard)) {
    state.descCache.set(shard, fetch(`data/desc/${shard}.json`).then((r) => (r.ok ? r.json() : {})).catch(() => ({})));
  }
  const map = await state.descCache.get(shard);
  return map[job.id] || job.summary || "";
}

// ---------------------------------------------------------------- filters
const TODAY = new Date().toISOString().slice(0, 10);
const daysAgo = (d) => new Date(Date.now() - d * 864e5).toISOString().slice(0, 10);
const profileSkillSet = () => new Set(canonicalSkills(state.profile.skills || [], state.matchers));

function matchesText(j, q) {
  const hay = `${j.title} ${j.company} ${j.summary} ${(j.skills || []).join(" ")} ${j.location}`.toLowerCase();
  return q.toLowerCase().split(/\s+/).filter(Boolean).every((t) => hay.includes(t));
}

function applyFilters({ except } = {}) {
  const f = state.f;
  const since = f.days !== "0" ? daysAgo(Number(f.days)) : "";
  const my = f.myYears === "" ? null : Number(f.myYears);
  return state.jobs.filter((j) => {
    if (f.q && !matchesText(j, f.q)) return false;
    if (my !== null) {
      if (j.years_min == null) { if (!f.includeNoYears) return false; } else if (j.years_min > my) return false;
    }
    if (since && (j.posted_at || j.first_seen || "") < since) return false;
    if (f.remoteOnly && !j.remote) return false;
    if (f.newOnly && j.first_seen !== TODAY) return false;
    if (except !== "country" && f.country.length && !f.country.includes(j.country)) return false;
    if (except !== "city" && f.city.length && !f.city.includes(j.city)) return false;
    if (except !== "category" && f.category.length && !f.category.includes(j.category)) return false;
    if (except !== "seniority" && f.seniority.length && !f.seniority.includes(j.seniority || "未標示")) return false;
    if (except !== "source" && f.source.length && !f.source.includes(j.source)) return false;
    if (except !== "skills" && f.skills.length) {
      const s = new Set(j.skills || []);
      if (f.skillMode === "all" ? !f.skills.every((x) => s.has(x)) : !f.skills.some((x) => s.has(x))) return false;
    }
    return true;
  });
}

function countBy(list, key) {
  const m = new Map();
  for (const j of list) {
    const vals = Array.isArray(j[key]) ? j[key] : [j[key] || (key === "seniority" ? "未標示" : "")];
    for (const v of vals) if (v) m.set(v, (m.get(v) || 0) + 1);
  }
  return [...m.entries()].sort((a, b) => b[1] - a[1]);
}

const SOURCE_LABEL = () => Object.fromEntries(Object.entries(state.meta?.sources || {}).map(([k, v]) => [k, v.label || k]));

function renderChecks(boxId, key, labelMap = {}) {
  const counts = countBy(applyFilters({ except: key }), key);
  const selected = state.f[key];
  for (const s of selected) if (!counts.some(([v]) => v === s)) counts.push([s, 0]);
  $(boxId).innerHTML = counts.map(([v, n]) => `
    <label class="check"><input type="checkbox" value="${esc(v)}" ${selected.includes(v) ? "checked" : ""}>
    <span>${esc(labelMap[v] || v)}</span><span class="count">${n}</span></label>`).join("") || `<span class="muted small">無</span>`;
  $$("input", $(boxId)).forEach((inp) => inp.addEventListener("change", () => {
    state.f[key] = $$("input:checked", $(boxId)).map((x) => x.value);
    update();
  }));
}

function renderSkillChips() {
  const counts = countBy(applyFilters({ except: "skills" }), "skills");
  const term = $("#skillSearch").value.trim().toLowerCase();
  const sel = state.f.skills;
  let list = counts.filter(([v]) => !term || v.toLowerCase().includes(term));
  if (!term) list = list.slice(0, 40);
  for (const s of sel) if (!list.some(([v]) => v === s)) list.unshift([s, 0]);
  const mine = profileSkillSet();
  $("#f-skills").innerHTML = list.map(([v, n]) =>
    `<button type="button" class="chip ${sel.includes(v) ? "on" : ""} ${mine.has(v) ? "mine" : ""}" data-v="${esc(v)}">${esc(v)} <small>${n}</small></button>`).join("");
  $$("#f-skills .chip").forEach((b) => b.addEventListener("click", () => {
    const v = b.dataset.v;
    state.f.skills = sel.includes(v) ? sel.filter((x) => x !== v) : [...sel, v];
    update();
  }));
}

function renderActiveChips() {
  const f = state.f;
  const chips = [];
  const add = (label, clear) => chips.push({ label, clear });
  if (f.q) add(`「${f.q}」`, () => { f.q = ""; $("#q").value = ""; });
  if (f.myYears !== "") add(`年資 ≤ ${f.myYears}`, () => { f.myYears = ""; $("#myYears").value = ""; });
  if (f.remoteOnly) add("可遠端", () => { f.remoteOnly = false; $("#remoteOnly").checked = false; });
  if (f.newOnly) add("今天新增", () => { f.newOnly = false; $("#newOnly").checked = false; });
  if (f.days !== "0") add(`${f.days} 天內`, () => { f.days = "0"; $("#days").value = "0"; });
  const labels = SOURCE_LABEL();
  for (const k of ["country", "city", "category", "seniority", "skills", "source"]) {
    for (const v of f[k]) add(k === "source" ? labels[v] || v : v, () => { f[k] = f[k].filter((x) => x !== v); });
  }
  $("#activeChips").innerHTML = chips.map((c, i) => `<button class="chip on" data-i="${i}">${esc(c.label)} ✕</button>`).join("");
  $$("#activeChips .chip").forEach((b) => b.addEventListener("click", () => { chips[b.dataset.i].clear(); update(); }));
}

function sortJobs(list) {
  const mine = profileSkillSet();
  const by = state.f.sort;
  const key = (j) => j.posted_at || j.first_seen || "";
  if (by === "match") {
    return list.map((j) => [j, quickMatch(mine, j.skills) ?? -1]).sort((a, b) => b[1] - a[1] || key(b[0]).localeCompare(key(a[0]))).map((x) => x[0]);
  }
  if (by === "yearsAsc") return [...list].sort((a, b) => (a.years_min ?? 99) - (b.years_min ?? 99) || key(b).localeCompare(key(a)));
  return [...list].sort((a, b) => key(b).localeCompare(key(a)));
}

// ---------------------------------------------------------------- list
function jobCard(j, mine) {
  const m = quickMatch(mine, j.skills);
  const meta = [j.city || j.country, j.remote ? "可遠端" : "", j.years_min != null ? (j.years_min ? `${j.years_min} 年以上` : "經驗不拘") : "", j.salary]
    .filter(Boolean).map(esc).join(" · ");
  const skills = (j.skills || []).slice(0, 8).map((s) => `<span class="tag ${mine.has(s) ? "mine" : ""}">${esc(s)}</span>`).join("");
  const isNew = j.first_seen === TODAY;
  return `<li class="job ${state.current?.id === j.id ? "active" : ""}" data-id="${j.id}" tabindex="0">
    <div class="job-top">
      <div>
        <div class="job-title">${esc(j.title)} ${isNew ? '<span class="badge new">NEW</span>' : ""}</div>
        <div class="job-company">${esc(j.company)} <span class="muted">· ${esc(SOURCE_LABEL()[j.source] || j.source)} · ${esc(j.posted_at || "")}</span></div>
      </div>
      <div class="job-side">
        ${m != null ? `<span class="match" style="--m:${m}">${m}%</span>` : ""}
        <button class="star ${state.saved.has(j.id) ? "on" : ""}" data-star="${j.id}" aria-label="收藏">${state.saved.has(j.id) ? "★" : "☆"}</button>
      </div>
    </div>
    <div class="job-meta">${meta}</div>
    <div class="tags">${skills}</div>
  </li>`;
}

function bindList(ul) {
  $$(".job", ul).forEach((li) => {
    li.addEventListener("click", (e) => { if (!e.target.closest("[data-star]")) openDetail(li.dataset.id); });
    li.addEventListener("keydown", (e) => { if (e.key === "Enter") openDetail(li.dataset.id); });
  });
  $$("[data-star]", ul).forEach((b) => b.addEventListener("click", () => toggleSave(b.dataset.star)));
}

function renderList(reset = true) {
  const mine = profileSkillSet();
  if (reset) state.shown = 0;
  const next = state.filtered.slice(state.shown, state.shown + PAGE);
  state.shown += next.length;
  const html = next.map((j) => jobCard(j, mine)).join("");
  const ul = $("#jobList");
  if (reset) ul.innerHTML = html; else ul.insertAdjacentHTML("beforeend", html);
  bindList(ul);
  $("#more").hidden = state.shown >= state.filtered.length;
  $("#empty").hidden = state.filtered.length > 0;
  $("#resultCount").textContent = `找到 ${state.filtered.length} 筆職缺`;
}

function renderExternalLinks() {
  const kw = state.f.q || state.f.skills.slice(0, 2).join(" ") || "software engineer";
  const e = encodeURIComponent(kw);
  const links = [
    ["LinkedIn", `https://www.linkedin.com/jobs/search/?keywords=${e}&location=Taiwan`],
    ["Indeed", `https://tw.indeed.com/jobs?q=${e}`],
    ["Glassdoor", `https://www.glassdoor.com/Job/jobs.htm?sc.keyword=${e}`],
    ["1111", `https://www.1111.com.tw/search/job?ks=${e}`],
    ["CakeResume", `https://www.cake.me/jobs/${e}`],
  ];
  $("#externalLinks").innerHTML = links.map(([n, u]) => `<a href="${u}" target="_blank" rel="noopener">${n}</a>`).join(" · ");
}

let saveTimer;
function update() {
  state.filtered = sortJobs(applyFilters());
  renderChecks("#f-country", "country");
  renderChecks("#f-city", "city");
  renderChecks("#f-category", "category");
  renderChecks("#f-seniority", "seniority");
  renderChecks("#f-source", "source", SOURCE_LABEL());
  $("#cityBox").hidden = !(state.f.country.length === 0 || state.f.country.includes("台灣"));
  renderSkillChips();
  renderActiveChips();
  renderExternalLinks();
  renderList(true);
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => store.set("ttj.filters", state.f), 300);
}

// ---------------------------------------------------------------- detail
function formatDescription(text) {
  return esc(text.trim())
    .replace(/\n{3,}/g, "\n\n")
    .replace(/\s*【([^】]+)】\s*/g, "\u0000$1\u0000")
    .replace(/\n/g, "<br>")
    .replace(/\u0000([^\u0000]+)\u0000/g, "<h4>$1</h4>");
}

async function openDetail(id) {
  const j = state.jobs.find((x) => x.id === id);
  if (!j) return;
  state.current = j;
  $$("#jobList .job, #savedList .job").forEach((li) => li.classList.toggle("active", li.dataset.id === id));
  const mine = profileSkillSet();
  const d = $("#detail");
  d.hidden = false;
  document.body.classList.add("detail-open");
  $("#detailBody").innerHTML = `
    <h2>${esc(j.title)}</h2>
    <div class="job-company">${esc(j.company)}</div>
    <dl class="facts">
      <dt>地點</dt><dd>${esc(j.location || j.city || j.country || "—")}${j.remote ? "（可遠端）" : ""}</dd>
      <dt>薪資</dt><dd>${esc(j.salary || "未標示")}</dd>
      <dt>年資</dt><dd>${j.years_min == null ? "未標示" : j.years_min ? `${j.years_min} 年以上` : "經驗不拘"}</dd>
      <dt>資歷</dt><dd>${esc(j.seniority || "未標示")}</dd>
      ${j.education ? `<dt>學歷</dt><dd>${esc(j.education)}</dd>` : ""}
      <dt>類別</dt><dd>${esc(j.category)}</dd>
      <dt>來源</dt><dd>${esc(SOURCE_LABEL()[j.source] || j.source)} · 刊登 ${esc(j.posted_at || "—")}</dd>
    </dl>
    <div class="tags">${(j.skills || []).map((s) => `<span class="tag ${mine.has(s) ? "mine" : ""}">${esc(s)}</span>`).join("")}</div>
    <div class="row wrap actions">
      <button class="btn" id="genResume">✨ 產生這份職缺的優化履歷</button>
      <a class="btn ghost" href="${esc(j.url)}" target="_blank" rel="noopener">前往原始職缺 ↗</a>
      <button class="btn ghost" id="detailStar">${state.saved.has(j.id) ? "★ 已收藏" : "☆ 收藏"}</button>
    </div>
    <h3>職缺內容</h3>
    <div class="desc" id="desc"><span class="muted">載入中…</span></div>`;
  $("#genResume").addEventListener("click", () => openResume(j));
  $("#detailStar").addEventListener("click", () => { toggleSave(j.id); openDetail(j.id); });
  const desc = await loadDescription(j);
  if (state.current?.id === id) $("#desc").innerHTML = formatDescription(desc) || '<span class="muted">此來源未提供內容，請見原始職缺。</span>';
  d.scrollTop = 0;
}

function closeDetail() {
  $("#detail").hidden = true;
  document.body.classList.remove("detail-open");
  state.current = null;
  $$(".job.active").forEach((li) => li.classList.remove("active"));
}

function toggleSave(id) {
  if (state.saved.has(id)) state.saved.delete(id); else state.saved.add(id);
  store.set("ttj.saved", [...state.saved]);
  $$(`[data-star="${id}"]`).forEach((b) => { b.classList.toggle("on", state.saved.has(id)); b.textContent = state.saved.has(id) ? "★" : "☆"; });
  renderSaved();
}

function renderSaved() {
  const list = state.jobs.filter((j) => state.saved.has(j.id));
  $("#savedCount").textContent = state.saved.size;
  const ul = $("#savedList");
  ul.innerHTML = list.map((j) => jobCard(j, profileSkillSet())).join("");
  bindList(ul);
  $("#savedEmpty").hidden = list.length > 0;
}

// ---------------------------------------------------------------- résumé
let resumeCtx = null;

function profileIsEmpty(p) {
  return !(p.name || p.summary || (p.skills || []).length || (p.experiences || []).length);
}

async function openResume(job) {
  if (profileIsEmpty(state.profile)) {
    alert("請先到「我的資料」填寫基本資料、技能與經歷，才能產生履歷。");
    switchView("profile");
    return;
  }
  const description = await loadDescription(job);
  resumeCtx = { job: { ...job, description }, semantic: null };
  $("#resumeLang").value = job.lang === "en" ? "en" : "zh";
  $("#resumeTitle").textContent = `優化履歷 · ${job.title} @ ${job.company}`;
  $("#resumeModal").hidden = false;
  document.body.classList.add("modal-open");
  renderResume();
}

function renderResume() {
  if (!resumeCtx) return;
  const r = tailorResume(state.profile, resumeCtx.job, {
    matchers: state.matchers,
    lang: $("#resumeLang").value,
    maxBullets: Number($("#maxBullets").value),
    semantic: resumeCtx.semantic || undefined,
  });
  resumeCtx.result = r;
  $("#resumeOut").innerHTML = renderResumeHTML(r, state.matchers);
  const score = r.matchScore == null ? "—" : `${r.matchScore}%`;
  $("#resumeInsights").innerHTML = `
    <div class="insight"><div class="big">${score}</div><div class="muted small">技能符合度</div></div>
    <div class="insight grow"><div class="small"><strong>已對應的技能</strong></div>
      <div class="tags">${r.matched.map((s) => `<span class="tag mine">${esc(s)}</span>`).join("") || '<span class="muted small">無</span>'}</div></div>
    <div class="insight grow"><div class="small"><strong>職缺要求但你的資料沒有提到</strong></div>
      <div class="tags">${r.missing.map((s) => `<span class="tag warn">${esc(s)}</span>`).join("") || '<span class="muted small">全部都有 🎉</span>'}</div>
      <div class="muted small">若你確實有這些經驗，請補進「我的資料」後再產生；系統不會自動替你加上。</div></div>
    <div class="muted small tip">經歷已依職缺相關度重新排序，相關技能以粗體標示。可以直接在下方履歷上點擊修改，再按「下載 PDF」。</div>`;
}

async function runSemantic() {
  if (!resumeCtx) return;
  const btn = $("#semanticBtn");
  btn.disabled = true;
  try {
    const { semanticScores } = await import("./semantic.js");
    const texts = [
      ...splitProfileTexts(state.profile),
    ];
    const jobText = `${resumeCtx.job.title}\n${resumeCtx.job.description}`.slice(0, 2000);
    resumeCtx.semantic = await semanticScores(jobText, texts, (msg) => { btn.textContent = msg; });
    btn.textContent = "語意比對 ✓";
    renderResume();
  } catch (e) {
    console.error(e);
    btn.textContent = "語意比對失敗";
    alert(`語意模型載入失敗：${e.message}\n仍可使用關鍵字比對的結果。`);
  } finally {
    btn.disabled = false;
  }
}

function splitProfileTexts(p) {
  const out = [];
  for (const e of p.experiences || []) out.push(...(e.bullets || []).filter(Boolean));
  for (const pr of p.projects || []) out.push(...(pr.bullets || []).filter(Boolean));
  out.push(...(p.summary || "").split(/(?<=[。！？!?])\s*|(?<=\.)\s+|\n+/).map((s) => s.trim()).filter(Boolean));
  return out;
}

function closeResume() {
  $("#resumeModal").hidden = true;
  document.body.classList.remove("modal-open");
  $("#semanticBtn").textContent = "語意比對";
}

// ---------------------------------------------------------------- profile form
const LIST_FIELDS = { experiences: ["title", "company", "start", "end", "bullets"], projects: ["name", "link", "description", "bullets"], education: ["school", "degree", "start", "end"] };
const splitLines = (s) => (s || "").split(/\n/).map((x) => x.trim()).filter(Boolean);
const splitComma = (s) => (s || "").split(/[,，、\n]/).map((x) => x.trim()).filter(Boolean);

function addBlock(kind, data = {}) {
  const node = $(`#tpl-${kind}`).content.firstElementChild.cloneNode(true);
  for (const inp of $$("[data-k]", node)) {
    const v = data[inp.dataset.k];
    inp.value = Array.isArray(v) ? v.join("\n") : v ?? "";
  }
  $("[data-remove]", node).addEventListener("click", () => { node.remove(); saveProfile(); });
  $(`#${kind}`).appendChild(node);
}

function fillProfileForm() {
  const p = state.profile;
  const form = $("#profileForm");
  for (const k of ["name", "headline", "email", "phone", "location", "years", "summary"]) form.elements[k].value = p[k] ?? "";
  form.elements.links.value = (p.links || []).join("\n");
  form.elements.skills.value = (p.skills || []).join(", ");
  form.elements.certifications.value = (p.certifications || []).join(", ");
  form.elements.languages.value = (p.languages || []).join(", ");
  for (const kind of Object.keys(LIST_FIELDS)) {
    $(`#${kind}`).innerHTML = "";
    const items = p[kind] || [];
    if (items.length) items.forEach((x) => addBlock(kind, x)); else addBlock(kind);
  }
}

function readProfileForm() {
  const form = $("#profileForm");
  const p = {};
  for (const k of ["name", "headline", "email", "phone", "location", "years", "summary"]) p[k] = form.elements[k].value.trim();
  p.links = splitLines(form.elements.links.value);
  p.skills = splitComma(form.elements.skills.value);
  p.certifications = splitComma(form.elements.certifications.value);
  p.languages = form.elements.languages.value.split(/[,，]/).map((x) => x.trim()).filter(Boolean);
  for (const [kind, keys] of Object.entries(LIST_FIELDS)) {
    p[kind] = $$(`#${kind} .block`).map((b) => {
      const o = {};
      for (const k of keys) {
        const v = $(`[data-k="${k}"]`, b).value.trim();
        o[k] = k === "bullets" ? splitLines(v) : v;
      }
      return o;
    }).filter((o) => Object.values(o).some((v) => (Array.isArray(v) ? v.length : v)));
  }
  return p;
}

let profileTimer;
function saveProfile() {
  clearTimeout(profileTimer);
  profileTimer = setTimeout(() => {
    state.profile = readProfileForm();
    store.set("ttj.profile", state.profile);
    $("#saveState").textContent = `已自動儲存 ${new Date().toLocaleTimeString("zh-TW", { hour12: false })}`;
  }, 400);
}

function bindProfile() {
  const form = $("#profileForm");
  form.addEventListener("input", saveProfile);
  $$("[data-add]").forEach((b) => b.addEventListener("click", () => addBlock(b.dataset.add)));
  $("#exportProfile").addEventListener("click", () => {
    const blob = new Blob([JSON.stringify(readProfileForm(), null, 2)], { type: "application/json" });
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: "my-profile.json" });
    a.click();
    URL.revokeObjectURL(a.href);
  });
  $("#importProfile").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      state.profile = { ...defaultProfile(), ...JSON.parse(await file.text()) };
      store.set("ttj.profile", state.profile);
      fillProfileForm();
      $("#saveState").textContent = "已匯入";
    } catch { alert("檔案格式不正確"); }
    e.target.value = "";
  });
  $("#clearProfile").addEventListener("click", () => {
    if (!confirm("確定要清除所有個人資料？")) return;
    state.profile = defaultProfile();
    store.set("ttj.profile", state.profile);
    fillProfileForm();
  });
  $("#detectSkills").addEventListener("click", () => {
    const found = extractSkills($("#pasteResume").value, state.matchers);
    const cur = splitComma(form.elements.skills.value);
    const merged = canonicalSkills([...cur, ...found], state.matchers);
    form.elements.skills.value = merged.join(", ");
    $("#detectResult").textContent = found.length ? `找到 ${found.length} 項：${found.join("、")}` : "沒有辨識到技能";
    saveProfile();
  });
}

// ---------------------------------------------------------------- misc UI
function switchView(v) {
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === v));
  $$(".view").forEach((el) => { el.hidden = el.id !== `view-${v}`; });
  if (v === "saved") renderSaved();
  if (v === "jobs") update();
}

function renderSourceStatus() {
  const s = state.meta?.sources;
  if (!s) return;
  $("#sourceStatus").innerHTML = "來源狀態：" + Object.values(s).map((v) =>
    `<span class="${v.ok ? "" : "warnText"}" title="${esc(v.error || "")}">${esc(v.label)} ${v.count}${v.ok ? "" : "⚠"}</span>`).join(" · ");
}

function restoreFilters() {
  const saved = store.get("ttj.filters", null);
  if (saved) Object.assign(state.f, saved);
  const f = state.f;
  $("#q").value = f.q; $("#myYears").value = f.myYears; $("#includeNoYears").checked = f.includeNoYears;
  $("#days").value = f.days; $("#remoteOnly").checked = f.remoteOnly; $("#newOnly").checked = f.newOnly; $("#sort").value = f.sort;
  $$('input[name="skillMode"]').forEach((r) => { r.checked = r.value === f.skillMode; });
  if (f.myYears === "" && state.profile.years) { f.myYears = String(state.profile.years); $("#myYears").value = f.myYears; }
}

function bindFilters() {
  let t;
  $("#q").addEventListener("input", (e) => { clearTimeout(t); t = setTimeout(() => { state.f.q = e.target.value.trim(); update(); }, 200); });
  $("#myYears").addEventListener("input", (e) => { state.f.myYears = e.target.value; update(); });
  $("#includeNoYears").addEventListener("change", (e) => { state.f.includeNoYears = e.target.checked; update(); });
  $("#days").addEventListener("change", (e) => { state.f.days = e.target.value; update(); });
  $("#remoteOnly").addEventListener("change", (e) => { state.f.remoteOnly = e.target.checked; update(); });
  $("#newOnly").addEventListener("change", (e) => { state.f.newOnly = e.target.checked; update(); });
  $("#sort").addEventListener("change", (e) => { state.f.sort = e.target.value; update(); });
  $$('input[name="skillMode"]').forEach((r) => r.addEventListener("change", () => { state.f.skillMode = r.value; update(); }));
  $("#skillSearch").addEventListener("input", renderSkillChips);
  $("#useMySkills").addEventListener("click", () => {
    const mine = [...profileSkillSet()];
    if (!mine.length) { alert("請先在「我的資料」填寫技能"); return; }
    state.f.skills = mine; state.f.skillMode = "any"; state.f.sort = "match";
    $("#sort").value = "match";
    $$('input[name="skillMode"]').forEach((r) => { r.checked = r.value === "any"; });
    update();
  });
  $("#resetFilters").addEventListener("click", () => {
    Object.assign(state.f, { q: "", myYears: "", includeNoYears: true, days: "0", remoteOnly: false, newOnly: false,
      country: [], city: [], category: [], seniority: [], skills: [], skillMode: "any", source: [], sort: "new" });
    store.set("ttj.filters", state.f);
    restoreFilters();
    state.f.myYears = ""; $("#myYears").value = "";
    update();
  });
  $("#more").addEventListener("click", () => renderList(false));
  $("#toggleFilters").addEventListener("click", () => $("#filters").classList.toggle("open"));
}

function bindChrome() {
  $$(".tab").forEach((t) => t.addEventListener("click", () => switchView(t.dataset.view)));
  $("#closeDetail").addEventListener("click", closeDetail);
  $("#closeResume").addEventListener("click", closeResume);
  $("#resumeLang").addEventListener("change", renderResume);
  $("#maxBullets").addEventListener("change", renderResume);
  $("#semanticBtn").addEventListener("click", runSemantic);
  $("#printResume").addEventListener("click", () => window.print());
  $("#copyMd").addEventListener("click", async () => {
    if (!resumeCtx?.result) return;
    try {
      await navigator.clipboard.writeText(renderResumeMarkdown(resumeCtx.result));
      $("#copyMd").textContent = "已複製 ✓";
      setTimeout(() => { $("#copyMd").textContent = "複製 Markdown"; }, 1500);
    } catch { alert("無法存取剪貼簿"); }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!$("#resumeModal").hidden) closeResume(); else if (!$("#detail").hidden) closeDetail();
  });
}

async function init() {
  bindChrome();
  bindFilters();
  bindProfile();
  fillProfileForm();
  try {
    await loadData();
  } catch (e) {
    $("#resultCount").textContent = "職缺資料載入失敗，請稍後再試。";
    console.error(e);
    return;
  }
  restoreFilters();
  renderSaved();
  update();
}

init();
