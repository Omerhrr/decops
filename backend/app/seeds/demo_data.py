"""Demo data for first launch: departments, staff accounts, and a realistic
task register so dashboards, charts, and PDF exports show meaningful data.
Every step is idempotent."""

DEMO_DEPARTMENTS = [
    ("Operations", "Day to day service operations and facilities coordination."),
    ("Engineering", "Internal systems, infrastructure, and integration work."),
    ("Finance", "Budgeting, procurement support, and financial reporting."),
]

# password for every demo account (change on first sign in)
DEMO_PASSWORD = "Interdec!2026"

DEMO_PEOPLE = [
    {
        "employee_code": "INT-0102",
        "full_name": "Amara Diallo",
        "email": "amara.diallo@interdec.com",
        "roles": ["Management"],
    },
    {
        "employee_code": "INT-0117",
        "full_name": "Tunde Bakare",
        "email": "tunde.bakare@interdec.com",
        "roles": ["Department Lead"],
        "department": {"name": "Operations", "lead": True},
    },
    {
        "employee_code": "INT-0121",
        "full_name": "Ngozi Eze",
        "email": "ngozi.eze@interdec.com",
        "roles": ["Accountable PM"],
        "department": {"name": "Engineering", "lead": True},
    },
    {
        "employee_code": "INT-0133",
        "full_name": "Sofia Mendes",
        "email": "sofia.mendes@interdec.com",
        "roles": ["Supporting PM", "Department Member"],
        "department": {"name": "Operations"},
    },
    {
        "employee_code": "INT-0140",
        "full_name": "Daniel Okafor",
        "email": "daniel.okafor@interdec.com",
        "roles": ["Department Member"],
        "department": {"name": "Engineering"},
    },
    {
        "employee_code": "INT-0151",
        "full_name": "Hauwa Bello",
        "email": "hauwa.bello@interdec.com",
        "roles": ["Approver"],
    },
]

# (title, description, department, assignee_email, priority,
#  created_days_ago, due_in_days, percent_complete)
DEMO_TASKS = [
    ("Quarterly fleet maintenance schedule", "Compile the maintenance calendar for all company vehicles and confirm workshop slots.", "Operations", "sofia.mendes@interdec.com", "medium", 12, 6, 55),
    ("Roll out VPN certificate rotation", "Replace expiring VPN certificates across staff laptops and verify connectivity.", "Engineering", "daniel.okafor@interdec.com", "high", 10, 3, 70),
    ("Close Q2 purchase order reconciliation", "Match outstanding purchase orders against invoices and flag variances above 2 percent.", "Finance", "amara.diallo@interdec.com", "high", 9, 2, 80),
    ("Office access badge audit", "Reconcile active badges against the current staff list and deactivate orphans.", "Operations", "tunde.bakare@interdec.com", "low", 8, 9, 30),
    ("Warehouse label printer replacement", "Procure and install two replacement label printers for the dispatch area.", "Operations", "sofia.mendes@interdec.com", "medium", 7, 14, 40),
    ("Restore nightly backup job", "Nightly database backups have failed since the storage migration; restore and verify.", "Engineering", "daniel.okafor@interdec.com", "critical", 6, 1, 65),
    ("Vendor contract renewal review", "Review the cleaning services contract terms ahead of the September renewal date.", "Finance", "amara.diallo@interdec.com", "medium", 6, 11, 45),
    ("Publish incident response playbook", "Finalize the incident response playbook and circulate for management approval.", "Engineering", "ngozi.eze@interdec.com", "high", 5, 4, 85),
    ("Onboarding checklist refresh", "Update the new starter checklist with the latest systems access steps.", "Operations", "tunde.bakare@interdec.com", "low", 5, 18, 20),
    ("Deprecate legacy file shares", "Migrate remaining project folders off the legacy share and archive them.", "Engineering", "daniel.okafor@interdec.com", "medium", 4, 21, 35),
    ("Monthly expense report submission", "Consolidate department expense claims for the monthly finance report.", "Finance", "amara.diallo@interdec.com", "medium", 4, -1, 90),
    ("Fire safety drill scheduling", "Coordinate with building management for the next quarterly fire drill.", "Operations", "sofia.mendes@interdec.com", "low", 3, 16, 15),
    ("Survey results dashboard mockup", "Draft the layout for the annual staff survey results dashboard.", "Operations", "ngozi.eze@interdec.com", "low", 2, 25, 10),
    ("Server patch management cycle", "Apply the latest security patches to production servers in the maintenance window.", "Engineering", "daniel.okafor@interdec.com", "critical", 2, 2, 50),
    ("Budget variance deep dive", "Analyze the engineering budget variance and prepare an explainer for management.", "Finance", "amara.diallo@interdec.com", "high", 1, 7, 25),
    ("Supplier onboarding form update", "Superseded by the new procurement workflow; work moved to the finance portal project.", "Finance", "hauwa.bello@interdec.com", "low", 3, 10, 0),
    ("Guest Wi-Fi capacity upgrade", "Assess and upgrade the guest network capacity for the upcoming open day.", "Engineering", "ngozi.eze@interdec.com", "medium", 1, 12, 5),
    ("Stationery stock count", "Run the quarterly stationery stock count and update the inventory sheet.", "Operations", "tunde.bakare@interdec.com", "low", 1, 5, 0),
]

# statuses assigned round robin; completed tasks also get completed_at
STATUS_CYCLE = [
    "completed", "in_progress", "open", "completed", "in_progress",
    "blocked", "under_review", "completed", "open", "in_progress",
    "completed", "open", "draft", "in_progress", "under_review",
    "cancelled", "open", "completed",
]
