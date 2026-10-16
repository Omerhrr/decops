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
