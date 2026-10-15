<template>
  <div class="mx-auto max-w-7xl px-4 py-8 sm:px-6">
    <section class="rounded-2xl border border-slate-200 bg-white p-6 sm:p-8">
      <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 class="text-xl font-semibold text-slate-900">Reports</h1>
          <p class="mt-1 text-sm text-slate-500">
            Authorized reporting only - every figure is computed from the tasks your access
            policy allows, and exports are audited.
          </p>
        </div>
        <div v-if="auth.hasPermission('exports.approved')" class="flex flex-wrap gap-2">
          <button
            v-for="option in exportOptions"
            :key="option.type"
            type="button"
            class="rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-sm font-medium text-brand-700 transition-colors hover:bg-brand-100 disabled:opacity-50"
            :disabled="exporting === option.type"
            @click="runExport(option.type)"
          >
            {{ exporting === option.type ? 'Preparing…' : option.label }}
          </button>
        </div>
      </div>
    </section>

    <!-- Not authorized -->
    <section v-if="!canSeeCompletion && !canSeeWorkload" class="mt-6 rounded-2xl border border-slate-200 bg-white p-10 text-center">
      <p class="text-sm font-medium text-slate-700">No reporting access</p>
      <p class="mt-1 text-sm text-slate-400">
        Reporting requires the <code>reports.view</code> or <code>reports.department.view</code> permission.
        {{ auth.hasPermission('exports.approved') ? 'You can still use the export buttons above.' : '' }}
      </p>
    </section>

    <div class="mt-6 grid grid-cols-1 gap-6">
      <!-- Completion trend -->
      <section v-if="canSeeCompletion" class="rounded-2xl border border-slate-200 bg-white p-6" aria-label="Task completion report">
        <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 class="text-base font-semibold text-slate-900">Task completion trend</h2>
            <p class="mt-1 text-sm text-slate-500">
              Created vs completed per week over the last {{ completion?.weeks }} weeks.
            </p>
          </div>
          <div v-if="completion" class="flex flex-wrap gap-4 text-xs text-slate-500">
            <span><span class="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-brand-500" /> Completed</span>
            <span><span class="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-slate-300" /> Created</span>
            <span>Avg cycle: <strong>{{ completion.avg_days_to_complete ?? '-' }}d</strong></span>
          </div>
        </div>

        <div v-if="completion" class="mt-6">
          <!-- SVG bar chart: created/completed per week -->
          <svg :viewBox="`0 0 ${chartWidth} ${chartHeight}`" class="h-56 w-full" role="img" aria-label="Weekly completion chart">
            <line v-for="tick in 5" :key="tick"
                  :x1="chartPad" :x2="chartWidth - 8"
                  :y1="chartPad + (chartHeight - chartPad * 2) * (tick - 1) / 4"
                  :y2="chartPad + (chartHeight - chartPad * 2) * (tick - 1) / 4"
                  stroke="#e2e8f0" stroke-width="1" />
            <g v-for="(point, i) in completion.series" :key="point.week_start">
              <rect
                :x="weekX(i) - barGap" :y="yFor(point.created)" :width="barWidth"
                :height="Math.max(yZero - yFor(point.created), point.created ? 2 : 0)" rx="2" fill="#cbd5e1"
              ><title>{{ weekLabel(point.week_start) }}: {{ point.created }} created</title></rect>
              <rect
                :x="weekX(i) + barGap" :y="yFor(point.completed)" :width="barWidth"
                :height="Math.max(yZero - yFor(point.completed), point.completed ? 2 : 0)" rx="2" fill="#2563eb"
              ><title>{{ weekLabel(point.week_start) }}: {{ point.completed }} completed</title></rect>
              <text v-if="i % labelEvery === 0" :x="weekX(i)" :y="chartHeight - 6" text-anchor="middle" class="fill-slate-400" font-size="9">
                {{ shortWeek(point.week_start) }}
              </text>
            </g>
          </svg>

          <div class="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div class="rounded-xl bg-slate-50 p-4">
              <p class="text-xs font-medium uppercase tracking-wide text-slate-400">Completed in window</p>
              <p class="mt-1 text-xl font-semibold text-slate-900">{{ completion.totals.completed_in_window }}</p>
            </div>
            <div class="rounded-xl bg-slate-50 p-4">
              <p class="text-xs font-medium uppercase tracking-wide text-slate-400">Active now</p>
              <p class="mt-1 text-xl font-semibold text-slate-900">{{ completion.totals.active }}</p>
            </div>
            <div class="rounded-xl bg-slate-50 p-4">
              <p class="text-xs font-medium uppercase tracking-wide text-slate-400">Overdue</p>
              <p class="mt-1 text-xl font-semibold" :class="completion.totals.overdue ? 'text-rose-600' : 'text-slate-900'">
                {{ completion.totals.overdue }}
              </p>
            </div>
            <div class="rounded-xl bg-slate-50 p-4">
              <p class="text-xs font-medium uppercase tracking-wide text-slate-400">Milestones done</p>
              <p class="mt-1 text-xl font-semibold text-slate-900">
                {{ completion.milestone_progress.completed }}/{{ completion.milestone_progress.total }}
              </p>
            </div>
          </div>

          <!-- Blocker analysis -->
          <div class="mt-6 rounded-xl border border-slate-100 p-4">
            <h3 class="text-sm font-semibold text-slate-800">Blocker analysis</h3>
            <p class="mt-1 text-xs text-slate-500">
              {{ completion.blocker_analysis.blocked_total }} blocked task(s),
              {{ completion.blocker_analysis.overdue_blocked }} of them past due.
            </p>
            <div class="mt-3 flex flex-wrap gap-2">
              <AppBadge v-for="(count, priority) in completion.blocker_analysis.by_priority" :key="priority" tone="rose">
                {{ priority }}: {{ count }}
              </AppBadge>
              <AppBadge v-for="(count, dept) in completion.blocker_analysis.by_department" :key="dept" tone="amber">
                {{ dept }}: {{ count }}
              </AppBadge>
              <span v-if="!completion.blocker_analysis.blocked_total" class="text-xs text-slate-400">Nothing blocked.</span>
            </div>
          </div>
        </div>
      </section>

      <!-- Department workload -->
      <section v-if="canSeeWorkload" class="rounded-2xl border border-slate-200 bg-white p-6" aria-label="Department workload report">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-base font-semibold text-slate-900">Department workload</h2>
            <p class="mt-1 text-sm text-slate-500">
              {{ workload?.scope === 'all' ? 'All departments (management scope).' : 'Departments you lead or belong to.' }}
            </p>
          </div>
          <NuxtLink to="/departments" class="text-sm font-medium text-brand-700 hover:underline">
            Open workspaces →
          </NuxtLink>
        </div>

        <div class="mt-4 overflow-x-auto">
          <table class="min-w-full divide-y divide-slate-200 text-sm">
            <thead>
              <tr class="text-left text-xs font-semibold uppercase tracking-wide text-slate-400">
                <th class="px-4 py-3">Department</th>
                <th class="px-4 py-3">Lead</th>
                <th class="px-4 py-3">Members</th>
                <th class="px-4 py-3">Active</th>
                <th class="px-4 py-3">Overdue</th>
                <th class="px-4 py-3">Blocked</th>
                <th class="px-4 py-3">Completed</th>
                <th class="px-4 py-3">Assignments</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-if="!workload?.departments.length">
                <td colspan="8" class="px-4 py-8 text-center text-slate-400">No departments in your reporting scope.</td>
              </tr>
              <tr v-for="row in workload?.departments" :key="row.department_id" class="transition-colors hover:bg-slate-50">
                <td class="px-4 py-3">
                  <NuxtLink :to="`/departments/${row.department_id}`" class="font-medium text-slate-800 hover:text-brand-700">
                    {{ row.department_name }}
                  </NuxtLink>
                </td>
                <td class="px-4 py-3 text-slate-600">{{ row.lead ?? '-' }}</td>
                <td class="px-4 py-3 text-slate-600">{{ row.member_count }}</td>
                <td class="px-4 py-3 text-slate-900">{{ row.active_tasks }}</td>
                <td class="px-4 py-3">
                  <span :class="row.overdue_tasks ? 'font-semibold text-rose-600' : 'text-slate-600'">{{ row.overdue_tasks }}</span>
                </td>
                <td class="px-4 py-3">
                  <span :class="row.blocked_tasks ? 'font-semibold text-amber-600' : 'text-slate-600'">{{ row.blocked_tasks }}</span>
                </td>
                <td class="px-4 py-3 text-slate-600">{{ row.completed_tasks }}</td>
                <td class="px-4 py-3 text-slate-600">{{ row.open_assignments }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { TaskCompletionReport, DepartmentWorkloadReport } from '~/types/api'

const auth = useAuth()
const api = useApi()

const canSeeCompletion = computed(() => auth.hasPermission('reports.view'))
const canSeeWorkload = computed(() => auth.hasPermission('reports.view', 'reports.department.view'))

const { data: completion } = await useFetch<TaskCompletionReport>('/api/v1/reports/task-completion', {
  query: { weeks: 12 },
  // 404 for users without reports.view - swallow into null instead of surfacing an error.
  server: false,
})
const { data: workload } = await useFetch<DepartmentWorkloadReport>('/api/v1/reports/department-workload', {
  server: false,
})

// ---- CSV exports (exports.approved; audited server-side) ----
const exportOptions = [
  { type: 'task_register', label: '⬇ Task register CSV' },
  { type: 'department_workload', label: '⬇ Department workload CSV' },
  { type: 'task_completion', label: '⬇ Completion trend CSV' },
] as const
const exporting = ref<string | null>(null)
const exportError = ref('')

async function runExport(type: string) {
  exporting.value = type
  exportError.value = ''
  try {
    const { blob, filename } = await api.download('/api/v1/reports/exports', { export_type: type })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  } catch (err) {
    exportError.value = err instanceof Error ? err.message : 'Export failed.'
  } finally {
    exporting.value = null
  }
}

// ---- Chart geometry ----
const chartWidth = 720
const chartHeight = 220
const chartPad = 16
const yZero = chartHeight - 22

const maxCount = computed(() => {
  if (!completion.value) return 1
  return Math.max(1, ...completion.value.series.map(p => Math.max(p.created, p.completed)))
})

const slotWidth = computed(() => (chartWidth - chartPad - 8) / Math.max(completion.value?.series.length ?? 1, 1))
const barWidth = computed(() => Math.min(14, slotWidth.value / 3))
const barGap = computed(() => barWidth.value / 2 + 2)
const labelEvery = computed(() => (completion.value?.series.length ?? 0) > 16 ? 4 : 2)

function weekX(index: number): number {
  return chartPad + slotWidth.value * (index + 0.5)
}

function yFor(count: number): number {
  const usable = yZero - chartPad
  return yZero - (count / maxCount.value) * usable
}

function weekLabel(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function shortWeek(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: 'numeric', day: 'numeric' })
}

useHead({ title: 'Reports - DecOps' })
</script>
