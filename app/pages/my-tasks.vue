<template>
  <div class="mx-auto max-w-7xl px-4 py-8 sm:px-6">
    <section class="card p-5 sm:p-6">
      <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 class="page-title">My Tasks</h1>
          <p class="page-subtitle">
            Quick access to the work assigned to you; the same engine-authorized set as the register.
          </p>
        </div>
        <div class="inline-flex rounded-xl border border-line bg-elevated p-1" role="tablist" aria-label="Task scope">
          <button
            v-for="option in scopeOptions"
            :key="option.value"
            type="button"
            role="tab"
            :aria-selected="scope === option.value"
            class="rounded-lg px-4 py-2 text-sm font-medium transition-colors"
            :class="scope === option.value ? 'bg-surface text-brand-700 dark:text-brand-300 shadow-sm' : 'text-muted hover:text-ink'"
            @click="switchScope(option.value)"
          >
            {{ option.label }}
          </button>
        </div>
      </div>
    </section>

    <section class="card mt-6">
      <div v-if="pending" class="p-10">
        <div class="space-y-2" aria-busy="true" aria-label="Loading tasks">
          <div v-for="i in 5" :key="i" class="h-10 animate-pulse rounded-lg bg-hover" />
        </div>
      </div>
      <div v-else-if="error" class="p-10 text-center text-sm text-rose-600 dark:text-rose-400">{{ error.message }}</div>

      <template v-else>
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-line text-sm">
            <thead>
              <tr class="table-head">
                <th class="px-6 py-4">Task</th>
                <th class="px-6 py-4">Status</th>
                <th class="px-6 py-4">Priority</th>
                <th class="px-6 py-4">Progress</th>
                <th class="px-6 py-4">Due date</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-line">
              <tr v-if="!page?.items.length">
                <td colspan="5">
                  <div class="empty-state">
                    <svg class="h-8 w-8 text-faint" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" aria-hidden="true">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25zM6.75 12h.008v.008H6.75V12zm0 3h.008v.008H6.75V15zm0 3h.008v.008H6.75V18z" />
                    </svg>
                    <p class="mt-2">No tasks in this scope yet.</p>
                  </div>
                </td>
              </tr>
              <tr v-for="task in page?.items" :key="task.id" class="transition-colors hover:bg-hover">
                <td class="px-6 py-4">
                  <NuxtLink :to="`/tasks/${task.id}`" class="font-medium text-ink hover:text-brand-700 dark:hover:text-brand-300">
                    {{ task.title }}
                  </NuxtLink>
                  <p class="mt-0.5 text-xs text-faint">
                    {{ task.task_number }}
                    <span v-if="task.department_names.length"> · {{ task.department_names.join(', ') }}</span>
                  </p>
                </td>
                <td class="px-6 py-4"><AppBadge :tone="statusTone(task.status)">{{ statusLabel(task.status) }}</AppBadge></td>
                <td class="px-6 py-4"><AppBadge :tone="priorityTone(task.priority)">{{ capitalize(task.priority) }}</AppBadge></td>
                <td class="px-6 py-4">
                  <div class="flex items-center gap-2">
                    <div class="h-1.5 w-24 overflow-hidden rounded-full bg-hover">
                      <div class="h-full rounded-full bg-brand-500" :style="{ width: `${task.percent_complete}%` }" />
                    </div>
                    <span class="text-xs text-muted">{{ task.percent_complete }}%</span>
                  </div>
                </td>
                <td class="px-6 py-4">
                  <span v-if="task.due_date" class="text-body">{{ formatDate(task.due_date) }}</span>
                  <AppBadge v-if="isOverdue(task.due_date, task.status)" tone="rose" class="ml-2">overdue</AppBadge>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="totalPages > 1" class="flex items-center justify-between border-t border-line px-6 py-4">
          <p class="text-xs text-muted">Page {{ page?.page }} of {{ totalPages }} · {{ page?.total }} task(s)</p>
          <div class="flex gap-2">
            <button
              type="button"
              class="btn-secondary px-3 py-1.5"
              :disabled="currentPage <= 1"
              aria-label="Previous page"
              @click="goTo(currentPage - 1)"
            >
              Previous
            </button>
            <button
              type="button"
              class="btn-secondary px-3 py-1.5"
              :disabled="currentPage >= totalPages"
              aria-label="Next page"
              @click="goTo(currentPage + 1)"
            >
              Next
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
  { value: 'all' as const, label: 'All visible' },
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

useHead({ title: 'My Tasks - DecOps' })
</script>
