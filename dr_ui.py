"""Tiny web UI for inspecting the Deep Research workspace DB live.

Run:
    python dr_ui.py
    # then open http://localhost:8765

Auto-refreshes every 2s. Read-only — never writes to the DB.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from deep_research.config import CONFIG
from deep_research.workspace import init_db, snapshot

app = FastAPI(title="Deep Research Workspace UI")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(CONFIG.workspace_db)
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/api/projects")
def list_projects() -> JSONResponse:
    init_db()
    with _conn() as c:
        rows = c.execute(
            """
            SELECT p.project_id, p.brief_json, p.round_number, p.created_at,
                   p.final_report IS NOT NULL AS has_final,
                   p.report_draft IS NOT NULL AS has_draft,
                   (SELECT COUNT(*) FROM findings  f WHERE f.project_id = p.project_id) AS n_findings,
                   (SELECT COUNT(*) FROM critiques cq WHERE cq.project_id = p.project_id) AS n_critiques
            FROM projects p
            ORDER BY p.created_at DESC
            """
        ).fetchall()

    out = []
    for r in rows:
        title = ""
        question = ""
        if r["brief_json"]:
            try:
                b = json.loads(r["brief_json"])
                title = b.get("title", "")
                question = b.get("research_question", "")
            except Exception:
                pass
        out.append({
            "project_id": r["project_id"],
            "title": title,
            "question": question,
            "round": r["round_number"] or 0,
            "created_at": r["created_at"],
            "n_findings": r["n_findings"],
            "n_critiques": r["n_critiques"],
            "has_draft": bool(r["has_draft"]),
            "has_final": bool(r["has_final"]),
        })
    return JSONResponse(out)


@app.get("/api/projects/{project_id}")
def project_detail(project_id: str) -> JSONResponse:
    try:
        snap = snapshot(project_id)
    except ValueError:
        raise HTTPException(404, f"No project {project_id}")

    # Include per-subquestion latest critique for easy UI rendering
    plan = snap.plan.model_dump() if snap.plan else None
    findings_by_sq = {f.sub_question_id: f.model_dump() for f in snap.findings}
    critiques_by_sq = {c.sub_question_id: c.model_dump() for c in snap.critiques}

    # Also fetch full history of findings/critiques so user can scroll rounds
    with _conn() as c:
        f_hist = c.execute(
            "SELECT round_number, sub_question_id, finding_json "
            "FROM findings WHERE project_id = ? ORDER BY id ASC",
            (project_id,),
        ).fetchall()
        c_hist = c.execute(
            "SELECT round_number, sub_question_id, critique_json "
            "FROM critiques WHERE project_id = ? ORDER BY id ASC",
            (project_id,),
        ).fetchall()

    return JSONResponse({
        "project_id": snap.project_id,
        "brief": snap.brief.model_dump() if snap.brief else None,
        "plan": plan,
        "round_number": snap.round_number,
        "findings_by_sq": findings_by_sq,
        "critiques_by_sq": critiques_by_sq,
        "findings_history": [
            {"round": r["round_number"], "sq": r["sub_question_id"], "finding": json.loads(r["finding_json"])}
            for r in f_hist
        ],
        "critiques_history": [
            {"round": r["round_number"], "sq": r["sub_question_id"], "critique": json.loads(r["critique_json"])}
            for r in c_hist
        ],
        "report_draft": snap.report_draft,
        "final_report": snap.final_report,
    })


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Deep Research — Workspace</title>
<style>
  :root {
    --bg: #0d1117; --panel: #161b22; --border: #30363d;
    --text: #c9d1d9; --muted: #8b949e; --accent: #58a6ff;
    --good: #3fb950; --bad: #f85149; --warn: #d29922;
  }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
         background: var(--bg); color: var(--text); font-size: 13px; }
  header { padding: 10px 16px; background: var(--panel); border-bottom: 1px solid var(--border);
           display: flex; align-items: center; gap: 12px; }
  header h1 { font-size: 14px; margin: 0; }
  header .status { color: var(--muted); margin-left: auto; }
  main { display: grid; grid-template-columns: 320px 1fr; height: calc(100vh - 42px); }
  #projects { border-right: 1px solid var(--border); overflow-y: auto; background: var(--panel); }
  .proj { padding: 10px 12px; border-bottom: 1px solid var(--border); cursor: pointer; }
  .proj:hover { background: #1f2630; }
  .proj.active { background: #1f2937; border-left: 3px solid var(--accent); }
  .proj .title { font-weight: 600; color: var(--text); }
  .proj .meta { color: var(--muted); font-size: 11px; margin-top: 4px; }
  .badge { display: inline-block; padding: 1px 6px; border-radius: 8px;
           font-size: 10px; background: #21262d; color: var(--muted); margin-right: 4px; }
  .badge.final { background: #033a16; color: var(--good); }
  .badge.draft { background: #3a2c03; color: var(--warn); }
  #detail { overflow-y: auto; padding: 16px 22px; }
  #detail h2 { font-size: 15px; margin: 18px 0 8px; color: var(--accent);
               border-bottom: 1px solid var(--border); padding-bottom: 4px; }
  #detail h3 { font-size: 13px; margin: 12px 0 6px; color: var(--text); }
  .card { background: var(--panel); border: 1px solid var(--border); border-radius: 6px;
          padding: 10px 12px; margin: 8px 0; }
  .sq { border-left: 3px solid var(--muted); }
  .sq.done      { border-left-color: var(--good); }
  .sq.pending   { border-left-color: var(--muted); }
  .sq.in_progress { border-left-color: var(--accent); }
  .sq.insufficient { border-left-color: var(--bad); }
  .pill { display: inline-block; padding: 1px 6px; border-radius: 8px; font-size: 10px;
          background: #21262d; color: var(--muted); margin-left: 6px; }
  .pill.good { background: #033a16; color: var(--good); }
  .pill.bad  { background: #3d0d0d; color: var(--bad); }
  .pill.warn { background: #3a2c03; color: var(--warn); }
  .src { font-size: 11px; color: var(--muted); margin: 2px 0; }
  .src a { color: var(--accent); text-decoration: none; }
  .src a:hover { text-decoration: underline; }
  pre { white-space: pre-wrap; word-break: break-word; background: #010409;
        border: 1px solid var(--border); border-radius: 4px; padding: 8px; font-size: 12px;
        max-height: 400px; overflow-y: auto; }
  .empty { color: var(--muted); padding: 40px; text-align: center; }
  .muted { color: var(--muted); }
  .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  label.toggle { color: var(--muted); cursor: pointer; user-select: none; }
  label.toggle input { vertical-align: middle; }
</style>
</head>
<body>
<header>
  <h1>📊 Deep Research — Workspace</h1>
  <label class="toggle"><input type="checkbox" id="autoRefresh" checked /> auto-refresh 2s</label>
  <span class="status" id="status">—</span>
</header>
<main>
  <aside id="projects"></aside>
  <section id="detail"><div class="empty">Select a project on the left.</div></section>
</main>

<script>
let selectedProjectId = null;
let lastDetailJson = "";

function tierLabel(t) {
  return ({1:"peer-reviewed",2:"official",3:"major-news",4:"industry",5:"unverified"})[t] || ("tier "+t);
}
function tierPill(t) {
  const cls = t <= 2 ? "good" : t === 3 ? "" : t === 4 ? "warn" : "bad";
  return `<span class="pill ${cls}">${tierLabel(t)}</span>`;
}

async function loadProjects() {
  try {
    const r = await fetch("/api/projects");
    const projects = await r.json();
    const aside = document.getElementById("projects");
    if (projects.length === 0) {
      aside.innerHTML = `<div class="empty">No projects yet. Run <code>python run_local.py "..."</code></div>`;
      return;
    }
    aside.innerHTML = projects.map(p => `
      <div class="proj ${p.project_id === selectedProjectId ? 'active' : ''}" data-id="${p.project_id}">
        <div class="title">${escapeHtml(p.title || "(untitled)")}</div>
        <div class="muted" style="font-size:11px;margin-top:2px">${escapeHtml(p.question || "").slice(0,80)}</div>
        <div class="meta">
          <span class="badge">id:${p.project_id}</span>
          <span class="badge">round ${p.round}</span>
          <span class="badge">${p.n_findings}f / ${p.n_critiques}c</span>
          ${p.has_final ? '<span class="badge final">final</span>'
            : p.has_draft ? '<span class="badge draft">draft</span>' : ''}
          <div style="margin-top:3px">${p.created_at}</div>
        </div>
      </div>
    `).join("");
    aside.querySelectorAll(".proj").forEach(el => {
      el.addEventListener("click", () => {
        selectedProjectId = el.dataset.id;
        lastDetailJson = "";
        loadProjects();
        loadDetail();
      });
    });
    setStatus(`${projects.length} project(s) • ${new Date().toLocaleTimeString()}`);
  } catch (e) { setStatus("error: " + e.message); }
}

async function loadDetail() {
  if (!selectedProjectId) return;
  try {
    const r = await fetch("/api/projects/" + selectedProjectId);
    if (!r.ok) { document.getElementById("detail").innerHTML = `<div class="empty">${r.status}</div>`; return; }
    const text = await r.text();
    if (text === lastDetailJson) return; // no change, don't re-render
    lastDetailJson = text;
    const d = JSON.parse(text);
    renderDetail(d);
  } catch (e) { setStatus("error: " + e.message); }
}

function renderDetail(d) {
  const parts = [];
  parts.push(`<div class="row"><h2 style="margin:0;border:none">${escapeHtml(d.brief?.title || "(no brief yet)")}</h2>
    <span class="pill">id ${d.project_id}</span>
    <span class="pill">round ${d.round_number}</span></div>`);

  if (d.brief) {
    parts.push(`<div class="card">
      <div><strong>Question:</strong> ${escapeHtml(d.brief.research_question)}</div>
      <div class="muted">Audience: ${escapeHtml(d.brief.audience)} • Depth: ${escapeHtml(d.brief.desired_depth)}</div>
      ${d.brief.constraints?.length ? `<div class="muted">Constraints: ${d.brief.constraints.map(escapeHtml).join("; ")}</div>` : ""}
    </div>`);
  }

  // Plan + sub-questions with status + per-sq finding/critique
  if (d.plan) {
    parts.push(`<h2>Plan</h2>`);
    parts.push(`<div class="card"><div><strong>Restated:</strong> ${escapeHtml(d.plan.brief_restated)}</div>
      <div style="margin-top:6px"><strong>Objectives:</strong><ul style="margin:4px 0 0 18px">
      ${d.plan.objectives.map(o => `<li>${escapeHtml(o)}</li>`).join("")}</ul></div>
      <div style="margin-top:6px"><strong>Success criteria:</strong><ul style="margin:4px 0 0 18px">
      ${d.plan.success_criteria.map(o => `<li>${escapeHtml(o)}</li>`).join("")}</ul></div>
    </div>`);

    parts.push(`<h2>Sub-questions (${d.plan.sub_questions.length})</h2>`);
    for (const sq of d.plan.sub_questions) {
      const f = d.findings_by_sq[sq.id];
      const c = d.critiques_by_sq[sq.id];
      const statusPill = `<span class="pill ${
        sq.status === 'done' ? 'good' :
        sq.status === 'insufficient' ? 'bad' :
        sq.status === 'in_progress' ? 'warn' : ''}">${sq.status}</span>`;
      parts.push(`<div class="card sq ${sq.status}">
        <div><strong>${escapeHtml(sq.question)}</strong> ${statusPill}
          <span class="pill">prio ${sq.priority}</span>
          <span class="pill">id ${sq.id}</span></div>
        <div class="muted" style="margin-top:4px">${escapeHtml(sq.rationale)}</div>
        ${sq.expected_source_types?.length
          ? `<div class="muted" style="margin-top:2px">Expected: ${sq.expected_source_types.map(escapeHtml).join(", ")}</div>`
          : ""}
        ${f ? renderFinding(f) : '<div class="muted" style="margin-top:6px">No finding yet.</div>'}
        ${c ? renderCritique(c) : ""}
      </div>`);
    }
  } else {
    parts.push(`<div class="empty">Planner has not produced a plan yet.</div>`);
  }

  // History
  if (d.findings_history.length > 1 || d.critiques_history.length > 0) {
    parts.push(`<h2>History</h2>`);
    parts.push(`<div class="muted">Findings: ${d.findings_history.length} • Critiques: ${d.critiques_history.length}</div>`);
  }

  if (d.final_report) {
    parts.push(`<h2>Final report</h2><pre>${escapeHtml(d.final_report)}</pre>`);
  } else if (d.report_draft) {
    parts.push(`<h2>Draft report</h2><pre>${escapeHtml(d.report_draft)}</pre>`);
  }

  document.getElementById("detail").innerHTML = parts.join("");
}

function renderFinding(f) {
  const conf = Math.round((f.confidence || 0) * 100);
  const confCls = conf >= 70 ? "good" : conf >= 40 ? "warn" : "bad";
  return `<div style="margin-top:8px"><h3>Finding <span class="pill ${confCls}">conf ${conf}%</span></h3>
    <div>${escapeHtml(f.answer)}</div>
    ${f.key_facts?.length ? `<div style="margin-top:6px"><strong>Key facts:</strong><ul style="margin:4px 0 0 18px">
      ${f.key_facts.map(k => `<li>${escapeHtml(k)}</li>`).join("")}</ul></div>` : ""}
    ${f.sources?.length ? `<div style="margin-top:6px"><strong>Sources (${f.sources.length}):</strong>
      ${f.sources.map(s => `<div class="src">${tierPill(s.tier)} <a href="${escapeHtml(s.url)}" target="_blank">${escapeHtml(s.title || s.url)}</a></div>`).join("")}
    </div>` : ""}
    ${f.open_questions?.length ? `<div style="margin-top:6px" class="muted"><strong>Open:</strong> ${f.open_questions.map(escapeHtml).join("; ")}</div>` : ""}
  </div>`;
}

function renderCritique(c) {
  const score = Math.round((c.score || 0) * 100);
  const acceptPill = c.accept ? '<span class="pill good">accepted</span>' : '<span class="pill bad">rejected</span>';
  return `<div style="margin-top:8px"><h3>Critic ${acceptPill} <span class="pill">score ${score}%</span></h3>
    <div class="row">
      <span class="pill ${c.answers_question?'good':'bad'}">answers</span>
      <span class="pill ${c.sufficient_sources?'good':'bad'}">sources</span>
      <span class="pill ${c.source_tier_ok?'good':'bad'}">tier</span>
    </div>
    ${c.issues?.length ? `<ul style="margin:6px 0 0 18px">${c.issues.map(i => `<li>${escapeHtml(i)}</li>`).join("")}</ul>` : ""}
  </div>`;
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, ch => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
}
function setStatus(s) { document.getElementById("status").textContent = s; }

loadProjects();
setInterval(() => {
  if (!document.getElementById("autoRefresh").checked) return;
  loadProjects();
  loadDetail();
}, 2000);
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML


if __name__ == "__main__":
    db = Path(CONFIG.workspace_db).resolve()
    print(f"Deep Research UI — reading {db}")
    print("Open http://localhost:8765")
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
