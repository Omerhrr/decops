<template>
  <div class="mx-auto max-w-7xl px-4 py-8 sm:px-6">
    <section class="rounded-2xl border border-line bg-surface p-6 sm:p-8">
      <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 class="text-xl font-semibold text-ink">CSV Import Center</h1>
          <p class="mt-1 max-w-2xl text-sm text-muted">
            Migrate legacy spreadsheets: map columns, preview normalized rows, resolve people,
            and commit only validated records. Invalid rows are reported, never discarded;
            duplicates are detected and excluded; commits are retry-safe.
          </p>
        </div>
        <label
          v-if="canManage"
          class="inline-flex cursor-pointer items-center justify-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-brand-700 disabled:opacity-50"
          :class="{ 'pointer-events-none': uploading }"
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.8"
               stroke="currentColor" class="h-4 w-4" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round"
                  d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z" />
          </svg>
          {{ uploading ? 'Validating…' : 'Upload legacy CSV' }}
          <input type="file" accept=".csv" class="hidden" @change="onFilePicked">
        </label>
      </div>
      <p v-if="uploadError" class="mt-3 rounded-lg bg-rose-50 dark:bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
        {{ uploadError }}
      </p>
    </section>

    <!-- Not authorized -->
    <section v-if="!canView" class="mt-6 rounded-2xl border border-line bg-surface p-10 text-center">
      <p class="text-sm font-medium text-body">No import access</p>
      <p class="mt-1 text-sm text-faint">
        The import center requires the <code>imports.view</code> or <code>imports.manage</code> permission.
      </p>
    </section>

    <template v-if="canView">
      <!-- Import history -->
      <section class="mt-6 rounded-2xl border border-line bg-surface p-6" aria-label="Import history">
        <h2 class="text-base font-semibold text-ink">Import history</h2>
        <p class="mt-1 text-sm text-muted">Every upload is recorded with its reconciliation counters.</p>
        <div v-if="!jobs.length" class="mt-4 rounded-xl bg-elevated p-6 text-center text-sm text-faint">
          No imports yet - upload a legacy CSV to begin.
        </div>
        <div v-else class="mt-4 overflow-x-auto">
          <table class="min-w-full text-left text-sm">
            <thead>
              <tr class="border-b border-line text-xs uppercase tracking-wide text-faint">
                <th class="py-2 pr-4 font-medium">File</th>
                <th class="py-2 pr-4 font-medium">Status</th>
                <th class="py-2 pr-4 font-medium">Rows</th>
                <th class="py-2 pr-4 font-medium">Committed</th>
                <th class="py-2 pr-4 font-medium">Uploaded</th>
                <th class="py-2 pr-4 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="job in jobs" :key="job.id"
                class="cursor-pointer border-b border-line hover:bg-hover"
                @click="selectJob(job.id)"
              >
                <td class="py-3 pr-4 font-medium text-ink">
                  {{ job.filename }}
                  <span v-if="selectedId === job.id" class="ml-2 text-xs text-brand-600 dark:text-brand-400">Viewing</span>
                </td>
                <td class="py-3 pr-4"><span :class="statusChip(job.status)" class="rounded-full px-2 py-0.5 text-xs font-medium">{{ capitalize(job.status) }}</span></td>
                <td class="py-3 pr-4 text-body">
                  {{ job.total_rows }} total
                  <span class="text-emerald-600 dark:text-emerald-400">{{ job.successful_rows }} ok</span>,
                  <span class="text-amber-600 dark:text-amber-400">{{ job.warning_rows }} warn</span>,
                  <span class="text-rose-600 dark:text-rose-400">{{ job.failed_rows }} failed</span>
                </td>
                <td class="py-3 pr-4 text-body">
                  {{ job.committed_rows }}
                  <span v-if="job.already_committed_rows" class="text-faint">(+{{ job.already_committed_rows }} retry-skip)</span>
                </td>
                <td class="py-3 pr-4 text-muted">{{ formatDate(job.created_at) }}</td>
                <td class="py-3 pr-4 text-right">
                  <button
                    type="button"
                    class="text-xs font-medium text-brand-600 dark:text-brand-400 hover:text-brand-700 dark:hover:text-brand-300"
                    @click.stop="downloadSummary(job.id)"
                  >summary.csv</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- Selected job detail -->
      <section v-if="selected" class="mt-6 rounded-2xl border border-line bg-surface p-6">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 class="text-base font-semibold text-ink">
              {{ selected.filename }}
              <span :class="statusChip(selected.status)" class="ml-2 rounded-full px-2 py-0.5 text-xs font-medium">{{ capitalize(selected.status) }}</span>
            </h2>
            <p class="mt-1 text-sm text-muted">
              Uploaded {{ formatDate(selected.created_at) }}
              <template v-if="selected.completed_at"> · committed {{ formatDate(selected.completed_at) }}</template>
              · by {{ selected.uploaded_by_email }}
            </p>
          </div>
          <div v-if="canManage && selected.status === 'validated'" class="flex gap-2">
            <button
              type="button"
              class="btn-primary"
              :disabled="committing"
              @click="commitSelected"
            >
              {{ committing ? 'Committing…' : `Commit ${committableCount} rows` }}
            </button>
          </div>
        </div>

        <p v-if="actionError" class="mt-4 rounded-lg bg-rose-50 dark:bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
          {{ actionError }}
        </p>

        <!-- Counters -->
        <div class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
          <div class="rounded-xl bg-elevated p-3 text-center">
            <p class="text-lg font-semibold text-ink">{{ selected.total_rows }}</p>
            <p class="text-xs text-faint">total rows</p>
          </div>
          <div class="rounded-xl bg-emerald-50 dark:bg-emerald-500/10 p-3 text-center">
            <p class="text-lg font-semibold text-emerald-700 dark:text-emerald-300">{{ selected.successful_rows }}</p>
            <p class="text-xs text-emerald-600 dark:text-emerald-400">ok</p>
          </div>
          <div class="rounded-xl bg-amber-50 dark:bg-amber-500/10 p-3 text-center">
            <p class="text-lg font-semibold text-amber-700 dark:text-amber-300">{{ selected.warning_rows }}</p>
            <p class="text-xs text-amber-600 dark:text-amber-400">warnings</p>
          </div>
          <div class="rounded-xl bg-rose-50 dark:bg-rose-500/10 p-3 text-center">
            <p class="text-lg font-semibold text-rose-700 dark:text-rose-300">{{ selected.failed_rows }}</p>
            <p class="text-xs text-rose-600 dark:text-rose-400">failed</p>
          </div>
          <div class="rounded-xl bg-elevated p-3 text-center">
            <p class="text-lg font-semibold text-ink">{{ selected.duplicate_rows }}</p>
            <p class="text-xs text-faint">duplicates</p>
          </div>
          <div class="rounded-xl bg-brand-50 dark:bg-brand-500/10 p-3 text-center">
            <p class="text-lg font-semibold text-brand-700 dark:text-brand-300">{{ selected.committed_rows }}</p>
            <p class="text-xs text-brand-600 dark:text-brand-400">committed</p>
          </div>
          <div class="rounded-xl bg-elevated p-3 text-center">
            <p class="text-lg font-semibold text-ink">{{ selected.already_committed_rows }}</p>
            <p class="text-xs text-faint">retry-skips</p>
          </div>
        </div>

        <p v-if="selected.file_level_errors" class="mt-4 rounded-lg bg-rose-50 dark:bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
          {{ selected.file_level_errors }}
        </p>

        <!-- Mapping editor -->
        <div v-if="report && canManage && selected.status !== 'committed'" class="mt-6">
          <h3 class="text-sm font-semibold text-ink">Column mapping</h3>
          <p class="mt-1 text-xs text-muted">
            Map each spreadsheet column to a DecOps field; "ignored" columns are reported but not imported.
          </p>
          <div class="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            <div v-for="header in report.headers" :key="header" class="flex items-center gap-2 rounded-lg border border-line px-3 py-2">
              <span class="w-40 truncate text-xs font-medium text-body" :title="header">{{ header }}</span>
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="h-3 w-3 shrink-0 text-faint" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
              </svg>
              <select
                v-model="mappingDraft[header]"
                class="min-w-0 flex-1 rounded-md border border-line bg-surface px-2 py-1 text-xs text-body"
              >
                <option :value="null">ignored</option>
                <option v-for="field in TARGET_FIELDS" :key="field" :value="field">{{ field }}</option>
              </select>
            </div>
          </div>

          <!-- Options -->
          <div class="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-xs text-body">
            <label class="flex items-center gap-2">
              <span>Initial visibility</span>
              <select v-model="optionsDraft.visibility_mode" class="select-field" aria-label="Initial visibility">
                <option value="participants">Participants</option>
                <option value="private">Private</option>
                <option value="department_scoped">Shared with departments</option>
                <option value="custom">Custom</option>
              </select>
            </label>
            <label class="flex items-center gap-2">
              <input v-model="optionsDraft.day_first" type="checkbox" class="h-3.5 w-3.5 accent-brand-600">
              Day-first dates (14/03/2025)
            </label>
            <label class="flex items-center gap-2">
              <input v-model="optionsDraft.match_title_due" type="checkbox" class="h-3.5 w-3.5 accent-brand-600">
              Duplicate rule: title + due date
            </label>
            <label class="flex items-center gap-2">
              <input v-model="optionsDraft.match_title_only" type="checkbox" class="h-3.5 w-3.5 accent-brand-600">
              Duplicate rule: title only
            </label>
            <label class="flex items-center gap-2">
              <input v-model="optionsDraft.reuse_task_number" type="checkbox" class="h-3.5 w-3.5 accent-brand-600">
              Keep original task IDs
            </label>
            <button
              type="button"
              class="rounded-lg border border-brand-200 bg-brand-50 dark:bg-brand-500/10 px-3 py-1.5 font-medium text-brand-700 dark:text-brand-300 hover:bg-brand-100 dark:hover:bg-brand-500/15 disabled:opacity-50"
              :disabled="applying"
              @click="applyConfig"
            >
              {{ applying ? 'Revalidating…' : 'Apply & revalidate' }}
            </button>
          </div>
        </div>

        <!-- Row report -->
        <div v-if="report" class="mt-6">
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-semibold text-ink">Row-level validation report</h3>
            <span class="text-xs text-faint">generated {{ formatDate(report.generated_at) }}</span>
          </div>
          <div class="mt-3 overflow-x-auto">
            <table class="min-w-full text-left text-sm">
              <thead>
                <tr class="border-b border-line text-xs uppercase tracking-wide text-faint">
                  <th class="py-2 pr-3 font-medium">#</th>
                  <th class="py-2 pr-3 font-medium">Source ID</th>
                  <th class="py-2 pr-3 font-medium">Title</th>
                  <th class="py-2 pr-3 font-medium">Validation</th>
                  <th class="py-2 pr-3 font-medium">Outcome</th>
                  <th class="py-2 pr-3 font-medium">Details</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in report.rows" :key="row.row_number" class="border-b border-line align-top">
                  <td class="py-2.5 pr-3 text-faint">{{ row.row_number }}</td>
                  <td class="py-2.5 pr-3 font-mono text-xs text-muted">{{ row.source_task_id || '-' }}</td>
                  <td class="max-w-[16rem] truncate py-2.5 pr-3 text-ink" :title="row.title">{{ row.title || '-' }}</td>
                  <td class="py-2.5 pr-3">
                    <span :class="rowChip(row.status)" class="rounded-full px-2 py-0.5 text-xs font-medium">{{ capitalize(row.status) }}</span>
                  </td>
                  <td class="py-2.5 pr-3 text-xs text-body">
                    <template v-if="row.outcome">
                      {{ row.outcome }}
                      <span v-if="row.committed_task_number" class="font-mono text-brand-600 dark:text-brand-400">{{ row.committed_task_number }}</span>
                    </template>
                    <template v-else> - </template>
                  </td>
                  <td class="py-2.5 pr-3 text-xs">
                    <p v-for="error in row.errors" :key="`e${error}`" class="text-rose-600 dark:text-rose-400">{{ error }}</p>
                    <p v-for="notice in row.notices" :key="`n${notice}`" class="text-amber-600 dark:text-amber-400">{{ notice }}</p>
                    <p v-for="dup in row.duplicates" :key="`d${dup.task_number}${dup.kind}`" class="text-violet-600 dark:text-violet-400">
                      duplicate ({{ dup.kind }}) → {{ dup.task_number }}
                    </p>
                    <p v-if="!row.errors.length && !row.notices.length && !row.duplicates.length" class="text-faint">clean</p>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">

import type {
  ImportJobSummary,
  ImportOptions,
  ImportReport,
} from '~/types/api'

const TARGET_FIELDS = [
  'legacy_task_id', 'date_created', 'title', 'description', 'priority',
  'accountable_pm', 'supporting_pms', 'assigned_by', 'start_date', 'due_date',
  'status', 'percent_complete', 'last_updated', 'next_follow_up_date',
  'dependency_summary', 'attachment_folder_reference', 'completion_date',
] as const

const api = useApi()
const auth = useAuth()
const { confirm } = useConfirm()
const canManage = computed(() => auth.hasPermission('imports.manage'))
const canView = computed(() => auth.hasPermission('imports.view', 'imports.manage'))

const jobs = ref<ImportJobSummary[]>([])
const selectedId = ref<string | null>(null)
const selected = ref<ImportJobSummary | null>(null)
const report = ref<ImportReport | null>(null)
const uploading = ref(false)
const uploadError = ref('')
const committing = ref(false)
const applying = ref(false)
const actionError = ref('')

const mappingDraft = ref<Record<string, string | null>>({})
const optionsDraft = ref<ImportOptions>({
  visibility_mode: 'participants',
  day_first: true,
  match_title_due: true,
  match_title_only: false,
  reuse_task_number: true,
})

const committableCount = computed(() => {
  if (!report.value) return 0
  return report.value.rows.filter(
    r => r.status !== 'failed' && r.normalized && !r.normalized.duplicate_review && !r.outcome,
  ).length
})

onMounted(loadJobs)

async function loadJobs() {
  try {
    jobs.value = await api.get<ImportJobSummary[]>('/api/v1/imports')
  } catch {
    jobs.value = []
  }
}

async function selectJob(id: string) {
  selectedId.value = id
  selected.value = null
  report.value = null
  actionError.value = ''
  try {
    selected.value = await api.get<ImportJobSummary>(`/api/v1/imports/${id}`)
    report.value = await api.get<ImportReport>(`/api/v1/imports/${id}/report`)
    mappingDraft.value = { ...report.value.mapping }
    const opts = (report.value as unknown as { options?: ImportOptions }).options
    if (opts) optionsDraft.value = { ...optionsDraft.value, ...opts }
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : 'Failed to load the import job.'
  }
}

async function onFilePicked(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  uploading.value = true
  uploadError.value = ''
  try {
    const form = new FormData()
    form.append('file', file)
    const created = await $fetch.raw('/api/v1/imports/csv', {
      method: 'POST',
      body: form,
      credentials: 'include',
      ignoreResponseError: true,
    })
    if (created.status >= 400) {
      const body = (created._data ?? { error: { message: 'Upload failed.' } }) as { error: { message: string } }
      uploadError.value = body.error?.message ?? 'Upload failed.'
      return
    }
    await loadJobs()
    const job = created._data as ImportJobSummary
    await selectJob(job.id)
  } finally {
    uploading.value = false
  }
}

async function applyConfig() {
  if (!selected.value) return
  applying.value = true
  actionError.value = ''
  try {
    selected.value = await api.patch<ImportJobSummary>(`/api/v1/imports/${selected.value.id}`, {
      mapping: { ...mappingDraft.value },
      options: { ...optionsDraft.value },
    })
    report.value = await api.get<ImportReport>(`/api/v1/imports/${selected.value.id}/report`)
    mappingDraft.value = { ...report.value.mapping }
    await loadJobs()
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : 'Revalidation failed.'
  } finally {
    applying.value = false
  }
}

async function commitSelected() {
  if (!selected.value) return
  const confirmed = await confirm({
    title: 'Commit import',
    message: `Commit ${committableCount.value} validated rows into DecOps? Failed rows and duplicates are excluded; this job cannot be committed twice.`,
    confirmLabel: 'Commit rows',
  })
  if (!confirmed) return
  committing.value = true
  actionError.value = ''
  try {
    await api.post(`/api/v1/imports/${selected.value.id}/commit`)
    await selectJob(selected.value.id)
    await loadJobs()
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : 'Commit failed.'
  } finally {
    committing.value = false
  }
}

async function downloadSummary(jobId: string) {
  const { blob, filename } = await api.downloadGet(`/api/v1/imports/${jobId}/report/download`)
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

function statusChip(status: string): string {
  switch (status) {
    case 'committed': return 'bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
    case 'validated': return 'bg-sky-50 dark:bg-sky-500/10 text-sky-700 dark:text-sky-300'
    case 'failed': return 'bg-rose-50 dark:bg-rose-500/10 text-rose-700 dark:text-rose-300'
    default: return 'bg-hover text-body'
  }
}

function rowChip(status: string): string {
  switch (status) {
    case 'ok': return 'bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
    case 'warning': return 'bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300'
    default: return 'bg-rose-50 dark:bg-rose-500/10 text-rose-700 dark:text-rose-300'
  }
}

function formatDate(value: string | null): string {
  if (!value) return '-'
  return new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}
</script>
