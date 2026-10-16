// Single source of truth for display helpers. Status and priority tones mirror
// the dashboard donut palette so every surface colors a state the same way.

export type BadgeTone = 'green' | 'amber' | 'blue' | 'violet' | 'gray' | 'rose'

const STATUS_TONES: Record<string, BadgeTone> = {
  draft: 'gray',
  open: 'blue',
  in_progress: 'amber',
  under_review: 'violet',
  completed: 'green',
  blocked: 'rose',
  cancelled: 'gray',
  archived: 'gray',
  pending: 'gray',
}

const PRIORITY_TONES: Record<string, BadgeTone> = {
  low: 'gray',
  medium: 'blue',
  high: 'amber',
  critical: 'rose',
}

const TERMINAL_STATUSES = ['completed', 'cancelled', 'archived']

export function statusTone(status: string): BadgeTone {
  return STATUS_TONES[status] ?? 'gray'
}

export function priorityTone(priority: string): BadgeTone {
  return PRIORITY_TONES[priority] ?? 'gray'
}

export function statusLabel(status: string): string {
  return status.replaceAll('_', ' ')
}

const VISIBILITY_LABELS: Record<string, string> = {
  private: 'Private',
  participants: 'Participants only',
  department_scoped: 'Shared with departments',
  custom: 'Custom access',
}

export function visibilityLabel(mode: string): string {
  return VISIBILITY_LABELS[mode] ?? mode.replaceAll('_', ' ')
}

export function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1)
}

export function isOverdue(dueDate: string | null | undefined, status: string): boolean {
  if (!dueDate || TERMINAL_STATUSES.includes(status)) return false
  const cutoff = dueDate.includes('T')
    ? new Date(dueDate)
    : new Date(`${dueDate}T23:59:59`)
  return cutoff < new Date()
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '-'
  const date = value.includes('T') ? new Date(value) : new Date(`${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

export function relativeTime(value: string): string {
  const then = new Date(value).getTime()
  if (Number.isNaN(then)) return ''
  const seconds = Math.round((Date.now() - then) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  if (days < 7) return `${days}d ago`
  return new Date(value).toLocaleDateString()
}

export function initials(fullName: string): string {
  const parts = fullName.trim().split(/\s+/)
  if (!parts[0]) return '?'
  const first = parts[0].charAt(0)
  const last = parts.length > 1 ? parts[parts.length - 1].charAt(0) : ''
  return (first + last).toUpperCase()
}

// Friendly names for permission codes. The catalogue is fixed, so a static map
// keeps the role editor free of internal identifiers.
const PERMISSION_LABELS: Record<string, string> = {
  'attachments.upload': 'Upload attachments',
  'audit.read': 'View audit log',
  'audit.security.read': 'View security events',
  'blockers.escalate': 'Escalate blockers',
  'blockers.report': 'Report blockers',
  'comments.create': 'Write comments',
  'dashboards.view': 'View dashboards',
  'departments.manage': 'Manage departments',
  'exports.approved': 'Export approved data',
  'imports.manage': 'Run imports',
  'imports.view': 'View import history',
  'milestones.manage': 'Manage milestones',
  'profile.read': 'View own profile',
  'profile.update': 'Edit own profile',
  'progress.update': 'Update task progress',
  'reports.department.view': 'View department reports',
  'reports.view': 'View management reports',
  'review.approve': 'Approve reviews',
  'review.reject': 'Reject reviews',
  'review.request': 'Request reviews',
  'review.request_changes': 'Request changes in review',
  'review.view_submitted': 'View submitted reviews',
  'roles.assign': 'Assign roles',
  'settings.org.manage': 'Manage organization profile',
  'system.config.manage': 'Manage system configuration',
  'system.health.inspect': 'Check system health',
  'system.settings.manage': 'Manage system settings',
  'tasks.approve': 'Approve tasks',
  'tasks.assign_department': 'Assign across departments',
  'tasks.create': 'Create tasks',
  'tasks.manage_all': 'Manage all tasks',
  'tasks.update_assigned': 'Edit assigned tasks',
  'tasks.view_authorized': 'View authorized tasks',
  'tasks.view_department': 'View department tasks',
  'users.manage': 'Manage users',
  'work_items.update_assigned': 'Edit assigned work items',
  'workflows.configure': 'Configure workflows',
  'workload.view': 'View workload',
}

export function permissionLabel(code: string): string {
  return PERMISSION_LABELS[code] ?? capitalize(statusLabel(code.split('.').pop() ?? code))
}

export function permissionGroupName(prefix: string): string {
  return capitalize(statusLabel(prefix))
}
