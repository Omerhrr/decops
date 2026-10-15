"""PDF export service (WeasyPrint).

Renders authorized reports as professionally designed PDF documents. Every
visual aspect (paper, orientation, accent color, font, cover page, header,
footer, table style) comes from the stored PDF design settings, so the
organization controls its own document identity.

Documents are built from the same engine-visible task set as the on-screen
register and CSV exports, so restricted tasks cannot leak into a PDF.
"""

import html
from datetime import UTC, datetime

from weasyprint import HTML

PDF_FONT_STACKS = {
    "sans": "'DejaVu Sans', sans-serif",
    "serif": "'DejaVu Serif', serif",
    "mono": "'DejaVu Sans Mono', monospace",
}

_LOGO_MARK = (
    '<svg width="26" height="26" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg">'
    '<path d="M16 1.5 28.5 8.75v14.5L16 30.5 3.5 23.25V8.75Z" fill="{accent}"/>'
    '<path d="M12 9.5h5.2c4.4 0 7.3 2.6 7.3 6.5s-2.9 6.5-7.3 6.5H12Zm4.9 9.6c2.4 0 4-1.2 4-3.1s-1.6-3.1-4-3.1h-1.5v6.2Z" fill="#fff"/>'
    "</svg>"
)


def _esc(value) -> str:
    return html.escape("" if value is None else str(value))


def _paper_rule(design: dict) -> str:
    size = design["paper_size"]
    orientation = design["orientation"]
    if size == "Letter":
        w, h = "8.5in", "11in"
    else:
        w, h = "210mm", "297mm"
    if orientation == "landscape":
        w, h = h, w
    return f"@page {{ size: {w} {h}; margin: 20mm 16mm 18mm 16mm; }}"


def _table_css(design: dict) -> str:
    accent = design["accent_color"]
    style = design["table_style"]
    base = "th, td { padding: 5pt 7pt; text-align: left; vertical-align: top; }"
    if style == "striped":
        return base + (
            f"table {{ border-collapse: collapse; width: 100%; }}"
            f"thead th {{ background: {accent}; color: #ffffff; font-weight: bold; }}"
            f"tbody tr {{ border-bottom: 0.5pt solid #e2e8f0; }}"
            f"tbody tr:nth-child(even) {{ background: {accent}14; }}"
        )
    if style == "bordered":
        return base + (
            "table { border-collapse: collapse; width: 100%; }"
            "th, td { border: 0.6pt solid #cbd5e1; }"
            f"thead th {{ background: {accent}1a; color: #0f172a; font-weight: bold; }}"
        )
    return base + (
        "table { width: 100%; }"
        "thead th { border-bottom: 1.2pt solid #0f172a; font-weight: bold; }"
        "tbody tr { border-bottom: 0.4pt solid #f1f5f9; }"
    )


def _bar_chart_svg(series: list[dict], accent: str, *, key_a: str, key_b: str, label_a: str, label_b: str) -> str:
    width, height = 660, 190
    pad_l, pad_b, pad_t = 34, 26, 10
    n = max(len(series), 1)
    slot = (width - pad_l - 8) / n
    bar_w = slot * 0.32
    peak = max([max(s[key_a], s[key_b]) for s in series], default=1) or 1
    scale = (height - pad_b - pad_t) / peak
    bars = []
    for i, s in enumerate(series):
        x = pad_l + i * slot + slot * 0.5 - bar_w
        ha = max(s[key_a] * scale, s[key_a] > 0 and 1.5 or 0)
        hb = max(s[key_b] * scale, s[key_b] > 0 and 1.5 or 0)
        bars.append(
            f'<rect x="{x:.1f}" y="{height - pad_b - ha:.1f}" width="{bar_w:.1f}" height="{ha:.1f}" fill="{accent}" rx="2"/>'
            f'<rect x="{x + bar_w + 2:.1f}" y="{height - pad_b - hb:.1f}" width="{bar_w:.1f}" height="{hb:.1f}" fill="{accent}" fill-opacity="0.38" rx="2"/>'
            f'<text x="{x + bar_w + 1:.1f}" y="{height - pad_b + 12}" text-anchor="middle" font-size="7.5" fill="#64748b">{_esc(s.get("label", ""))}</text>'
        )
    legend_y = pad_t + 2
    legend = (
        f'<rect x="{pad_l}" y="{legend_y}" width="9" height="9" fill="{accent}" rx="2"/>'
        f'<text x="{pad_l + 13}" y="{legend_y + 8}" font-size="8" fill="#334155">{_esc(label_a)}</text>'
        f'<rect x="{pad_l + 90}" y="{legend_y}" width="9" height="9" fill="{accent}" fill-opacity="0.38" rx="2"/>'
        f'<text x="{pad_l + 103}" y="{legend_y + 8}" font-size="8" fill="#334155">{_esc(label_b)}</text>'
    )
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">'
        f'<line x1="{pad_l}" y1="{height - pad_b}" x2="{width - 6}" y2="{height - pad_b}" stroke="#cbd5e1" stroke-width="1"/>'
        + legend + "".join(bars) + "</svg>"
    )


def _cover_page(design: dict, org: dict, title: str, subtitle: str) -> str:
    accent = design["accent_color"]
    return f"""
    <div class="cover">
      <div class="cover-mark">{_LOGO_MARK.format(accent=accent)}</div>
      <p class="cover-org">{_esc(org.get("org_name"))}</p>
      <h1 class="cover-title">{_esc(title)}</h1>
      <p class="cover-subtitle">{_esc(subtitle)}</p>
      <div class="cover-rule"></div>
      <p class="cover-meta">Generated {datetime.now(UTC).strftime("%d %B %Y, %H:%M UTC")}</p>
    </div>
    <div style="page-break-after: always;"></div>
    """


def _header_footer(design: dict, org: dict, title: str) -> tuple[str, str]:
    accent = design["accent_color"]
    logo = f'<span class="hf-mark">{_LOGO_MARK.format(accent=accent)}</span>' if design["header_show_logo"] else ""
    org_name = f'<span class="hf-org">{_esc(org.get("org_name"))}</span>' if design["header_show_org_name"] else ""
    header = f'<div class="hf">{logo}{org_name}<span class="hf-title">{_esc(title)}</span></div>'
    page_numbers = (
        '<span class="hf-pages"><span class="page"></span> / <span class="pages"></span></span>'
        if design["show_page_numbers"] else ""
    )
    footer = (
        '<div class="hf footer">'
        f'<span>{_esc(design["footer_text"])}</span>'
        f"{page_numbers}"
        "</div>"
    )
    return header, footer


def _sections_html(sections: list[dict]) -> str:
    parts = []
    for section in sections:
        parts.append(f'<h2 class="section-title">{_esc(section["heading"])}</h2>')
        if section.get("paragraph"):
            parts.append(f'<p class="section-note">{_esc(section["paragraph"])}</p>')
        if section.get("metrics"):
            cells = "".join(
                f'<div class="metric"><p class="metric-value">{_esc(m["value"])}</p>'
                f'<p class="metric-label">{_esc(m["label"])}</p></div>'
                for m in section["metrics"]
            )
            parts.append(f'<div class="metrics">{cells}</div>')
        if section.get("chart_svg"):
            parts.append(f'<div class="chart">{section["chart_svg"]}</div>')
        table = section.get("table")
        if table:
            head = "".join(f"<th>{_esc(c)}</th>" for c in table["columns"])
            body = "".join(
                "<tr>" + "".join(f"<td>{_esc(cell)}</td>" for cell in row) + "</tr>"
                for row in table["rows"]
            )
            parts.append(f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>')
    return "".join(parts)


def render_pdf(
    design: dict,
    org: dict,
    *,
    title: str,
    subtitle: str,
    sections: list[dict],
    generated_by: str,
) -> bytes:
    accent = design["accent_color"]
    font = PDF_FONT_STACKS.get(design["font_family"], PDF_FONT_STACKS["sans"])
    header, footer = _header_footer(design, org, title)
    cover = _cover_page(design, org, title, subtitle) if design["show_cover_page"] else ""
    body = _sections_html(sections)
    css = f"""
    {_paper_rule(design)}
    body {{ font-family: {font}; font-size: {design["font_size_pt"]}pt; color: #0f172a; line-height: 1.45; }}
    @page {{
      @top-left {{ content: element(hf-top); }}
      @bottom-center {{ content: element(hf-bottom); }}
    }}
    .hf {{ position: hf-top; width: 100%; padding-bottom: 4pt; border-bottom: 0.6pt solid {accent}66;
           font-size: 8pt; color: #475569; }}
    .hf.footer {{ position: hf-bottom; border-bottom: none; border-top: 0.6pt solid {accent}66;
                  padding-top: 4pt; display: flex; justify-content: space-between; width: 100%; }}
    .hf-pages {{ color: #64748b; }}
    .hf-mark svg {{ vertical-align: -6pt; }}
    .hf-org {{ font-weight: bold; color: {accent}; margin-left: 4pt; }}
    .hf-title {{ float: right; }}
    .cover {{ padding-top: 70mm; text-align: left; }}
    .cover-mark svg {{ width: 52px; height: 52px; }}
    .cover-org {{ font-size: 11pt; font-weight: bold; color: {accent}; margin: 10pt 0 26pt; letter-spacing: 1.5pt; text-transform: uppercase; }}
    .cover-title {{ font-size: 26pt; font-weight: bold; margin: 0; color: #0f172a; }}
    .cover-subtitle {{ font-size: 12pt; color: #475569; margin: 8pt 0 0; }}
    .cover-rule {{ width: 46pt; border-bottom: 2.5pt solid {accent}; margin: 18pt 0; }}
    .cover-meta {{ font-size: 9pt; color: #64748b; }}
    .doc-header {{ font-size: 8pt; color: #64748b; margin-bottom: 10pt; }}
    .section-title {{ font-size: 13pt; font-weight: bold; color: {accent}; margin: 16pt 0 6pt; }}
    .section-note {{ font-size: 9pt; color: #475569; margin: 0 0 8pt; }}
    .metrics {{ display: flex; gap: 8pt; margin: 8pt 0 4pt; }}
    .metric {{ flex: 1; border: 0.6pt solid #e2e8f0; border-top: 2.5pt solid {accent};
               border-radius: 3pt; padding: 7pt 9pt; }}
    .metric-value {{ font-size: 15pt; font-weight: bold; margin: 0; color: #0f172a; }}
    .metric-label {{ font-size: 7.5pt; text-transform: uppercase; letter-spacing: 0.6pt; color: #64748b; margin: 2pt 0 0; }}
    .chart {{ margin: 10pt 0; }}
    table {{ margin: 6pt 0 2pt; font-size: {max(design["font_size_pt"] - 0.5, 6.5)}pt; }}
    {_table_css(design)}
    """
    document = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{css}</style></head>
<body>
<header>{header}</header>
{cover}
<p class="doc-header">Prepared for {_esc(generated_by)} on {datetime.now(UTC).strftime("%d %B %Y")}</p>
<main>{body}</main>
<footer>{footer}</footer>
</body></html>"""
    return HTML(string=document).write_pdf()


# ---------------------------------------------------------------------------
# Report builders (authorized sets only)
# ---------------------------------------------------------------------------

def task_register_pdf(
    db, actor, org: dict, design: dict, *, rows: list[dict], row_count: int,
) -> bytes:
    today = datetime.now(UTC).date().isoformat()
    sections = [{
        "heading": "Task register",
        "paragraph": f"{row_count} task(s) you are authorized to view, exported on {today}.",
        "metrics": [],
        "table": {
            "columns": ["Task", "Title", "Status", "Priority", "Accountable PM", "Due", "%"],
            "rows": [
                [
                    r["task_number"], r["title"], r["status"], r["priority"],
                    r["accountable_pm"], r["due_date"], r["percent_complete"],
                ]
                for r in rows
            ],
        },
    }]
    return render_pdf(
        design, org,
        title="Task Register Report",
        subtitle="Authorized task records with lifecycle status",
        sections=sections,
        generated_by=actor.full_name,
    )


def task_completion_pdf(db, actor, org: dict, design: dict, report: dict) -> bytes:
    totals = report["totals"]
    series = report["series"]
    chart_series = [
        {"label": s["week_start"].strftime("%d %b"), "created": s["created"], "completed": s["completed"]}
        for s in series
    ]
    sections = [
        {
            "heading": "Overview",
            "metrics": [
                {"label": "Visible tasks", "value": totals["visible_total"]},
                {"label": "Active", "value": totals["active"]},
                {"label": "Completed", "value": totals["completed"]},
                {"label": "Overdue", "value": totals["overdue"]},
                {"label": "Avg days to complete", "value": report["avg_days_to_complete"] if report["avg_days_to_complete"] is not None else "-"},
            ],
        },
        {
            "heading": "Weekly throughput",
            "paragraph": f"Tasks created versus completed over the last {report['weeks']} weeks.",
            "chart_svg": _bar_chart_svg(
                chart_series, design["accent_color"],
                key_a="completed", key_b="created", label_a="Completed", label_b="Created",
            ),
            "table": {
                "columns": ["Week starting", "Completed", "Created"],
                "rows": [[s["week_start"].isoformat(), s["completed"], s["created"]] for s in series],
            },
        },
        {
            "heading": "Blocker analysis",
            "paragraph": "Where currently blocked work concentrates.",
            "table": {
                "columns": ["Blocked by priority", "Tasks", "Blocked by department", "Tasks"],
                "rows": _blocker_rows(report),
            },
        },
    ]
    return render_pdf(
        design, org,
        title="Task Completion Report",
        subtitle=f"{report['weeks']}-week delivery trend and blockers",
        sections=sections,
        generated_by=actor.full_name,
    )


def _blocker_rows(report: dict) -> list[list[str]]:
    ba = report["blocker_analysis"]
    by_priority = sorted(ba["by_priority"].items(), key=lambda kv: -kv[1])
    by_department = sorted(ba["by_department"].items(), key=lambda kv: -kv[1])
    length = max(len(by_priority), len(by_department), 1)
    rows = []
    for i in range(length):
        left = by_priority[i] if i < len(by_priority) else ("", "")
        right = by_department[i] if i < len(by_department) else ("", "")
        rows.append([left[0], left[1], right[0], right[1]])
    if ba["blocked_total"] == 0:
        rows = [["No blocked tasks", "", "", ""]]
    return rows


def department_workload_pdf(db, actor, org: dict, design: dict, report: dict) -> bytes:
    rows = report["departments"]
    scope_note = (
        "All departments." if report["scope"] == "all"
        else "Departments you lead or belong to."
    )
    sections = [{
        "heading": "Department workload",
        "paragraph": scope_note,
        "table": {
            "columns": ["Department", "Lead", "Members", "Active", "Overdue", "Blocked", "Completed", "Open assignments"],
            "rows": [
                [
                    r["department_name"], r["lead"] or "", r["member_count"],
                    r["active_tasks"], r["overdue_tasks"], r["blocked_tasks"],
                    r["completed_tasks"], r["open_assignments"],
                ]
                for r in rows
            ],
        },
    }]
    return render_pdf(
        design, org,
        title="Department Workload Report",
        subtitle="Capacity, delivery and blockers per department",
        sections=sections,
        generated_by=actor.full_name,
    )
