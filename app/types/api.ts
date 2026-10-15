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
