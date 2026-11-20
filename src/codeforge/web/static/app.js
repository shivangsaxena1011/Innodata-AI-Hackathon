/* CodeForge AI dashboard. All data comes from the local API (real pipeline output). */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch { /* keep status text */ }
    throw new Error(msg);
  }
  return res.json();
}

/* ---------- logos: prefer the team's original PNG artwork when present ---------- */
function useOriginalLogos() {
  const map = { codeforge: "/static/assets/codeforge-logo.png", techtitan: "/static/assets/tech-titan-logo.png" };
  Object.entries(map).forEach(([key, url]) => {
    const probe = new Image();
    probe.onload = () => $$(`img[data-logo="${key}"]`).forEach((img) => { img.src = url; });
    probe.src = url;
  });
}

/* ---------- background particles ---------- */
function particles() {
  const c = $("#particles");
  if (!c || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const ctx = c.getContext("2d");
  let w, h, pts;
  const resize = () => {
    w = c.width = innerWidth; h = c.height = innerHeight;
    pts = Array.from({ length: Math.min(70, Math.floor(w / 22)) }, () => ({
      x: Math.random() * w, y: Math.random() * h, vx: (Math.random() - .5) * .25, vy: (Math.random() - .5) * .25,
    }));
  };
  resize(); addEventListener("resize", resize);
  (function tick() {
    ctx.clearRect(0, 0, w, h);
    for (const p of pts) {
      p.x = (p.x + p.vx + w) % w; p.y = (p.y + p.vy + h) % h;
      ctx.fillStyle = "rgba(103,232,249,.55)"; ctx.fillRect(p.x, p.y, 1.6, 1.6);
    }
    for (let i = 0; i < pts.length; i++) for (let j = i + 1; j < pts.length; j++) {
      const a = pts[i], b = pts[j], d = Math.hypot(a.x - b.x, a.y - b.y);
      if (d < 120) { ctx.strokeStyle = `rgba(99,102,241,${(1 - d / 120) * .18})`; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); }
    }
    requestAnimationFrame(tick);
  })();
}

function reveal() {
  document.documentElement.classList.add("js");
  const els = $$(".reveal");
  if (!("IntersectionObserver" in window)) { els.forEach((el) => el.classList.add("in")); return; }
  const io = new IntersectionObserver((es) => es.forEach((e) => e.isIntersecting && e.target.classList.add("in")), { threshold: .05 });
  els.forEach((el) => io.observe(el));
  setTimeout(() => els.forEach((el) => el.classList.add("in")), 2500); // never leave content hidden
}

/* ---------- status + hero stats ---------- */
async function loadStatus() {
  try {
    const s = await api("/api/status");
    const set = (k, ok, title) => { const d = $(`.dot[data-k="${k}"]`); d.classList.add(ok ? "ok" : "bad"); d.title = title; };
    set("docker", !!s.docker, s.docker || "Docker not reachable");
    set("harbor", !!s.harbor, s.harbor ? `Harbor ${s.harbor}` : "Harbor CLI not found");
    const llmOk = s.llm.gemini_key_present || s.llm.ollama_installed;
    set("llm", llmOk, `${s.llm.model} (free tier${s.llm.ollama_installed ? ", Ollama fallback" : ""})`);
  } catch { /* status is cosmetic */ }
}

function countUp(el, target, suffix = "") {
  if (document.hidden) { el.textContent = target + suffix; return; } // rAF is paused when hidden
  const start = performance.now(), dur = 1100;
  const step = (t) => {
    const k = Math.min(1, (t - start) / dur), v = target * (1 - Math.pow(1 - k, 3));
    el.textContent = (Number.isInteger(target) ? Math.round(v) : v.toFixed(1)) + suffix;
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function renderStats(tasks) {
  const valid = tasks.filter((t) => t.status === "valid");
  if (!valid.length) return;
  const avg = valid.reduce((a, t) => a + (t.score || 0), 0) / valid.length;
  const ms = valid.map((t) => t.mutation_score).filter((x) => x != null);
  countUp($('[data-stat="tasks"]'), valid.length);
  countUp($('[data-stat="score"]'), Math.round(avg * 10) / 10);
  if (ms.length) countUp($('[data-stat="mutants"]'), Math.round(100 * ms.reduce((a, b) => a + b, 0) / ms.length), "%");
  countUp($('[data-stat="archetypes"]'), new Set(valid.map((t) => t.archetype)).size);
}

/* ---------- analysis ---------- */
async function analyze() {
  const btn = $("#analyze-btn"), box = $("#analysis");
  btn.disabled = true; btn.textContent = "Analyzing…";
  try {
    const a = await api("/api/analyze", { method: "POST", body: JSON.stringify({ repo: $("#repo").value || "sample", ref: $("#ref").value || null }) });
    const total = Object.values(a.languages).reduce((x, y) => x + y, 0) || 1;
    box.innerHTML = `
      <h3>${esc(a.name)} ${a.is_sample ? '<span class="chip">bundled sample, not the Innodata repo</span>' : ""}</h3>
      <div class="kv">
        <div><small>Commit</small><b><code>${esc(a.commit.slice(0, 12))}</code></b></div>
        <div><small>Language</small><b>${esc(a.language)}</b></div>
        <div><small>Framework</small><b>${esc(a.framework || "—")}</b></div>
        <div><small>Tests</small><b>${esc(a.test_framework || "—")}</b></div>
        <div><small>Files · symbols</small><b>${a.files} · ${a.symbols}</b></div>
        <div><small>Execution adapter</small><b>${a.supported ? esc(a.adapter) : "unsupported"}</b></div>
      </div>
      <div class="langbar">${Object.entries(a.languages).map(([l, n]) => `<span title="${esc(l)}" style="width:${(100 * n / total).toFixed(1)}%"></span>`).join("")}</div>
      <small class="sub">Extension points</small>
      <div class="chips">${a.extension_points.map((p) => `<span class="chip">${esc(p.split(" ").slice(1).join(" "))}</span>`).join("")}</div>
      <details><summary>Ranked repository map (token-budgeted LLM context)</summary><pre class="code">${esc(a.repo_map)}</pre></details>
      ${a.supported ? "" : `<p class="chip no">${esc(a.unsupported_reason)}</p>`}`;
    box.classList.remove("hidden");
  } catch (e) {
    box.innerHTML = `<p class="chip no">${esc(e.message)}</p>`; box.classList.remove("hidden");
  } finally { btn.disabled = false; btn.textContent = "Analyze"; }
}

/* ---------- live pipeline ---------- */
const STAGES = [
  ["repository", "Repository"], ["analysis", "Analysis"], ["environment", "Docker env"], ["baseline", "Baseline"],
  ["discovery", "Discovery"], ["spec", "Spec"], ["tests", "Hidden tests"], ["reference", "Reference"],
  ["validation", "Red · Green"], ["mutation", "Mutation"], ["harbor", "Harbor"],
];

function resetStepper() {
  $("#stepper").innerHTML = STAGES.map(([k, label], i) => `<li data-stage="${k}"><span class="ic">${i + 1}</span>${label}</li>`).join("");
  $("#console").innerHTML = ""; $("#candidates").innerHTML = "";
}

const STAGE_ALIAS = { strengthen: "mutation", repair: "validation" };

function applyEvent(e) {
  const li = $(`#stepper li[data-stage="${STAGE_ALIAS[e.stage] || e.stage}"]`);
  if (li) {
    if (e.status === "started") {
      $$("#stepper li.active").forEach((x) => { if (x !== li) x.classList.remove("active"); });
      li.classList.remove("done", "failed"); li.classList.add("active");
    } else if (e.status === "done") { li.classList.remove("active", "failed"); li.classList.add("done"); li.querySelector(".ic").textContent = "✓"; }
    else if (e.status === "failed") { li.classList.remove("active"); li.classList.add("failed"); li.querySelector(".ic").textContent = "!"; }
  }
  if (e.stage === "discovery" && e.status === "done" && e.data.candidates) {
    $("#candidates").innerHTML = e.data.candidates.map((c) => `
      <div class="cand"><span class="chip ${c.accepted ? "ok" : "no"}">${c.accepted ? "selected" : "rejected"}</span>
      <span class="chip">${esc(c.archetype)}</span><b>${esc(c.title)}</b>
      <span class="why">${c.accepted ? `novelty ${Number(c.novelty).toFixed(2)}` : esc(c.reason || "")}</span></div>`).join("");
  }
  const cls = e.status === "failed" ? "bad" : e.status === "done" ? "ok" : "st";
  const line = `<span class="t">${esc(e.ts.slice(11, 19))}</span> <span class="${cls}">${esc(e.stage.padEnd(11))}</span> ${esc(e.message)}\n`;
  const con = $("#console"); con.insertAdjacentHTML("beforeend", line); con.scrollTop = con.scrollHeight;
}

async function forge(ev) {
  ev.preventDefault();
  const btn = $("#forge-btn"); btn.disabled = true; btn.textContent = "Forging…";
  $("#live").classList.remove("hidden"); resetStepper();
  const pill = $("#run-state"); pill.className = "pill running"; pill.textContent = "running";
  try {
    const body = { repo: $("#repo").value || "sample", ref: $("#ref").value || null, tasks: Number($("#count").value), harbor: $("#harbor").checked };
    const { run_id } = await api("/api/runs", { method: "POST", body: JSON.stringify(body) });
    let since = 0;
    for (;;) {
      const r = await api(`/api/runs/${run_id}?since=${since}`);
      r.events.forEach(applyEvent); since = r.next;
      if (r.status !== "running") {
        pill.className = `pill ${r.status}`; pill.textContent = r.status;
        $$("#stepper li.active").forEach((x) => x.classList.remove("active"));
        if (r.summary) appendRunLinks(run_id, r.summary);
        await loadTasks();
        break;
      }
      await new Promise((res) => setTimeout(res, 1500));
    }
  } catch (e) {
    pill.className = "pill failed"; pill.textContent = "error";
    $("#console").insertAdjacentHTML("beforeend", `<span class="bad">${esc(e.message)}</span>\n`);
  } finally { btn.disabled = false; btn.textContent = "Forge"; }
}

function appendRunLinks(runId, s) {
  $("#console").insertAdjacentHTML("beforeend",
    `<span class="ok">run ${esc(s.status)}: ${s.accepted} valid, ${s.rejected} rejected</span>  <a href="/api/runs/${esc(runId)}/report" target="_blank" style="color:#67e8f9">open evidence report ↗</a>\n`);
}

/* ---------- tasks ---------- */
function ring(score) {
  const r = 26, c = 2 * Math.PI * r, v = Math.max(0, Math.min(100, score || 0));
  return `<div class="ring"><svg width="64" height="64" viewBox="0 0 64 64">
    <defs><linearGradient id="rg" x1="0" x2="1"><stop offset="0" stop-color="#22d3ee"/><stop offset="1" stop-color="#a855f7"/></linearGradient></defs>
    <circle cx="32" cy="32" r="${r}" stroke="#1e293b" stroke-width="6" fill="none"/>
    <circle class="fg" cx="32" cy="32" r="${r}" stroke="url(#rg)" stroke-width="6" fill="none" stroke-linecap="round"
      stroke-dasharray="${c}" stroke-dashoffset="${c}" data-target="${c * (1 - v / 100)}"/></svg>
    <span class="val">${Math.round(v)}</span></div>`;
}

async function loadTasks() {
  let tasks = [];
  try { tasks = await api("/api/tasks"); } catch { return; }
  renderStats(tasks);
  const box = $("#task-cards");
  if (!tasks.length) { box.innerHTML = '<p class="empty">No tasks yet. Forge one above.</p>'; return; }
  box.innerHTML = tasks.map((t, i) => `
    <article class="card" style="animation-delay:${i * 60}ms" data-repo="${esc(t.repo)}" data-id="${esc(t.task_id)}" tabindex="0">
      <div class="card-top">${ring(t.score)}<div>
        <span class="eyebrow">${esc((t.archetype || "").replace(/_/g, " "))}</span>
        <h3>${esc(t.title)}</h3></div></div>
      <div class="gates">${(t.gates || []).map((g) => `<span class="g ${esc(g.status)}" title="${esc(g.gate)}: ${esc(g.summary)}"></span>`).join("")}</div>
      <div class="meta"><span>${esc(t.repo)} @ ${esc((t.commit || "").slice(0, 10))}</span>
        <span>${t.mutation_score != null ? `mutants ${Math.round(t.mutation_score * 100)}%` : ""}</span></div>
    </article>`).join("");
  requestAnimationFrame(() => $$(".ring circle.fg").forEach((c) => { c.style.strokeDashoffset = c.dataset.target; }));
  $$(".card", box).forEach((card) => {
    const open = () => openTask(card.dataset.repo, card.dataset.id);
    card.addEventListener("click", open);
    card.addEventListener("keydown", (e) => e.key === "Enter" && open());
  });
}

/* ---------- drawer ---------- */
let current = null;
function md(text) {
  return esc(text).replace(/^### (.*)$/gm, "<h4>$1</h4>").replace(/^## (.*)$/gm, "<h4>$1</h4>").replace(/^# (.*)$/gm, "<h3>$1</h3>")
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/^(?:- |\d+\. )(.*)$/gm, "<li>$1</li>").replace(/\n{2,}/g, "<br>");
}
function diffHtml(d) {
  return d.split("\n").map((l) => {
    const c = l.startsWith("+++") || l.startsWith("---") ? "hunk" : l.startsWith("+") ? "add" : l.startsWith("-") ? "del" : l.startsWith("@@") ? "hunk" : "";
    return c ? `<span class="${c}">${esc(l)}</span>` : esc(l) + "\n";
  }).join("");
}
function bar(label, v) {
  const pct = v == null ? null : Math.round(v * 100);
  return `<div class="bar"><small>${label}: <b>${pct == null ? "n/a" : pct + "%"}</b></small><div class="track2"><div class="fill" data-w="${pct || 0}"></div></div></div>`;
}

function renderTab(tab) {
  $$("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  const t = current, body = $("#tab-body"), m = t.manifest, v = m.validation || {};
  if (tab === "overview") body.innerHTML = `<div>${md(t.instruction)}</div>`;
  if (tab === "diff") body.innerHTML = `<p class="sub">${esc(m.reference.explanation || "")}</p><pre class="code diff">${diffHtml(t.diff)}</pre>`;
  if (tab === "tests") body.innerHTML = Object.entries(t.feature_tests).map(([p, c]) => `<h4><code>${esc(p)}</code></h4><pre class="code">${esc(c)}</pre>`).join("")
    + `<h4>Requirement → test traceability</h4><ul>${(m.traceability || []).map((x) => `<li><code>${esc(x.test_name)}</code> → ${x.criteria.map(esc).join(", ")}</li>`).join("")}</ul>`;
  if (tab === "manifest") body.innerHTML = `<h4>task_manifest.json</h4><pre class="code">${esc(JSON.stringify(m, null, 2))}</pre><h4>task.toml</h4><pre class="code">${esc(t.task_toml)}</pre>`;
  if (tab === "validation") {
    const val = t.validation || {};
    const mut = val.mutation_result, sem = val.semantic_mutation_result;
    const score = val.score;
    body.innerHTML = `
      <div class="kv"><div><small>Status</small><b><span class="badge ${esc(v.status)}">${esc(v.status)}</span></b></div>
        <div><small>Validity score</small><b>${esc(v.validity_score)}</b></div>
        <div><small>Changed-line coverage</small><b>${v.coverage && v.coverage.percent != null ? v.coverage.percent + "%" : "n/a"}</b></div>
        <div><small>Harbor oracle / nop</small><b>${val.harbor_validation ? `${val.harbor_validation.oracle.reward} / ${val.harbor_validation.nop.reward}` : "n/a"}</b></div></div>
      <div class="bars">${bar("Diff-scoped AST mutation score", v.mutation_score)}${bar("Semantic (LLM) mutants caught", v.semantic_mutant_score)}</div>
      <h4>Gates</h4>${(v.gates || []).map((g) => `<div class="gate-row"><b>${esc(g.gate.replace(/_/g, " "))}</b><span class="badge ${esc(g.status)}">${esc(g.status)}</span><span>${esc(g.summary)}</span></div>`).join("")}
      ${score ? `<h4>Score breakdown</h4>${score.components.map((c) => `<div class="gate-row"><b>${esc(c.name)}</b><span>${Math.round(c.score * 100)}% × ${c.weight}</span><span class="sub">${esc(c.rule)}</span></div>`).join("")}<p class="sub">${esc(score.disclaimer)}</p>` : ""}
      ${sem && sem.outcomes.length ? `<h4>Semantic mutants</h4>${sem.outcomes.map((o) => `<div class="mutant"><header><span>${esc(o.description)}</span><span class="badge ${o.killed ? "passed" : "failed"}">${o.killed ? "caught" : "survived"}</span></header></div>`).join("")}` : ""}
      ${mut && mut.outcomes.length ? `<details><summary>AST mutants (${mut.killed}/${mut.total} killed)</summary>${mut.outcomes.map((o) => `<div class="mutant"><header><span><code>${esc(o.file)}:${o.line}</code> ${esc(o.operator)} · ${esc(o.description)}</span><span class="badge ${o.killed ? "passed" : "failed"}">${o.killed ? "killed" : "survived"}</span></header><pre class="code diff">${diffHtml(o.diff)}</pre></div>`).join("")}</details>` : ""}`;
    requestAnimationFrame(() => $$(".fill", body).forEach((f) => { f.style.width = f.dataset.w + "%"; }));
  }
}

async function openTask(repo, id) {
  try { current = await api(`/api/tasks/${encodeURIComponent(repo)}/${encodeURIComponent(id)}`); }
  catch (e) { alert(e.message); return; }
  const m = current.manifest;
  $("#drawer-title").textContent = m.title;
  $("#drawer-arch").textContent = (m.archetype || "").replace(/_/g, " ");
  $("#drawer-commit").textContent = `${m.repository.name} @ ${m.repository.starting_commit_sha}`;
  $("#drawer-download").href = `/api/tasks/${encodeURIComponent(repo)}/${encodeURIComponent(id)}/download`;
  $("#drawer").classList.remove("hidden");
  document.body.style.overflow = "hidden";
  renderTab("overview");
}
function closeDrawer() { $("#drawer").classList.add("hidden"); document.body.style.overflow = ""; }

/* ---------- boot ---------- */
document.addEventListener("DOMContentLoaded", () => {
  useOriginalLogos(); particles(); reveal(); loadStatus(); loadTasks();
  $("#analyze-btn").addEventListener("click", analyze);
  $("#forge-form").addEventListener("submit", forge);
  $$("[data-close]").forEach((el) => el.addEventListener("click", closeDrawer));
  $$("#tabs button").forEach((b) => b.addEventListener("click", () => renderTab(b.dataset.tab)));
  addEventListener("keydown", (e) => e.key === "Escape" && closeDrawer());
});
