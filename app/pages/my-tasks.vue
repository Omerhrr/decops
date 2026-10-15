<template>
  <div class="mx-auto max-w-7xl px-4 py-8 sm:px-6">
    <section class="rounded-2xl border border-slate-200 bg-white p-6 sm:p-8">
      <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 class="text-xl font-semibold text-slate-900">My Tasks</h1>
          <p class="mt-1 text-sm text-slate-500">
            Quick access to the work assigned to you — the same engine-authorized set as the register.
          </p>
        </div>
        <!-- Scope switch -->
        <div class="inline-flex rounded-xl border border-slate-200 bg-slate-50 p-1" role="tablist" aria-label="Task scope">
          <button
            v-for="option in scopeOptions"
            :key="option.value"
            type="button"
            role="tab"
            :aria-selected="scope === option.value"
            class="rounded-lg px-4 py-2 text-sm font-medium transition-colors"
            :class="scope === option.value ? 'bg-white text-brand-700 shadow-sm' : 'text-slate-500 hover:text-slate-800'"
            @click="switchScope(option.value)"
          >
            {{ option.label }}
          </button>
        </div>
      </div>
    </section>

    <section class="mt-6 rounded-2xl border border-slate-200 bg-white">
      <div v-if="pending" class="p-10 text-center text-sm text-slate-400">Loading tasks…</div>
      <div v-else-if="error" class="p-10 text-center text-sm text-rose-600">{{ error.message }}</div>

      <template v-else>
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-slate-200 text-sm">
            <thead>
              <tr class="text-left text-xs font-semibold uppercase tracking-wide text-slate-400">
                <th class="px-6 py-4">Task</th>
                <th class="px-6 py-4">Status</th>
                <th class="px-6 py-4">Priority</th>
                <th class="px-6 py-4">Progress</th>
                <th class="px-6 py-4">Due date</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-if="!page?.items.length">
                <td colspan="5" class="px-6 py-10 text-center text-slate-400">
                  No tasks in this scope yet.
                </td>
              </tr>
              <tr v-for="task in page?.items" :key="task.id" class="transition-colors hover:bg-slate-50">
                <td class="px-6 py-4">
                  <NuxtLink :to="`/tasks/${task.id}`" class="font-medium text-slate-800 hover:text-brand-700">
                    {{ task.title }}
                  </NuxtLink>
                  <p class="mt-0.5 text-xs text-slate-400">
                    {{ task.task_number }}
                    <span v-if="task.department_names.length"> · {{ task.department_names.join(', ') }}</span>
                  </p>
                </td>
                <td class="px-6 py-4"><AppBadge :tone="statusTone(task.status)">{{ prettyStatus(task.status) }}</AppBadge></td>
                <td class="px-6 py-4"><AppBadge :tone="priorityTone(task.priority)">{{ task.priority }}</AppBadge></td>
                <td class="px-6 py-4">
                  <div class="flex items-center gap-2">
                    <div class="h-1.5 w-24 overflow-hidden rounded-full bg-slate-100">
                      <div class="h-full rounded-full bg-brand-500" :style="{ width: `${task.percent_complete}%` }" />
                    </div>
                    <span class="text-xs text-slate-500">{{ task.percent_complete }}%</span>
                  </div>
                </td>
                <td class="px-6 py-4">
                  <span v-if="task.due_date" class="text-slate-600">{{ formatDate(task.due_date) }}</span>
                  <AppBadge v-if="isOverdue(task)" tone="rose" class="ml-2">overdue</AppBadge>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Pagination -->
        <div v-if="totalPages > 1" class="flex items-center justify-between border-t border-slate-100 px-6 py-4">
          <p class="text-xs text-slate-400">Page {{ page?.page }} of {{ totalPages }} · {{ page?.total }} task(s)</p>
          <div class="flex gap-2">
            <button
              type="button"
              class="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 disabled:opacity-40"
              :disabled="currentPage <= 1"
              @click="goTo(currentPage - 1)"
            >
              ← Previous
            </button>
            <button
              type="button"
              class="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 disabled:opacity-40"
              :disabled="currentPage >= totalPages"
              @click="goTo(currentPage + 1)"
            >
              Next →
            </button>
          </div>
        </div>
      </template>
    </section>
  </div>
</template>

<script setup lang="ts">
import type { MyTaskPage } from '~/types/api'

const scopeOptions = [
  { value: 'assigned' as const, label: 'Assigned to me' },
  { value: 'accountable' as const, label: 'I am accountable' },
  { value: 'all' as const, label: 'Everything' },
]

const route = useRoute()
const router = useRouter()

const scope = computed<'assigned' | 'accountable' | 'all'>(() => {
  const raw = String(route.query.scope ?? 'assigned')
  return raw === 'accountable' || raw === 'all' ? raw : 'assigned'
})
const currentPage = computed(() => Math.max(1, Number(route.query.page ?? 1)))

function switchScope(value: 'assigned' | 'accountable' | 'all') {
  router.push({ query: { scope: value, page: 1 } })
}

function goTo(page: number) {
  router.push({ query: { scope: scope.value, page } })
}

const { data: page, pending, error } = await useFetch<MyTaskPage>('/api/v1/dashboard/my-tasks', {
  query: { scope, page: currentPage, page_size: 10 },
})

const totalPages = computed(() => {
  if (!page.value) return 1
  return Math.max(1, Math.ceil(page.value.total / page.value.page_size))
})

function statusTone(status: string): 'green' | 'amber' | 'gray' | 'rose' {
  if (status === 'completed') return 'green'
  if (status === 'blocked') return 'rose'
  if (status === 'in_progress' || status === 'under_review') return 'amber'
  return 'gray'
}

function priorityTone(priority: string): 'green' | 'amber' | 'gray' | 'rose' {
  if (priority === 'critical') return 'rose'
  if (priority === 'high') return 'amber'
  if (priority === 'low') return 'gray'
  return 'green'
}

function prettyStatus(status: string): string {
  return status.replace(/_/g, ' ')
}

function isOverdue(task: { status: string, due_date: string | null }): boolean {
  if (!task.due_date || ['completed', 'cancelled', 'archived'].includes(task.status)) return false
  return new Date(`${task.due_date}T23:59:59`) < new Date()
}

function formatDate(value: string): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

useHead({ title: 'My Tasks — DecOps' })
</script>
