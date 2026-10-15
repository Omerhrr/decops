// Shared API types mirroring the backend response schemas (typed API clients -
// spec technology_stack.frontend.requirements)

export interface RoleBrief {
  id: string
  name: string
  description: string | null
}

export interface Me {
  id: string
  employee_code: string
  full_name: string
  email: string
  account_status: 'active' | 'disabled' | 'deactivated'
  last_login_at: string | null
  roles: RoleBrief[]
  permissions: string[]
}

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    details?: Record<string, unknown>
  }
}

export interface HealthResponse {
  status: string
  environment: string
  version: string
  database: string
}

export interface UserOut {
  id: string
  employee_code: string
  full_name: string
  email: string
  account_status: string
  last_login_at: string | null
  created_at: string
}

export interface UserPage {
  items: UserOut[]
  total: number
  page: number
  page_size: number
}

// ---------- Phase 3: administration ----------

export interface Permission {
  id: string
  code: string
  description: string | null
}

export interface Role {
  id: string
  name: string
  description: string | null
  is_system_role: boolean
  permissions: string[]
}

export interface RoleListPage {
  items: Role[]
  total: number
}

export interface Membership {
  department_id: string
  user_id: string
  membership_role: 'lead' | 'member'
  valid_from: string | null
  valid_until: string | null
}

export interface UserDetail {
  id: string
  employee_code: string
  full_name: string
  email: string
  account_status: 'active' | 'disabled' | 'deactivated'
  last_login_at: string | null
  created_at: string
  roles: RoleBrief[]
  memberships: Membership[]
}

export interface DepartmentMemberUser {
  id: string
  full_name: string
  email: string
  employee_code: string
  account_status: string
}

export interface DepartmentMembership {
  id: string
  user_id: string
  membership_role: 'lead' | 'member'
  valid_from: string | null
  valid_until: string | null
  user: DepartmentMemberUser | null
}

export interface Department {
  id: string
  name: string
  description: string | null
  status: 'active' | 'inactive'
  lead_user_id: string | null
  lead: DepartmentMemberUser | null
  member_count: number
}

export interface DepartmentDetail extends Department {
  memberships: DepartmentMembership[]
}

// ---------- Phase 4: task management ----------

export type TaskStatus =
  | 'draft'
  | 'open'
  | 'in_progress'
  | 'blocked'
  | 'under_review'
  | 'completed'
  | 'cancelled'
  | 'archived'

export type TaskPriority = 'low' | 'medium' | 'high' | 'critical'
export type VisibilityMode = 'private' | 'participants' | 'department_scoped' | 'custom'
export type AccessLevel = 'view' | 'operate' | 'manage' | 'denied'
export type AssignmentRole = 'accountable_pm' | 'supporting_pm' | 'work_item_assignee'

export interface TaskUserBrief {
  id: string
  full_name: string
  email: string
  employee_code: string
}

export interface TaskAssignment {
  id: string
  user_id: string
  user: TaskUserBrief
  assignment_role: AssignmentRole
  assigned_by_id: string
  assigned_at: string
  revoked_at: string | null
}

export interface TaskDepartmentLink {
  id: string
  department_id: string
  department_name: string | null
  participation_type: 'executing' | 'consulted' | 'informed'
}

export interface TaskAccessGrant {
  id: string
  principal_id: string
  principal: TaskUserBrief
  access_level: AccessLevel
  granted_by_id: string
  granted_at: string
  revoked_at: string | null
  revocation_reason: string | null
}

export interface Task {
  id: string
  task_number: string
  title: string
  priority: TaskPriority
  status: TaskStatus
  accountable_pm_id: string
  accountable_pm: TaskUserBrief | null
  start_date: string | null
  due_date: string | null
  next_follow_up_date: string | null
  percent_complete: number
  progress_mode: 'manual' | 'calculated'
  visibility_mode: VisibilityMode
  created_at: string
  department_names: string[]
}

export interface TaskDetail extends Task {
  description: string | null
  created_by_id: string
  dependency_summary: string | null
  version: number
  completed_at: string | null
  cancelled_at: string | null
  archived_at: string | null
  updated_at: string
  assignments: TaskAssignment[]
  task_departments: TaskDepartmentLink[]
  access_grants: TaskAccessGrant[]
}

export interface TaskPage {
  items: Task[]
  total: number
  page: number
  page_size: number
}

export interface TaskActivityEntry {
  id: string
  activity_type: string
  summary: string
  detail: Record<string, unknown> | null
  created_at: string
  actor: TaskUserBrief | null
}

export interface TransitionOptions {
  current_status: TaskStatus
  allowed_transitions: TaskStatus[]
}

// ---------- Phase 5: workflow engine ----------

export type StageStatus = 'pending' | 'in_progress' | 'completed' | 'cancelled'
export type WorkItemStatus = StageStatus
export type ExecutionMode = 'sequential' | 'parallel'
export type WorkItemType = 'milestone' | 'subtask'
export type ProgressBasis = 'all_items' | 'milestones_only' | 'subtasks_only'

export interface WorkflowStage {
  id: string
  task_id: string
  name: string
  description: string | null
  sequence_number: number
  execution_mode: ExecutionMode
  status: StageStatus
  weight: number
  progress_basis: ProgressBasis
  start_date: string | null
  due_date: string | null
  completed_at: string | null
}

export interface WorkItem {
  id: string
  task_id: string
  stage_id: string
  parent_work_item_id: string | null
  item_type: WorkItemType
  title: string
  description: string | null
  status: WorkItemStatus
  priority: string | null
  assigned_user_id: string | null
  assignee: TaskUserBrief | null
  sequence_number: number
  is_required: boolean
  weight: number
  start_date: string | null
  due_date: string | null
  completed_at: string | null
  version: number
}

export interface WorkflowDependency {
  id: string
  task_id: string
  predecessor_id: string
  successor_id: string
  note: string | null
}

export interface StageProgress {
  stage_id: string
  stage_name: string
  status: string
  weight: number
  included_item_count: number
  completed_item_count: number
  total_weight: number
  completed_weight: number
  percent: number
  excluded: Record<string, number>
  method: string
}

export interface WorkflowProgress {
  task_percent: number
  counted_item_total: number
  counted_item_completed: number
  method: string
  stages: StageProgress[]
}

export interface WorkflowBlocker {
  item_id: string
  blocked_by: string[]
}

export interface Workflow {
  task_id: string
  task_status: TaskStatus
  task_progress_mode: 'manual' | 'calculated'
  task_percent_complete: number
  calculated_percent: number
  stages: WorkflowStage[]
  items: WorkItem[]
  dependencies: WorkflowDependency[]
  blockers: WorkflowBlocker[]
  actionable_stage_ids: string[]
  progress: WorkflowProgress
}

export interface WorkflowTemplate {
  id: string
  name: string
  description: string | null
  definition: { stages: { name: string, execution_mode: string, weight: number, items: { item_type: string, title: string, is_required: boolean, weight: number }[] }[] }
  version: number
  is_active: boolean
  created_by_id: string
  created_at: string
  updated_at: string
}
