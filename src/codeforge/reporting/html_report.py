"""Self-contained static HTML report for a run (no external assets), for judges to open
directly from the reports/ folder."""

from __future__ import annotations

import html
from pathlib import Path

STATUS_COLORS = {"passed": "#22c55e", "valid": "#22c55e", "warning": "#f59e0b",
                 "failed": "#ef4444", "rejected": "#ef4444", "unsupported": "#94a3b8",
                 "skipped": "#94a3b8"}


def _badge(status: str) -> str:
    color = STATUS_COLORS.get(status, "#94a3b8")
    return (f'<span style="background:{color}22;color:{color};border:1px solid {color}55;'
            f'padding:2px 8px;border-radius:999px;font-size:12px">{html.escape(status)}</span>')


def write_html_report(run_dir: Path, summary: dict) -> Path:
    e = html.escape
    repo = summary.get("repository") or {}
    rows = []
    for t in summary.get("tasks", []):
        gates = "".join(f"<li>{_badge(g['status'])} <b>{e(g['gate'])}</b> — {e(g['summary'])}"
                        f"</li>" for g in t.get("gates", []))
        reasons = "".join(f"<li>{e(r)}</li>" for r in t.get("reasons", []))
        rows.append(f"""<section class="card"><h2>{e(t['title'])} {_badge(t['status'])}</h2>
<p class="muted">{e(t['task_id'])} · {e(t['archetype'])} · validity score
<b>{t.get('score')}</b></p><ul class="gates">{gates}</ul>
{'<h3>Rejection reasons</h3><ul>' + reasons + '</ul>' if reasons else ''}</section>""")
    var = summary.get("variation") or {}
    matrix = summary.get("discrimination_matrix")
    mtable = ""
    if matrix:
        head = "".join(f"<th>ref {j + 1}</th>" for j in range(len(matrix["tasks"])))
        body = "".join(
            f"<tr><th>tests {i + 1}</th>" + "".join(
                f'<td style="color:{"#22c55e" if c == "pass" else "#ef4444"}">{c}</td>'
                for c in row) + "</tr>" for i, row in enumerate(matrix["cells"]))
        mtable = (f"<h3>Cross-task discrimination matrix</h3><table>"
                  f"<tr><th></th>{head}</tr>{body}</table><p class='muted'>Off-diagonal "
                  f"failing: {matrix['off_diagonal_fail']}/{matrix['off_diagonal_total']}</p>")
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CodeForge Run Report</title><style>
body{{margin:0;background:#050816;color:#e2e8f0;font:15px/1.5 system-ui,sans-serif}}
main{{max-width:960px;margin:0 auto;padding:32px 16px}}
h1{{background:linear-gradient(90deg,#22d3ee,#6366f1,#a855f7);-webkit-background-clip:text;
color:transparent;margin:0 0 4px}}
.card{{background:#0b1024;border:1px solid #1e293b;border-radius:16px;padding:20px;
margin:16px 0}}.muted{{color:#94a3b8}}ul.gates{{list-style:none;padding:0}}
ul.gates li{{margin:6px 0}}table{{border-collapse:collapse}}td,th{{border:1px solid #1e293b;
padding:6px 10px;text-align:center}}code{{color:#a5b4fc}}</style></head><body><main>
<h1>CodeForge AI — Run Report</h1>
<p class="muted">Team TECH TITAN · Shivang Saxena &amp; Rani Malviya</p>
<section class="card"><p>Repository <code>{e(str(repo.get('url', '')))}</code><br>
Commit <code>{e(str(repo.get('commit', '')))}</code> · {e(str(repo.get('language', '')))}
· tests: {e(str(repo.get('test_framework', '')))}</p>
<p>Status {_badge(summary.get('status', ''))} · valid tasks <b>{summary.get('accepted')}</b> ·
rejected <b>{summary.get('rejected')}</b> · distinct archetypes
<b>{var.get('distinct_archetypes', 0)}</b> · diversity score
<b>{var.get('diversity_score')}</b></p>{mtable}</section>
{''.join(rows)}
<p class="muted">Every status above comes from executed tests and Harbor trials.
See summary.json and each task's validation.json for raw evidence.</p></main></body></html>"""
    path = run_dir / "report.html"
    path.write_text(doc, encoding="utf-8")
    return path
