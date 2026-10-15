<template>
  <div v-if="!workflow" class="rounded-2xl border border-line bg-surface p-5 text-sm text-faint">
    Loading workflow…
  </div>
  <div v-else class="space-y-6">
    <!-- Progress + calculation method (AC-06) -->
    <section class="rounded-2xl border border-line bg-surface p-5">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="text-sm font-semibold text-ink">Workflow progress</h2>
          <p class="mt-1 text-xs text-faint">
            {{ workflow!.task_progress_mode === 'calculated'
              ? 'Calculated from the workflow (weighted stages × required items).'
              : 'Manual progress entry; the engine calculation is shown for reference.' }}
          </p>
        </div>
        <button
          v-if="canManage"
          type="button"
          class="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-body hover:bg-hover"
          @click="toggleProgressMode"
        >
          Switch to {{ workflow!.task_progress_mode === 'calculated' ? 'manual' : 'calculated' }}
        </button>
      </div>

      <div class="mt-4 flex items-center gap-3">
        <div class="h-2.5 flex-1 overflow-hidden rounded-full bg-hover">
          <div
            class="h-full rounded-full transition-all"
            :class="workflow!.task_progress_mode === 'calculated' ? 'bg-brand-500' : 'bg-indigo-400'"
            :style="{ width: `${displayPercent}%` }"
          />
        </div>
        <span class="text-sm font-semibold text-body">{{ displayPercent }}%</span>
      </div>
      <p class="mt-2 text-xs text-muted">{{ workflow!.progress.method }}</p>

      <div v-if="workflow!.progress.stages.length" class="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
        <div v-for="s in workflow!.progress.stages" :key="s.stage_id" class="rounded-xl bg-elevated px-3 py-2">
          <div class="flex items-center justify-between text-xs">
            <span class="font-medium text-body">{{ s.stage_name }}</span>
            <span class="text-faint">weight {{ s.weight }} · {{ s.percent }}%</span>
          </div>
          <div class="mt-1.5 h-1.5 overflow-hidden rounded-full bg-hover">
            <div class="h-full rounded-full bg-brand-400" :style="{ width: `${s.percent}%` }" />
          </div>
          <p class="mt-1 text-[11px] leading-4 text-faint">{{ s.method }}</p>
        </div>
      </div>
    </section>

    <!-- Stages & work items (editor) -->
    <section class="rounded-2xl border border-line bg-surface p-5">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 class="text-sm font-semibold text-ink">Stages &amp; work items</h2>
          <p class="mt-1 text-xs text-faint">
            Sequential stages start when all earlier stages finish; parallel stages run simultaneously. Cycles and invalid transitions are rejected by the engine.
          </p>
        </div>
        <button
          v-if="canManage"
          type="button"
          class="rounded-lg bg-brand-600 px-3 py-2 text-xs font-medium text-white hover:bg-brand-700"
          @click="openStageModal()"
        >
          + Add stage
        </button>
      </div>

      <p v-if="panelError" class="mt-3 rounded-lg bg-rose-50 dark:bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">{{ panelError }}</p>

      <ol v-if="workflow!.stages.length" class="mt-4 space-y-4">
        <li v-for="stage in workflow!.stages" :key="stage.id" class="rounded-xl border border-line bg-elevated/60 p-4">
          <div class="flex flex-wrap items-start justify-between gap-2">
            <div>
              <p class="flex flex-wrap items-center gap-2 text-sm font-semibold text-ink">
                <span class="text-faint">{{ stage.sequence_number }}.</span>
                {{ stage.name }}
                <AppBadge :tone="stageStatusTone(stage.status)">{{ stageStatusLabel(stage.status) }}</AppBadge>
                <AppBadge tone="gray">{{ stage.execution_mode }}</AppBadge>
                <AppBadge v-if="stage.progress_basis !== 'all_items'" tone="amber">{{ basisLabel(stage.progress_basis) }}</AppBadge>
                <AppBadge v-if="!isActionable(stage) && stage.status === 'pending'" tone="rose">waiting</AppBadge>
              </p>
              <p class="mt-1 text-xs text-faint">
                weight {{ stage.weight }} · {{ formatDate(stage.start_date) }} → {{ formatDate(stage.due_date) }}
                <template v-if="stage.completed_at"> · completed {{ formatDateTime(stage.completed_at) }}</template>
              </p>
            </div>
            <div v-if="canManage" class="flex flex-wrap gap-1.5">
              <button v-if="stage.status === 'pending'" type="button" class="stage-btn" @click="transitionStage(stage, 'in_progress')">Start</button>
              <button v-if="stage.status === 'in_progress'" type="button" class="stage-btn brand" @click="transitionStage(stage, 'completed')">Complete</button>
              <button v-if="stage.status === 'in_progress'" type="button" class="stage-btn danger" @click="transitionStage(stage, 'cancelled')">Cancel</button>
              <button v-if="stage.status === 'pending'" type="button" class="stage-btn danger" @click="transitionStage(stage, 'cancelled')">Cancel</button>
              <button v-if="stage.status === 'completed'" type="button" class="stage-btn" @click="transitionStage(stage, 'in_progress')">Reopen</button>
              <button v-if="stage.status === 'cancelled'" type="button" class="stage-btn" @click="transitionStage(stage, 'pending')">Restore</button>
              <button type="button" class="stage-btn" @click="openStageModal(stage)">Edit</button>
              <button type="button" class="stage-btn danger" @click="deleteStage(stage)">Delete</button>
            </div>
          </div>

          <!-- Work items -->
          <ul class="mt-3 space-y-2">
            <li v-for="item in itemsOf(stage.id)" :key="item.id"
                class="rounded-lg border px-3 py-2"
                :class="item.status === 'cancelled' ? 'border-line bg-surface/40 opacity-60' : 'border-line bg-surface'">
              <div class="flex flex-wrap items-start justify-between gap-2">
                <div class="min-w-0">
                  <p class="flex flex-wrap items-center gap-1.5 text-sm text-ink">
                    <span class="inline-block h-2 w-2 rotate-45 rounded-[1px]"
                          :class="item.item_type === 'milestone' ? 'bg-amber-500' : 'bg-line-strong'" />
                    <span class="font-medium">{{ item.title }}</span>
                    <AppBadge :tone="itemStatusTone(item.status)">{{ item.status.replaceAll('_', ' ') }}</AppBadge>
                    <AppBadge v-if="!item.is_required" tone="gray">optional</AppBadge>
                    <AppBadge v-if="isBlocked(item)" tone="rose">blocked by {{ blockedByNames(item) }}</AppBadge>
                  </p>
                  <p class="mt-0.5 text-xs text-faint">
                    {{ item.assignee ? `assigned to ${item.assignee.full_name}` : 'unassigned' }}
                    · weight {{ item.weight }}
                    · due {{ formatDate(item.due_date) }}
                    <template v-if="item.completed_at"> · completed {{ formatDateTime(item.completed_at) }}</template>
                  </p>
                  <p v-if="item.parent_work_item_id" class="mt-0.5 text-[11px] text-faint">
                    under milestone “{{ itemTitle(item.parent_work_item_id) }}”
                  </p>
                </div>
                <div v-if="canManage" class="flex flex-wrap gap-1.5">
                  <button v-if="item.status === 'pending'" type="button" class="stage-btn" @click="transitionItem(item, 'in_progress')">Start</button>
                  <button v-if="item.status === 'in_progress'" type="button" class="stage-btn brand" @click="transitionItem(item, 'completed')">Complete</button>
                  <button v-if="item.status === 'completed'" type="button" class="stage-btn" @click="transitionItem(item, 'in_progress')">Reopen</button>
                  <button v-if="['pending', 'in_progress'].includes(item.status)" type="button" class="stage-btn danger" @click="transitionItem(item, 'cancelled')">Cancel</button>
                  <button v-if="item.status === 'cancelled'" type="button" class="stage-btn" @click="transitionItem(item, 'pending')">Restore</button>
                  <button type="button" class="stage-btn" @click="openAssignModal(item)">{{ item.assignee ? 'Reassign' : 'Assign' }}</button>
                  <button type="button" class="stage-btn" @click="openItemModal(stage, item)">Edit</button>
                  <button type="button" class="stage-btn danger" @click="deleteItem(item)">Delete</button>
                </div>
              </div>
            </li>
          </ul>
          <p v-if="!itemsOf(stage.id).length" class="mt-2 text-xs text-faint">No work items in this stage yet.</p>

          <button
            v-if="canManage"
            type="button"
            class="mt-3 text-xs font-medium text-brand-600 dark:text-brand-400 hover:text-brand-700 dark:hover:text-brand-300"
            @click="openItemModal(stage)"
          >
            + Add milestone / subtask
          </button>
        </li>
      </ol>
      <p v-else class="mt-4 rounded-xl bg-elevated px-4 py-6 text-center text-sm text-faint">
        No stages yet - build the workflow to track stages, milestones and progress.
      </p>
    </section>

    <!-- Dependencies -->
    <section class="rounded-2xl border border-line bg-surface p-5">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 class="text-sm font-semibold text-ink">Dependencies &amp; blockers</h2>
          <p class="mt-1 text-xs text-faint">A work item cannot start until its predecessors complete. Cycles are rejected.</p>
        </div>
      </div>
      <ul v-if="workflow!.dependencies.length" class="mt-3 space-y-2">
        <li v-for="dep in workflow!.dependencies" :key="dep.id" class="flex items-center justify-between rounded-lg bg-elevated px-3 py-2 text-sm">
          <span class="text-body">
            <span class="font-medium">{{ itemTitle(dep.successor_id) }}</span>
            <span class="mx-1 text-faint">is blocked until</span>
            <span class="font-medium">{{ itemTitle(dep.predecessor_id) }}</span>
            <span class="text-faint">completes</span>
          </span>
          <button v-if="canManage" type="button" class="stage-btn danger" @click="removeDependency(dep)">Remove</button>
        </li>
      </ul>
      <p v-else class="mt-3 text-sm text-faint">No dependencies defined.</p>

      <form v-if="canManage && workflow!.items.length >= 2" class="mt-4 flex flex-wrap items-end gap-2" @submit.prevent="addDependency">
        <label class="block">
          <span class="text-xs font-medium text-body">Work item</span>
          <select v-model="depForm.successor_id" class="dep-select">
            <option value="">Select…</option>
            <option v-for="i in workflow!.items" :key="i.id" :value="i.id">{{ itemTitle(i.id) }}</option>
          </select>
        </label>
        <span class="pb-2 text-xs text-faint">cannot start until</span>
        <label class="block">
          <span class="text-xs font-medium text-body">Predecessor</span>
          <select v-model="depForm.predecessor_id" class="dep-select">
            <option value="">Select…</option>
            <option v-for="i in workflow!.items" :key="i.id" :value="i.id">{{ itemTitle(i.id) }}</option>
          </select>
        </label>
        <button type="submit" class="rounded-lg bg-brand-600 px-3 py-2 text-xs font-medium text-white hover:bg-brand-700">Link</button>
      </form>
    </section>

    <!-- Stage modal -->
    <div v-if="stageModal" class="modal-backdrop" @click.self="stageModal = null">
      <div class="modal-card">
        <h2 class="text-lg font-semibold text-ink">{{ stageModal.existing ? 'Edit stage' : 'Add stage' }}</h2>
        <div class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label class="sm:col-span-2 block">
            <span class="field-label">Name</span>
            <input v-model="stageForm.name" type="text" class="field" placeholder="e.g. Discovery">
          </label>
          <label class="block">
            <span class="field-label">Execution mode</span>
            <select v-model="stageForm.execution_mode" class="field">
              <option value="sequential">Sequential - waits for earlier stages</option>
              <option value="parallel">Parallel - may run simultaneously</option>
            </select>
          </label>
          <label class="block">
            <span class="field-label">Position</span>
            <input v-model.number="stageForm.sequence_number" type="number" min="1" class="field" placeholder="end">
          </label>
          <label class="block">
            <span class="field-label">Weight (progress share)</span>
            <input v-model.number="stageForm.weight" type="number" min="1" max="100" class="field">
          </label>
          <label class="block">
            <span class="field-label">Progress basis</span>
            <select v-model="stageForm.progress_basis" class="field">
              <option value="all_items">All items</option>
              <option value="milestones_only">Milestones only</option>
              <option value="subtasks_only">Subtasks only</option>
            </select>
          </label>
          <label class="block">
            <span class="field-label">Start date</span>
            <input v-model="stageForm.start_date" type="date" class="field">
          </label>
          <label class="block">
            <span class="field-label">Due date</span>
            <input v-model="stageForm.due_date" type="date" class="field">
          </label>
        </div>
        <p v-if="modalError" class="mt-3 rounded-lg bg-rose-50 dark:bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">{{ modalError }}</p>
        <div class="mt-5 flex justify-end gap-3">
          <button type="button" class="btn-ghost" @click="stageModal = null">Cancel</button>
          <button type="button" class="btn-primary" @click="submitStage">{{ stageModal.existing ? 'Save' : 'Add stage' }}</button>
        </div>
      </div>
    </div>

    <!-- Item modal -->
    <div v-if="itemModal" class="modal-backdrop" @click.self="itemModal = null">
      <div class="modal-card">
        <h2 class="text-lg font-semibold text-ink">{{ itemModal.existing ? 'Edit work item' : 'Add work item' }}</h2>
        <div class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label class="block">
            <span class="field-label">Type</span>
            <select v-model="itemForm.item_type" class="field" :disabled="!!itemModal.existing">
              <option value="milestone">Milestone</option>
              <option value="subtask">Subtask</option>
            </select>
          </label>
          <label class="block">
            <span class="field-label">Parent milestone (subtasks only)</span>
            <select v-model="itemForm.parent_work_item_id" class="field" :disabled="!!itemModal.existing">
              <option value="">None</option>
              <option v-for="m in milestoneOptions(itemModal.stage.id, itemModal.existing?.id)" :key="m.id" :value="m.id">{{ m.title }}</option>
            </select>
          </label>
          <label class="sm:col-span-2 block">
            <span class="field-label">Title</span>
            <input v-model="itemForm.title" type="text" class="field" placeholder="e.g. MVP live">
          </label>
          <label class="block">
            <span class="field-label">Weight</span>
            <input v-model.number="itemForm.weight" type="number" min="1" max="100" class="field">
          </label>
          <label class="flex items-center gap-2 pb-2">
            <input v-model="itemForm.is_required" type="checkbox" class="h-4 w-4 rounded border-line-strong">
            <span class="text-xs font-medium text-body">Required (counts toward progress, gates completion)</span>
          </label>
          <label class="block">
            <span class="field-label">Start date</span>
            <input v-model="itemForm.start_date" type="date" class="field">
          </label>
          <label class="block">
            <span class="field-label">Due date</span>
            <input v-model="itemForm.due_date" type="date" class="field">
          </label>
        </div>
        <p v-if="modalError" class="mt-3 rounded-lg bg-rose-50 dark:bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">{{ modalError }}</p>
        <div class="mt-5 flex justify-end gap-3">
          <button type="button" class="btn-ghost" @click="itemModal = null">Cancel</button>
          <button type="button" class="btn-primary" @click="submitItem">{{ itemModal.existing ? 'Save' : 'Add item' }}</button>
        </div>
      </div>
    </div>

    <div v-if="assignModal" class="modal-backdrop" @click.self="assignModal = null">
      <div class="modal-card max-w-md">
        <h2 class="text-lg font-semibold text-ink">Assign “{{ assignModal.item.title }}”</h2>
        <label class="mt-4 block">
          <span class="field-label">Person</span>
          <select v-model="assignForm.user_id" class="field">
            <option value="">Unassigned</option>
            <option v-for="u in assignees" :key="u.id" :value="u.id">{{ u.full_name }} ({{ u.employee_code }})</option>
          </select>
        </label>
        <p v-if="modalError" class="mt-3 rounded-lg bg-rose-50 dark:bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">{{ modalError }}</p>
        <div class="mt-5 flex justify-end gap-3">
          <button type="button" class="btn-ghost" @click="assignModal = null">Cancel</button>
          <button type="button" class="btn-primary" @click="submitAssign">Save</button>
        </div>
      </div>
    </div>

    <!-- Reason modal (stage/item transitions needing justification) -->
    <div v-if="reasonModal" class="modal-backdrop" @click.self="reasonModal = null">
      <div class="modal-card max-w-md">
        <h2 class="text-lg font-semibold text-ink">{{ reasonModal.summary }}</h2>
        <p class="mt-1 text-sm text-muted">
          {{ reasonModal.needsReason ? 'This change is recorded with a required reason.' : 'Optional context, recorded on the task history.' }}
        </p>
        <textarea v-model="reasonForm.reason" rows="3" class="field mt-3" placeholder="Recorded on the task history…" />
        <p v-if="modalError" class="mt-3 rounded-lg bg-rose-50 dark:bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">{{ modalError }}</p>
        <div class="mt-5 flex justify-end gap-3">
          <button type="button" class="btn-ghost" @click="reasonModal = null">Cancel</button>
          <button type="button" class="btn-primary" @click="confirmReasonTransition">Confirm</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type {
  ProgressBasis,
  TaskDetail,
  Workflow,
  WorkflowDependency,
  WorkflowStage,
  WorkItem,
  WorkItemStatus,
  WorkItemType,
} from '~/types/api'

const props = defineProps<{ task: TaskDetail }>()
const emit = defineEmits<{ changed: [] }>()

const api = useApi()
const auth = useAuth()

const workflow = ref<Workflow | null>(null)
const panelError = ref('')
const modalError = ref('')
const directoryUsers = ref<{ id: string, full_name: string, employee_code: string }[]>([])

const canManage = computed(() =>
  auth.hasPermission('tasks.update_assigned')
  || props.task.created_by_id === auth.user.value?.id
  || auth.hasPermission('tasks.manage_all'),
)

const displayPercent = computed(() =>
  workflow.value?.task_progress_mode === 'calculated'
    ? workflow.value.calculated_percent
    : props.task.percent_complete,
)

async function load() {
  try {
    workflow.value = await api.get<Workflow>(`/api/v1/tasks/${props.task.id}/workflow`)
    panelError.value = ''
  } catch (err) {
    panelError.value = err instanceof Error ? err.message : 'Could not load the workflow.'
  }
}

async function loadDirectory() {
  try {
    const users = await api.get<{ items: { id: string, full_name: string, employee_code: string, account_status: string }[] }>('/api/v1/users?page_size=100')
    directoryUsers.value = users.items.filter(u => u.account_status === 'active')
  } catch { /* needs users.manage; assign dialog falls back to task participants */ }
}

const assignees = computed(() => {
  if (directoryUsers.value.length) return directoryUsers.value
  const people = new Map<string, { id: string, full_name: string, employee_code: string }>()
  for (const a of props.task.assignments) if (a.user && !a.revoked_at) people.set(a.user.id, a.user)
  for (const g of props.task.access_grants) if (g.principal && !g.revoked_at) people.set(g.principal.id, g.principal)
  return [...people.values()]
})

onMounted(async () => {
  await Promise.all([load(), loadDirectory()])
})

function refreshAll() {
  emit('changed')
  return load()
}

function itemsOf(stageId: string): WorkItem[] {
  return (workflow.value?.items ?? []).filter(i => i.stage_id === stageId)
}
function itemTitle(itemId: string): string {
  return workflow.value?.items.find(i => i.id === itemId)?.title ?? 'work item'
}
function isActionable(stage: WorkflowStage): boolean {
  return workflow.value?.actionable_stage_ids.includes(stage.id) ?? false
}
function isBlocked(item: WorkItem): boolean {
  return workflow.value?.blockers.some(b => b.item_id === item.id) ?? false
}
function blockedByNames(item: WorkItem): string {
  const blocker = workflow.value?.blockers.find(b => b.item_id === item.id)
  if (!blocker) return ''
  return blocker.blocked_by.map(id => itemTitle(id)).join(', ')
}
function milestoneOptions(stageId: string, excludeId?: string): WorkItem[] {
  return (workflow.value?.items ?? []).filter(
    i => i.stage_id === stageId && i.item_type === 'milestone' && i.id !== excludeId,
  )
}

async function toggleProgressMode() {
  if (!workflow.value) return
  const next = workflow.value.task_progress_mode === 'calculated' ? 'manual' : 'calculated'
  try {
    await api.post(`/api/v1/tasks/${props.task.id}/workflow-settings`, { progress_mode: next })
    await refreshAll()
  } catch (err) {
    panelError.value = err instanceof Error ? err.message : 'Could not switch the progress mode.'
  }
}

const stageModal = ref<{ existing: WorkflowStage | null } | null>(null)
const stageForm = reactive({
  name: '',
  execution_mode: 'sequential',
  sequence_number: null as number | null,
  weight: 1,
  progress_basis: 'all_items' as ProgressBasis,
  start_date: '',
  due_date: '',
})

function openStageModal(existing?: WorkflowStage) {
  modalError.value = ''
  stageModal.value = { existing: existing ?? null }
  stageForm.name = existing?.name ?? ''
  stageForm.execution_mode = existing?.execution_mode ?? 'sequential'
  stageForm.sequence_number = existing?.sequence_number ?? null
  stageForm.weight = existing?.weight ?? 1
  stageForm.progress_basis = existing?.progress_basis ?? 'all_items'
  stageForm.start_date = existing?.start_date ?? ''
  stageForm.due_date = existing?.due_date ?? ''
}

async function submitStage() {
  if (!stageModal.value) return
  modalError.value = ''
  const payload = {
    name: stageForm.name.trim(),
    execution_mode: stageForm.execution_mode,
    weight: stageForm.weight,
    progress_basis: stageForm.progress_basis,
    sequence_number: stageForm.sequence_number,
    start_date: stageForm.start_date || null,
    due_date: stageForm.due_date || null,
  }
  try {
    if (stageModal.value.existing) {
      await api.patch(`/api/v1/tasks/${props.task.id}/stages/${stageModal.value.existing.id}`, payload)
    } else {
      await api.post(`/api/v1/tasks/${props.task.id}/stages`, payload)
    }
    stageModal.value = null
    await refreshAll()
  } catch (err) {
    modalError.value = err instanceof Error ? err.message : 'The stage was rejected.'
  }
}

const reasonModal = ref<{ kind: 'stage' | 'item', id: string, to: string, summary: string, needsReason: boolean } | null>(null)
const reasonForm = reactive({ reason: '' })

const REASON_REQUIRED = new Set(['cancelled', 'pending', 'in_progress_after_completed'])
function needsReasonFor(current: string, to: string): boolean {
  if (to === 'cancelled') return true
  if (to === 'in_progress' && current === 'completed') return true
  if (to === 'pending' && current === 'cancelled') return true
  return false
}
void REASON_REQUIRED

function transitionStage(stage: WorkflowStage, to: string) {
  openReasonModal('stage', stage.id, to, `Stage “${stage.name}” → ${stageStatusLabel(to)}`, needsReasonFor(stage.status, to))
}
function transitionItem(item: WorkItem, to: string) {
  openReasonModal('item', item.id, to, `Work item “${item.title}” → ${item.status.replaceAll('_', ' ')} → ${to.replaceAll('_', ' ')}`, needsReasonFor(item.status, to))
}

function openReasonModal(kind: 'stage' | 'item', id: string, to: string, summary: string, needsReason: boolean) {
  modalError.value = ''
  reasonForm.reason = ''
  reasonModal.value = { kind, id, to, summary, needsReason }
}

async function confirmReasonTransition() {
  if (!reasonModal.value) return
  modalError.value = ''
  const { kind, id, to } = reasonModal.value
  const payload = { to_status: to, reason: reasonForm.reason.trim() || null }
  try {
    if (kind === 'stage') {
      await api.post(`/api/v1/tasks/${props.task.id}/stages/${id}/transition`, payload)
    } else {
      await api.post(`/api/v1/tasks/${props.task.id}/items/${id}/transition`, payload)
    }
    reasonModal.value = null
    await refreshAll()
  } catch (err) {
    modalError.value = err instanceof Error ? err.message : 'The transition was rejected.'
  }
}

async function deleteStage(stage: WorkflowStage) {
  if (!confirm(`Delete stage “${stage.name}”? This only works for empty, never-started stages.`)) return
  try {
    await api.delete(`/api/v1/tasks/${props.task.id}/stages/${stage.id}`)
    await refreshAll()
  } catch (err) {
    panelError.value = err instanceof Error ? err.message : 'The stage could not be deleted.'
  }
}

const itemModal = ref<{ stage: WorkflowStage, existing: WorkItem | null } | null>(null)
const itemForm = reactive({
  item_type: 'subtask' as WorkItemType,
  title: '',
  parent_work_item_id: '' as string | null,
  weight: 1,
  is_required: true,
  start_date: '',
  due_date: '',
})

function openItemModal(stage: WorkflowStage, existing?: WorkItem) {
  modalError.value = ''
  itemModal.value = { stage, existing: existing ?? null }
  itemForm.item_type = existing?.item_type ?? 'subtask'
  itemForm.title = existing?.title ?? ''
  itemForm.parent_work_item_id = existing?.parent_work_item_id ?? ''
  itemForm.weight = existing?.weight ?? 1
  itemForm.is_required = existing?.is_required ?? true
  itemForm.start_date = existing?.start_date ?? ''
  itemForm.due_date = existing?.due_date ?? ''
}

async function submitItem() {
  if (!itemModal.value) return
  modalError.value = ''
  const { stage, existing } = itemModal.value
  try {
    if (existing) {
      await api.patch(`/api/v1/tasks/${props.task.id}/items/${existing.id}`, {
        title: itemForm.title.trim(),
        weight: itemForm.weight,
        is_required: itemForm.is_required,
        start_date: itemForm.start_date || null,
        due_date: itemForm.due_date || null,
        version: existing.version,
      })
    } else {
      await api.post(`/api/v1/tasks/${props.task.id}/stages/${stage.id}/items`, {
        item_type: itemForm.item_type,
        title: itemForm.title.trim(),
        parent_work_item_id: itemForm.item_type === 'subtask' ? (itemForm.parent_work_item_id || null) : null,
        weight: itemForm.weight,
        is_required: itemForm.is_required,
        start_date: itemForm.start_date || null,
        due_date: itemForm.due_date || null,
      })
    }
    itemModal.value = null
    await refreshAll()
  } catch (err) {
    modalError.value = err instanceof Error ? err.message : 'The work item was rejected.'
  }
}

async function deleteItem(item: WorkItem) {
  if (!confirm(`Delete work item “${item.title}”? Only pending/cancelled items without dependencies can be deleted.`)) return
  try {
    await api.delete(`/api/v1/tasks/${props.task.id}/items/${item.id}`)
    await refreshAll()
  } catch (err) {
    panelError.value = err instanceof Error ? err.message : 'The work item could not be deleted.'
  }
}

const assignModal = ref<{ item: WorkItem } | null>(null)
const assignForm = reactive({ user_id: '' })

function openAssignModal(item: WorkItem) {
  modalError.value = ''
  assignModal.value = { item }
  assignForm.user_id = item.assigned_user_id ?? ''
}

async function submitAssign() {
  if (!assignModal.value) return
  modalError.value = ''
  try {
    await api.post(`/api/v1/tasks/${props.task.id}/items/${assignModal.value.item.id}/assign`, {
      assigned_user_id: assignForm.user_id || null,
    })
    assignModal.value = null
    await refreshAll()
  } catch (err) {
    modalError.value = err instanceof Error ? err.message : 'The assignment was rejected.'
  }
}

const depForm = reactive({ predecessor_id: '', successor_id: '' })

async function addDependency() {
  if (!depForm.successor_id || !depForm.predecessor_id) {
    panelError.value = 'Select both work items to link the dependency.'
    return
  }
  try {
    await api.post(`/api/v1/tasks/${props.task.id}/dependencies`, {
      predecessor_id: depForm.predecessor_id,
      successor_id: depForm.successor_id,
    })
    depForm.predecessor_id = ''
    depForm.successor_id = ''
    await refreshAll()
  } catch (err) {
    panelError.value = err instanceof Error ? err.message : 'The dependency was rejected.'
  }
}

async function removeDependency(dep: WorkflowDependency) {
  try {
    await api.delete(`/api/v1/tasks/${props.task.id}/dependencies/${dep.id}`)
    await refreshAll()
  } catch (err) {
    panelError.value = err instanceof Error ? err.message : 'The dependency could not be removed.'
  }
}

function stageStatusLabel(s: string): string {
  return s.replaceAll('_', ' ')
}
function stageStatusTone(s: string): 'green' | 'amber' | 'gray' | 'rose' {
  if (s === 'completed') return 'green'
  if (s === 'in_progress') return 'amber'
  if (s === 'cancelled') return 'rose'
  return 'gray'
}
function itemStatusTone(s: string): 'green' | 'amber' | 'gray' | 'rose' {
  if (s === 'completed') return 'green'
  if (s === 'in_progress') return 'amber'
  if (s === 'cancelled') return 'rose'
  return 'gray'
}
function basisLabel(b: string): string {
  if (b === 'milestones_only') return 'milestones only'
  if (b === 'subtasks_only') return 'subtasks only'
  return b
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
</script>

<style scoped>
.stage-btn {
  border-radius: 0.5rem;
  border: 1px solid #e2e8f0;
  padding: 0.25rem 0.6rem;
  font-size: 0.6875rem;
  font-weight: 500;
  color: #475569;
}
.stage-btn:hover { background: #f1f5f9; }
.stage-btn.brand { border-color: #c7d2fe; color: #4f46e5; }
.stage-btn.brand:hover { background: #eef2ff; }
.stage-btn.danger { border-color: #fecdd3; color: #e11d48; }
.stage-btn.danger:hover { background: #fff1f2; }

.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 23, 42, 0.4);
  padding: 1rem;
}
.modal-card {
  width: 100%;
  max-width: 40rem;
  border-radius: 1rem;
  background: #fff;
  padding: 1.5rem;
  box-shadow: 0 20px 25px -5px rgb(0 0 0 / 0.1);
}
.field-label {
  display: block;
  font-size: 0.75rem;
  font-weight: 500;
  color: #475569;
}
.field {
  margin-top: 0.25rem;
  width: 100%;
  border-radius: 0.5rem;
  border: 1px solid #e2e8f0;
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
  outline: none;
}
.field:focus { border-color: #6366f1; }
.dep-select {
  margin-top: 0.25rem;
  border-radius: 0.5rem;
  border: 1px solid #e2e8f0;
  padding: 0.5rem 0.75rem;
  font-size: 0.8125rem;
  outline: none;
  max-width: 16rem;
}
.btn-ghost {
  border-radius: 0.5rem;
  border: 1px solid #e2e8f0;
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
  color: #334155;
}
.btn-ghost:hover { background: #f1f5f9; }
.btn-primary {
  border-radius: 0.5rem;
  background: #4f46e5;
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
  font-weight: 500;
  color: #fff;
}
.btn-primary:hover { background: #4338ca; }
</style>
