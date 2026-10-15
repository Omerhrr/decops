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
