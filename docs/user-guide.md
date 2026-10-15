# DecOps User Guide

End-user documentation for the Interdec Operations Management System (DecOps).
Audience: all employees with an approved account. Administrator tasks (accounts,
imports, backups) are covered in `docs/admin-guide.md`.

## 1. Signing in

1. Open DecOps in your browser and navigate to the sign-in page.
2. Enter your Interdec email and your temporary password (issued by your
   administrator at launch), then choose **Sign in**.
3. **Rotate your temporary password immediately** - this is a launch security
   requirement. Contact your administrator if the sign-in page rejects an
   otherwise correct password five times; the account locks for 15 minutes
   after five failed attempts as a protection against guessing attacks.
4. Sessions last 12 hours. Use **Sign out** when leaving a shared workstation -
   signing out revokes the session immediately, not just the window.

If you forget your password, an administrator issues a new temporary password;
DecOps never emails passwords.

## 2. The layout

- **Sidebar (left)**: main navigation. It is collapsible - use the toggle at
  the sidebar edge to switch between the wide and the icon-only rail on
  desktop. On phones and narrow windows the sidebar becomes a drawer: tap the
  ☰ menu button in the top bar to open it, choose an item, and it closes
  automatically; tapping the shaded background also dismisses it.
- **Top bar**: mobile menu button, the notifications bell, and your account
  menu (sign out).
- **Entries appear per your permissions.** You will not see Tasks, Reports,
  Users, or Imports unless your role grants them - that is expected, not a
  malfunction.

## 3. Dashboard

The dashboard is the landing page and summarises what needs attention:

- **Stat cards** - counts relevant to you (for example assigned, blocked,
  overdue, due soon).
- **Management overview** (Management role) - cross-department totals that
  reconcile with the task register.
- **Upcoming deadlines** - active tasks due within the next days, nearest
  first.
- **Blocked tasks** - currently impeded work with reasons, so escalation is
  obvious.
- **Recent activity** - the latest audited changes on tasks you can see.

Everything on the dashboard is authorization-filtered: you only ever see data
you are entitled to see.

## 4. Working with tasks

### 4.1 Task register (Tasks)

The register lists authorized tasks with filtering (status, priority,
department, search) and pagination. Open a task to see its detail page.

### 4.2 Task detail

- **Fields**: title, description, priority, status, dates (start, due,
  follow-up, completion), accountable PM, assignments, visibility scope.
- **Activity** tab: the auditable history of the task (created, assigned,
  status changes with reasons).
- **Comments**: post updates; comments are part of the collaboration record.
- **Attachments**: upload reference documents (PDF, Office, images, zip; max
  25 MB). Attachments are task-scoped and private - only people authorized on
  the task can download them.

### 4.3 Lifecycle (Workflow panel)

Tasks move through the approved lifecycle:
`draft → open → in progress → under review → completed`, with `blocked`,
`cancelled`, and `archived` side states.

- Choose **Workflows / transition options** on a task to see which moves *you*
  can make right now.
- Moves into or out of **blocked**, **cancelled**, and **archived** require a
  **reason** - state the cause concisely; it is recorded permanently.
- If an action is missing, your role does not permit it (or the task state
  does not allow it) - ask the accountable PM or your lead.
- The **Gantt view** shows tasks on a timeline for schedule awareness.

### 4.4 My Tasks

Your personal worklist across all departments, with scope tabs (for example
*assigned to me* vs *delegated*). This is the fastest way to find what you owe.

## 5. Departments

Leads and members see their departments and the per-department **workspace**:
active tasks, deadlines, blocked/overdue lists, and team assignments.
Department visibility follows your membership - a lead sees workspaces for
departments they lead only.

## 6. Reports & exports (Management, Approvers)

- **Task completion** - created-vs-completed trends, totals, and milestone
  tracking.
- **Department workload** - distribution of open work per department.
- **CSV exports** - export the authorized data for offline analysis. Exports
  are permission-gated and audited; rows follow the same visibility rules as
  the screens (private tasks never appear, for anyone).

## 7. Notifications

The bell shows in-app notifications (assignments, deadline reminders, status
changes on your tasks). Deadline reminders are sent ahead of the due date and
de-duplicated so you are not spammed. Email delivery is switched off until
Interdec approves SMTP - notifications are in-app only for now.

## 8. Data migration awareness (legacy spreadsheet users)

The legacy planning spreadsheet is retired at launch. If you spot a task that
did not make it into DecOps, do **not** recreate it by hand - raise it with
your administrator so it can be imported through the Imports center with its
history, provenance, and duplicate checks intact. Imported tasks show their
legacy task ID (for example `DEC-2024-002`) on the task detail.

## 9. Quick reference

| I want to… | Where |
|---|---|
| See my work | My Tasks |
| Update status | Task → Workflows |
| Report an impediment | Task → move to *blocked* (reason required) |
| Share a document | Task → Attachments |
| Ask / answer questions | Task → Comments |
| Check a deadline | Dashboard → Upcoming deadlines |
| Export a report | Reports → CSV export |
| Get help | Support procedures (`docs/support-procedures.md`) |
