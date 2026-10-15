<template>
  <div class="mx-auto max-w-7xl px-4 py-8 sm:px-6">
    <section class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <nav class="text-xs text-slate-400" aria-label="Breadcrumb">
          <NuxtLink to="/" class="hover:text-slate-600">Dashboard</NuxtLink>
          <span class="mx-1">/</span>
          <NuxtLink to="/tasks" class="hover:text-slate-600">Tasks</NuxtLink>
          <span class="mx-1">/</span>
          <span class="text-slate-600">{{ task?.task_number ?? '…' }}</span>
        </nav>
        <h1 class="mt-1 text-xl font-semibold text-slate-900">{{ task?.title ?? 'Task' }}</h1>
        <p v-if="task" class="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-500">
          <span class="font-mono text-xs text-slate-600">{{ task.task_number }}</span>
          <AppBadge :tone="statusTone(task.status)">{{ statusLabel(task.status) }}</AppBadge>
          <AppBadge :tone="priorityTone(task.priority)">{{ task.priority }} priority</AppBadge>
          <AppBadge tone="gray">{{ visibilityLabel(task.visibility_mode) }}</AppBadge>
          <span class="text-xs text-slate-400">v{{ task.version }}</span>
        </p>
      </div>
      <div v-if="task && canManage(task)" class="flex flex-wrap justify-start gap-2 sm:justify-end">
        <button
          v-for="target in allowedTransitions"
          :key="target"
          type="button"
          class="rounded-lg border px-3 py-2 text-xs font-medium transition-colors"
          :class="transitionClass(target)"
          @click="beginTransition(target)"
        >
          {{ transitionLabel(target) }}
        </button>
      </div>
    </section>

    <p v-if="loadError" class="mt-6 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{{ loadError }}</p>

    <div v-if="task" class="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
      <div class="space-y-6 lg:col-span-2">
        <section class="rounded-2xl border border-slate-200 bg-white p-5">
          <div class="flex items-center justify-between">
            <h2 class="text-sm font-semibold text-slate-900">Summary</h2>
            <button
              v-if="canManage(task) && !editing"
              type="button"
              class="text-xs font-medium text-brand-600 hover:text-brand-700"
              @click="startEdit"
            >
              Edit
            </button>
          </div>
          <template v-if="!editing">
            <p class="mt-3 whitespace-pre-line text-sm text-slate-600">{{ task.description || 'No description yet.' }}</p>
            <dl class="mt-4 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
              <div>
                <dt class="text-xs text-slate-400">Accountable PM</dt>
                <dd class="mt-0.5 font-medium text-slate-800">{{ task.accountable_pm?.full_name ?? '-' }}</dd>
              </div>
              <div>
                <dt class="text-xs text-slate-400">Start</dt>
                <dd class="mt-0.5 text-slate-800">{{ formatDate(task.start_date) }}</dd>
              </div>
              <div>
                <dt class="text-xs text-slate-400">Due</dt>
                <dd class="mt-0.5" :class="isOverdue ? 'font-medium text-rose-600' : 'text-slate-800'">{{ formatDate(task.due_date) }}</dd>
              </div>
              <div>
                <dt class="text-xs text-slate-400">Next follow-up</dt>
                <dd class="mt-0.5 text-slate-800">{{ formatDate(task.next_follow_up_date) }}</dd>
              </div>
              <div>
                <dt class="text-xs text-slate-400">Progress ({{ task.progress_mode }})</dt>
                <dd class="mt-1 flex items-center gap-2">
                  <div class="h-1.5 w-24 overflow-hidden rounded-full bg-slate-100">
                    <div class="h-full rounded-full bg-brand-500" :style="{ width: `${task.percent_complete}%` }" />
                  </div>
                  <span class="text-xs text-slate-500">{{ task.percent_complete }}%</span>
                </dd>
              </div>
              <div>
                <dt class="text-xs text-slate-400">Created</dt>
                <dd class="mt-0.5 text-slate-800">{{ formatDateTime(task.created_at) }}</dd>
              </div>
              <div v-if="task.dependency_summary" class="col-span-2">
                <dt class="text-xs text-slate-400">Dependencies &amp; blockers</dt>
                <dd class="mt-0.5 text-slate-800">{{ task.dependency_summary }}</dd>
              </div>
            </dl>
          </template>
          <template v-else>
            <div class="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <label class="sm:col-span-2 block">
                <span class="text-xs font-medium text-slate-600">Title</span>
                <input v-model="editForm.title" type="text" class="input-field mt-1" />
              </label>
              <label class="sm:col-span-2 block">
                <span class="text-xs font-medium text-slate-600">Description</span>
                <textarea v-model="editForm.description" rows="4" class="input-field mt-1" />
              </label>
              <label class="block">
                <span class="text-xs font-medium text-slate-600">Priority</span>
                <select v-model="editForm.priority" class="input-field mt-1">
                  <option v-for="p in PRIORITIES" :key="p" :value="p">{{ p }}</option>
                </select>
              </label>
              <label class="block">
                <span class="text-xs font-medium text-slate-600">Percent complete</span>
                <input v-model.number="editForm.percent_complete" type="number" min="0" max="100" class="input-field mt-1" />
              </label>
              <label class="block">
                <span class="text-xs font-medium text-slate-600">Due date</span>
                <input v-model="editForm.due_date" type="date" class="input-field mt-1" />
              </label>
              <label class="block">
                <span class="text-xs font-medium text-slate-600">Next follow-up</span>
                <input v-model="editForm.next_follow_up_date" type="date" class="input-field mt-1" />
              </label>
              <label class="sm:col-span-2 block">
                <span class="text-xs font-medium text-slate-600">Dependencies / blockers note</span>
                <textarea v-model="editForm.dependency_summary" rows="2" class="input-field mt-1" />
              </label>
            </div>
            <p v-if="editError" class="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{{ editError }}</p>
            <div class="mt-4 flex justify-end gap-2">
              <button type="button" class="btn-secondary" @click="editing = false">Cancel</button>
              <button type="button" class="btn-primary" @click="saveEdit">Save changes</button>
            </div>
          </template>
        </section>

        <WorkflowPanel :task="task" @changed="reloadLight" />
        <WorkflowGantt
          v-if="workflow"
          :workflow="workflow"
          :task-start="task.start_date"
          :task-due="task.due_date"
        />

        <TaskComments :task-id="task.id" />
        <TaskAttachments :task-id="task.id" />

        <section class="rounded-2xl border border-slate-200 bg-white p-5">
          <h2 class="text-sm font-semibold text-slate-900">Activity history</h2>
          <p class="mt-1 text-xs text-slate-400">Every creation, transition, assignment, and access change on this task (AC-12).</p>
          <ol v-if="activity.length" class="mt-4 space-y-4">
            <li v-for="a in activity" :key="a.id" class="relative border-l-2 border-slate-100 pl-4">
              <span class="absolute -left-[7px] top-1 h-3 w-3 rounded-full border-2 border-white" :class="activityDot(a.activity_type)" />
              <p class="text-sm text-slate-700">{{ a.summary }}</p>
              <p class="mt-0.5 text-xs text-slate-400">
                {{ a.actor?.full_name ?? 'System' }} · {{ formatDateTime(a.created_at) }}
              </p>
            </li>
          </ol>
          <p v-else class="mt-4 text-sm text-slate-400">No activity recorded yet.</p>
        </section>
      </div>

      <div class="space-y-6">
        <section class="rounded-2xl border border-slate-200 bg-white p-5">
          <div class="flex items-center justify-between">
            <h2 class="text-sm font-semibold text-slate-900">Assignments</h2>
            <button
              v-if="canManage(task)"
              type="button"
              class="text-xs font-medium text-brand-600 hover:text-brand-700"
              @click="showAssign = true"
            >
              + Assign
            </button>
          </div>
          <ul class="mt-3 space-y-3">
            <li v-for="a in activeAssignments" :key="a.id" class="flex items-start justify-between gap-2">
              <div>
                <p class="text-sm font-medium text-slate-800">{{ a.user.full_name }}</p>
                <p class="text-xs text-slate-400">{{ roleLabel(a.assignment_role) }} · assigned by {{ assignerName(a.assigned_by_id) }}</p>
              </div>
              <button
                v-if="canManage(task) && a.assignment_role !== 'accountable_pm'"
                type="button"
                class="rounded-lg border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-100"
                @click="removeAssignment(a)"
              >
                Remove
              </button>
            </li>
          </ul>
          <p v-if="!activeAssignments.length" class="mt-3 text-sm text-slate-400">No active assignments.</p>
          <p class="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">
            One accountable PM per task (DEC-02). Replace the accountable PM from the Assign dialog.
          </p>
        </section>

        <section class="rounded-2xl border border-slate-200 bg-white p-5">
          <div class="flex items-center justify-between">
            <h2 class="text-sm font-semibold text-slate-900">Departments</h2>
          </div>
          <ul class="mt-3 space-y-2">
            <li v-for="td in task.task_departments" :key="td.id" class="flex items-center justify-between">
              <span class="text-sm text-slate-700">{{ td.department_name ?? td.department_id }}</span>
              <AppBadge tone="gray">{{ td.participation_type }}</AppBadge>
            </li>
          </ul>
          <p v-if="!task.task_departments.length" class="mt-2 text-sm text-slate-400">No departments linked.</p>
        </section>

        <section class="rounded-2xl border border-slate-200 bg-white p-5">
          <div class="flex items-center justify-between">
            <h2 class="text-sm font-semibold text-slate-900">Access grants</h2>
            <button
              v-if="canChangeVisibility(task)"
              type="button"
              class="text-xs font-medium text-brand-600 hover:text-brand-700"
              @click="showGrant = true"
            >
              + Grant
            </button>
          </div>
          <p class="mt-1 text-xs text-slate-400">
            Explicit per-user access; revocation is immediate. Denials always win.
          </p>
          <ul class="mt-3 space-y-3">
            <li v-for="g in activeGrants" :key="g.id" class="flex items-start justify-between gap-2">
              <div>
                <p class="text-sm font-medium text-slate-800">
                  {{ g.principal.full_name }}
                  <AppBadge :tone="g.access_level === 'denied' ? 'rose' : g.access_level === 'manage' ? 'amber' : 'gray'" class="ml-1">
                    {{ g.access_level }}
                  </AppBadge>
                </p>
                <p class="text-xs text-slate-400">granted {{ formatDateTime(g.granted_at) }}</p>
              </div>
              <button
                v-if="canChangeVisibility(task)"
                type="button"
                class="rounded-lg border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-100"
                @click="revokeGrant(g)"
              >
                Revoke
              </button>
            </li>
          </ul>
          <p v-if="!activeGrants.length" class="mt-3 text-sm text-slate-400">No explicit grants.</p>
        </section>
      </div>
    </div>

    <div v-if="pendingTransition" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" @click.self="pendingTransition = null">
      <div class="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
        <h2 class="text-lg font-semibold text-slate-900">{{ transitionLabel(pendingTransition) }}</h2>
        <p class="mt-1 text-sm text-slate-500">
          {{ reasonHint(pendingTransition) }}
        </p>
        <textarea
          v-model="transitionReason"
          rows="3"
          class="input-field mt-4"
          placeholder="Recorded on the task history…"
        />
        <p v-if="transitionError" class="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{{ transitionError }}</p>
        <div class="mt-5 flex justify-end gap-3">
          <button type="button" class="btn-secondary" @click="pendingTransition = null">Cancel</button>
          <button type="button" class="btn-primary" @click="confirmTransition">Confirm</button>
        </div>
      </div>
    </div>

    <div v-if="showAssign" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" @click.self="showAssign = false">
      <div class="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
        <h2 class="text-lg font-semibold text-slate-900">Assign a person</h2>
        <p v-if="assignError" class="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{{ assignError }}</p>
        <label class="mt-4 block">
          <span class="text-xs font-medium text-slate-600">Person</span>
          <select v-model="assignForm.user_id" class="input-field mt-1">
            <option value="">Select…</option>
            <option v-for="u in directoryUsers" :key="u.id" :value="u.id">{{ u.full_name }} ({{ u.employee_code }})</option>
          </select>
        </label>
        <label class="mt-4 block">
          <span class="text-xs font-medium text-slate-600">Role</span>
          <select v-model="assignForm.role" class="input-field mt-1">
            <option value="supporting_pm">Supporting PM</option>
            <option value="accountable_pm">Accountable PM (replaces current)</option>
            <option value="work_item_assignee">Work item assignee</option>
          </select>
        </label>
        <p v-if="assignForm.role === 'accountable_pm'" class="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">
          DEC-02: the previous accountable PM's assignment is revoked and recorded on the history.
        </p>
        <div class="mt-5 flex justify-end gap-3">
          <button type="button" class="btn-secondary" @click="showAssign = false">Cancel</button>
          <button type="button" class="btn-primary" @click="submitAssignment">Assign</button>
        </div>
      </div>
    </div>

    <div v-if="showGrant" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" @click.self="showGrant = false">
      <div class="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
        <h2 class="text-lg font-semibold text-slate-900">Grant task access</h2>
        <p v-if="grantError" class="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{{ grantError }}</p>
        <label class="mt-4 block">
          <span class="text-xs font-medium text-slate-600">Person</span>
          <select v-model="grantForm.user_id" class="input-field mt-1">
            <option value="">Select…</option>
            <option v-for="u in directoryUsers" :key="u.id" :value="u.id">{{ u.full_name }} ({{ u.employee_code }})</option>
          </select>
        </label>
        <label class="mt-4 block">
          <span class="text-xs font-medium text-slate-600">Access level</span>
          <select v-model="grantForm.level" class="input-field mt-1">
            <option value="view">View - see and comment</option>
            <option value="operate">Operate - update and coordinate</option>
            <option value="manage">Manage - administer the task</option>
            <option value="denied">Denied - explicitly blocked</option>
          </select>
        </label>
        <div class="mt-5 flex justify-end gap-3">
          <button type="button" class="btn-secondary" @click="showGrant = false">Cancel</button>
          <button type="button" class="btn-primary" @click="submitGrant">Grant</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type {
  AccessLevel,
  AssignmentRole,
  TaskAccessGrant,
  TaskActivityEntry,
  TaskAssignment,
  TaskDetail,
  TaskPriority,
  TaskStatus,
  TransitionOptions,
  Workflow,
} from '~/types/api'

const route = useRoute()
const api = useApi()
const auth = useAuth()

const PRIORITIES: TaskPriority[] = ['low', 'medium', 'high', 'critical']

const task = ref<TaskDetail | null>(null)
const activity = ref<TaskActivityEntry[]>([])
const allowedTransitions = ref<TaskStatus[]>([])
const workflow = ref<Workflow | null>(null)
const loadError = ref('')
const editing = ref(false)
const editError = ref('')
const editForm = reactive({
  title: '',
  description: '',
  priority: 'medium' as TaskPriority,
  percent_complete: 0,
  due_date: '',
  next_follow_up_date: '',
  dependency_summary: '',
})

const pendingTransition = ref<TaskStatus | null>(null)
const transitionReason = ref('')
const transitionError = ref('')

const showAssign = ref(false)
const assignError = ref('')
const assignForm = reactive({ user_id: '', role: 'supporting_pm' as AssignmentRole })
const directoryUsers = ref<{ id: string, full_name: string, employee_code: string }[]>([])

const showGrant = ref(false)
const grantError = ref('')
const grantForm = reactive<{ user_id: string, level: AccessLevel }>({ user_id: '', level: 'view' })

const activeAssignments = computed(() => (task.value?.assignments ?? []).filter(a => !a.revoked_at))
const activeGrants = computed(() => (task.value?.access_grants ?? []).filter(g => !g.revoked_at))
const isOverdue = computed(() => {
  const t = task.value
  if (!t?.due_date || ['completed', 'cancelled', 'archived'].includes(t.status)) return false
  return new Date(t.due_date).getTime() < Date.now()
})

// Permissions: manage = engine UPDATE (holds tasks.update_assigned or created it);
// visibility changes additionally require the dedicated permission per the engine.
function canManage(t: TaskDetail): boolean {
  return auth.hasPermission('tasks.update_assigned') || t.created_by_id === auth.user.value?.id
    || auth.hasPermission('tasks.manage_all')
}
function canChangeVisibility(t: TaskDetail): boolean {
  return auth.hasPermission('tasks.manage_all')
    || (auth.hasPermission('tasks.update_assigned') && canManage(t))
}

const statusLabel = (s: string) => s.replaceAll('_', ' ')
const visibilityLabel = (v: string) => v.replaceAll('_', ' ')
const roleLabel = (r: AssignmentRole) => ({
  accountable_pm: 'Accountable PM',
  supporting_pm: 'Supporting PM',
  work_item_assignee: 'Work item assignee',
}[r])
const priorityTone = (p: string) =>
  p === 'critical' ? 'rose' : p === 'high' ? 'amber' : p === 'medium' ? 'gray' : 'green'

function statusTone(s: string): 'green' | 'amber' | 'gray' | 'rose' {
  switch (s) {
    case 'completed': return 'green'
    case 'open':
    case 'in_progress': return 'amber'
    case 'blocked':
    case 'cancelled': return 'rose'
    default: return 'gray'
  }
}

function transitionLabel(s: TaskStatus): string {
  const map: Partial<Record<TaskStatus, string>> = {
    open: 'Open task', in_progress: 'Start work', blocked: 'Report blocker',
    under_review: 'Submit for review', completed: 'Mark complete',
    cancelled: 'Cancel task', archived: 'Archive',
  }
  return map[s] ?? statusLabel(s)
}

function transitionClass(s: TaskStatus): string {
  if (s === 'cancelled') return 'border-red-200 text-red-600 hover:bg-red-50'
  if (s === 'completed') return 'border-brand-200 bg-brand-600 text-white hover:bg-brand-700'
  if (s === 'archived') return 'border-slate-200 text-slate-600 hover:bg-slate-100'
  return 'border-brand-200 text-brand-700 hover:bg-brand-50'
}

function reasonHint(s: TaskStatus): string {
  if (s === 'blocked') return 'Blocking a task requires an explanation of the blocker.'
  if (s === 'cancelled') return 'Cancelling requires a recorded reason and an authorized actor.'
  if (s === 'in_progress' && task.value?.status === 'completed') return 'Reopening a completed task requires an explicit reason.'
  return 'Optional context, recorded on the task history.'
}

function activityDot(type: string): string {
  if (type === 'task.created') return 'bg-brand-500'
  if (type === 'task.status_changed') return 'bg-amber-500'
  if (type === 'task.assigned' || type === 'task.accountable_pm_changed') return 'bg-indigo-500'
  if (type === 'task.access_changed') return 'bg-rose-400'
  return 'bg-slate-300'
}

function formatDate(value: string | null): string {
  if (!value) return '-'
  return new Date(value).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

function formatDateTime(value: string | null): string {
  if (!value) return '-'
  return new Date(value).toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

function assignerName(userId: string): string {
  if (userId === task.value?.accountable_pm?.id) return task.value.accountable_pm?.full_name ?? '-'
  const fromAssignments = task.value?.assignments.find(a => a.assigned_by_id === userId)
  if (fromAssignments) return fromAssignments.user.id === userId ? fromAssignments.user.full_name : (fromAssignments.user.full_name)
  const fromGrants = task.value?.access_grants.find(g => g.granted_by_id === userId)
  if (fromGrants) return fromGrants.principal.id === userId ? fromGrants.principal.full_name : fromGrants.principal.full_name
  if (userId === auth.user.value?.id) return auth.displayName.value
  return 'a colleague'
}

function startEdit() {
  const t = task.value!
  editForm.title = t.title
  editForm.description = t.description ?? ''
  editForm.priority = t.priority
  editForm.percent_complete = t.percent_complete
  editForm.due_date = t.due_date ?? ''
  editForm.next_follow_up_date = t.next_follow_up_date ?? ''
  editForm.dependency_summary = t.dependency_summary ?? ''
  editError.value = ''
  editing.value = true
}

async function saveEdit() {
  if (!task.value) return
  editError.value = ''
  try {
    task.value = await api.patch<TaskDetail>(`/api/v1/tasks/${task.value.id}`, {
      version: task.value.version,
      title: editForm.title.trim(),
      description: editForm.description.trim() || null,
      priority: editForm.priority,
      percent_complete: editForm.percent_complete,
      due_date: editForm.due_date || null,
      next_follow_up_date: editForm.next_follow_up_date || null,
      dependency_summary: editForm.dependency_summary.trim() || null,
    })
    editing.value = false
    await loadActivity()
  } catch (err) {
    editError.value = err instanceof Error ? err.message : 'Could not save the changes.'
  }
}

function beginTransition(target: TaskStatus) {
  transitionReason.value = ''
  transitionError.value = ''
  pendingTransition.value = target
}

async function confirmTransition() {
  if (!task.value || !pendingTransition.value) return
  transitionError.value = ''
  try {
    task.value = await api.post<TaskDetail>(`/api/v1/tasks/${task.value.id}/transition`, {
      to_status: pendingTransition.value,
      reason: transitionReason.value.trim() || null,
    })
    pendingTransition.value = null
    await Promise.all([loadActivity(), loadTransitions()])
  } catch (err) {
    transitionError.value = err instanceof Error ? err.message : 'The transition was rejected.'
  }
}

async function removeAssignment(a: TaskAssignment) {
  if (!task.value) return
  try {
    await api.delete(`/api/v1/tasks/${task.value.id}/assignments/${a.id}`)
    await reload()
  } catch (err) {
    assignError.value = err instanceof Error ? err.message : 'Could not remove the assignment.'
  }
}

async function submitAssignment() {
  if (!task.value) return
  assignError.value = ''
  if (!assignForm.user_id) { assignError.value = 'Select a person first.'; return }
  try {
    task.value = await api.post<TaskDetail>(`/api/v1/tasks/${task.value.id}/assignments`, {
      user_id: assignForm.user_id,
      assignment_role: assignForm.role,
    })
    showAssign.value = false
    assignForm.user_id = ''
    await Promise.all([loadActivity(), reloadLight()])
  } catch (err) {
    assignError.value = err instanceof Error ? err.message : 'The assignment was rejected.'
  }
}

async function revokeGrant(g: TaskAccessGrant) {
  if (!task.value) return
  try {
    await api.delete(`/api/v1/tasks/${task.value.id}/access-grants/${g.id}`)
    await reload()
  } catch (err) {
    grantError.value = err instanceof Error ? err.message : 'Could not revoke the grant.'
  }
}

async function submitGrant() {
  if (!task.value) return
  grantError.value = ''
  if (!grantForm.user_id) { grantError.value = 'Select a person first.'; return }
  try {
    task.value = await api.post<TaskDetail>(`/api/v1/tasks/${task.value.id}/access-grants`, {
      user_id: grantForm.user_id,
      access_level: grantForm.level,
    })
    showGrant.value = false
    grantForm.user_id = ''
    await loadActivity()
  } catch (err) {
    grantError.value = err instanceof Error ? err.message : 'The grant was rejected.'
  }
}

async function loadTransitions() {
  if (!task.value) return
  try {
    const options = await api.get<TransitionOptions>(`/api/v1/tasks/${task.value.id}/transition-options`)
    allowedTransitions.value = options.allowed_transitions
  } catch {
    allowedTransitions.value = []
  }
}

async function loadActivity() {
  if (!task.value) return
  try {
    activity.value = await api.get<TaskActivityEntry[]>(`/api/v1/tasks/${task.value.id}/activity`)
  } catch {
    activity.value = []
  }
}

async function loadWorkflow() {
  if (!task.value) return
  try {
    workflow.value = await api.get<Workflow>(`/api/v1/tasks/${task.value.id}/workflow`)
  } catch {
    workflow.value = null
  }
}

async function reload() {
  const t = await api.get<TaskDetail>(`/api/v1/tasks/${String(route.params.id)}`)
  task.value = t
  await Promise.all([loadActivity(), loadTransitions(), loadWorkflow()])
}

async function reloadLight() {
  const t = await api.get<TaskDetail>(`/api/v1/tasks/${String(route.params.id)}`)
  task.value = t
  await Promise.all([loadActivity(), loadWorkflow()])
}

async function loadDirectory() {
  // Directory lookup for assign/grant dialogs; hidden when lacking permission.
  try {
    const users = await api.get<{ items: { id: string, full_name: string, employee_code: string, account_status: string }[] }>('/api/v1/users?page_size=100')
    directoryUsers.value = users.items.filter(u => u.account_status === 'active')
  } catch { /* needs users.manage */ }
}

onMounted(async () => {
  try {
    await reload()
  } catch (err) {
    loadError.value = err instanceof Error && err.message.includes('not found')
      ? 'This task does not exist or you are not authorized to see it.'
      : 'Could not load the task.'
  }
  await loadDirectory()
})

useHead({ title: 'Task detail - DecOps' })
</script>
