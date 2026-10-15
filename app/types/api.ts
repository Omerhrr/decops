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
