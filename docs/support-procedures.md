# DecOps Support & Incident Procedures

Support model, incident handling, and the feedback loop for DecOps at
Interdec. Complements `docs/runbook.md` (infrastructure operations),
`docs/admin-guide.md` (administrator duties), and
`docs/reports/phase10_launch_report.md` (launch record).

## 1. Support model

| Tier | Who | Handles | Target response |
|---|---|---|---|
| L1 — Floor support | Nominated super-users per department | Sign-in trouble, "how do I…", navigation, blocked-task questions | Same business day |
| L2 — Administration | Company Administrator | Account/role changes, password resets, import corrections, permission questions | 4 business hours |
| L3 — Engineering | DecOps maintainers | Defects, data corrections needing code/SQL, performance, security events | 1 business day (sev-1: immediate) |

Escalation path: user → L1 → L2 → L3. The Company Administrator owns the
relationship with L3 and files defects (§5). Out of hours: sev-1 only (§3).

## 2. Request intake

All requests land in the support log (`docs/launch/feedback_log.csv` fields —
captured_on, raised_by, role, area, summary, detail, source,
priority_suggested, status). Sources: walk-ups, email to the DecOps
administrator inbox, and items surfaced by the daily monitor report.

Minimum record for every request: date, requester, role, area (screen/feature),
one-line summary, detail, and the `request_id` from the UI error banner when
the request is about a failure — the `x-request-id` response header value is
correlation gold for L3 (it links web request → server log → audit row).

## 3. Incident handling

### 3.1 Severity

| Sev | Definition | Examples | Action |
|---|---|---|---|
| Sev-1 | Service down or data at risk | API unhealthy, DB unreachable, suspected data corruption, suspected breach | Immediate: runbook §8 triage; notify L3; consider read-only freeze |
| Sev-2 | Major function broken, workaround exists | Sign-in broken for one role, imports failing, notifications stalled | Same day; L2 + L3 |
| Sev-3 | Minor/cosmetic, no data risk | Wrong sort order, label typo, slow report | Normal backlog |

### 3.2 Playbook (summary; full version: runbook §8)

1. **Triage** — `GET /api/v1/health`, structured logs (`request_id`
   correlation), audit events for blast radius. The launch monitor
   (`scripts/monitor_phase10.py`) prints health, adoption, outbox backlog,
   and security alerts in one view.
2. **Suspected data issue** — freeze writes (read-only mode at the proxy),
   restore a backup into staging, compare, then decide on cutover. Never
   patch production data ad hoc during business hours without a record.
3. **Suspected security event** — revoke sessions, rotate
   `DECOPS_SESSION_SECRET_KEY` (invalidates all tokens), force password
   resets, preserve `audit_events` (append-only) for forensics.
4. **Import mishap** — imports are staged; a committed import is audited with
   per-row task IDs (`import_jobs.committed_task_ids`) enabling surgical
   rollback of exactly the imported tasks.
5. **Post-incident** — one-page timeline (detection → mitigation → recovery)
   from logs + audit, filed with the defect, plus a preventive action.

### 3.3 Communication

Sev-1: immediate note to all users (banner/email) with expected resolution
updates every 30 minutes. Sev-2: affected departments the same day. Every
incident closes with a user-visible summary — trust is the product.

## 4. Feedback collection & prioritization (launch objective)

**Collect**: every L1/L2 interaction that is not a pure how-to goes into the
feedback log. Weekly, the administrator walks the log with Management and
prioritizes.

**Prioritize** — impact × reach, validated against the spec's intent:

| Priority | Meaning | Example |
|---|---|---|
| Must have | Blocks a core workflow or an exit criterion | "Leads cannot see their department's blocked tasks" |
| Should have | Clear friction, workaround painful | "Deadline reminders arrive too early" |
| Could have | Nice-to-have polish | "Add saved filters on the register" |
| Won't have (now) | Out of scope for launch | Mobile native app, email digests |

Rules of thumb: anything that contradicts the approved role matrix or the task
lifecycle is a defect, not feedback; feedback that would require changing
audit semantics or RBAC goes to Interdec process owners before engineering.

**Act**: accepted items get an owner and a target release in the log
(`decision`, `decision_on`, `assigned_to`, `release_target`); status moves
`new → triaged → accepted/rejected → delivered`. Review the delivered set in
the next weekly walk — the loop closes when the requester confirms.

## 5. Defect filing (L2 → L3)

A defect report contains: severity (§3.1), environment (`DECOPS_ENVIRONMENT`,
release/tag), a reproduction path with the exact request/response where
possible, the `request_id`, audit excerpts for data-affecting defects, and
expected-vs-actual. L3 reproduces against the failing release; fixes land via
the standard release procedure (runbook §3) — never hot edits on production.

## 6. Post-launch stabilization (first two weeks)

- Daily monitor snapshot (adoption: distinct logins, actions per day;
  delivery: outbox backlog; security: failed-login bursts) — keep the JSON
  snapshots; they are the usage baseline for the 30-day review.
- Weekly feedback walk (§4) with the log reviewed item by item.
- Watch the register for hand-made duplicates of imported tasks (§8 of the
  user guide) and merge through a documented data-fix, not silent deletes.
- After two stable weeks and Interdec's rollout acceptance, switch the
  cadence: monitor weekly, feedback walk bi-weekly, and schedule the 30-day
  review against the Phase 10 exit criteria.
