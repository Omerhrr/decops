<template>
  <div class="mx-auto max-w-7xl px-4 py-8 sm:px-6">
    <section class="rounded-2xl border border-line bg-surface p-6 sm:p-8">
      <h1 class="text-xl font-semibold text-ink">Department workspace</h1>
      <p class="mt-1 text-sm text-muted">
        {{ workload?.scope === 'all'
          ? 'All departments (management reporting scope).'
          : 'Departments you lead or belong to.' }}
        Task contents inside each workspace are still filtered by your task access policies.
      </p>
    </section>

    <!-- Dynamic body is client-only: the department-workload fetch is
         client-side, and resolving before hydration would race the SSR tree. -->
    <ClientOnly>
      <div v-if="pending" class="mt-6 rounded-2xl border border-line bg-surface p-10 text-center text-sm text-faint">
        Loading departments…
      </div>

      <div v-else-if="error" class="mt-6 rounded-2xl border border-line bg-surface p-10 text-center">
        <p class="text-sm font-medium text-body">No department reporting access</p>
        <p class="mt-1 text-sm text-faint">
          Department workspaces require the <code>reports.view</code> or <code>reports.department.view</code> permission.
        </p>
      </div>
    <div v-else-if="workload" class="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <NuxtLink
        v-for="row in workload.departments"
        :key="row.department_id"
        :to="`/departments/${row.department_id}`"
        class="group rounded-2xl border border-line bg-surface p-6 transition-all hover:border-brand-300 hover:shadow-md"
      >
        <div class="flex items-start justify-between">
          <div>
            <h2 class="text-base font-semibold text-ink group-hover:text-brand-700 dark:hover:text-brand-300">{{ row.department_name }}</h2>
            <p class="mt-0.5 text-xs text-faint">Lead: {{ row.lead ?? '-' }} · {{ row.member_count }} member(s)</p>
          </div>
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="h-5 w-5 text-faint transition-colors group-hover:text-brand-500" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
          </svg>
        </div>
        <div class="mt-4 grid grid-cols-4 gap-2 text-center">
          <div class="rounded-lg bg-elevated py-2">
            <p class="text-lg font-semibold text-ink">{{ row.active_tasks }}</p>
            <p class="text-[10px] uppercase tracking-wide text-faint">Active</p>
          </div>
          <div class="rounded-lg bg-elevated py-2">
            <p class="text-lg font-semibold" :class="row.overdue_tasks ? 'text-rose-600 dark:text-rose-400' : 'text-ink'">{{ row.overdue_tasks }}</p>
            <p class="text-[10px] uppercase tracking-wide text-faint">Overdue</p>
          </div>
          <div class="rounded-lg bg-elevated py-2">
            <p class="text-lg font-semibold" :class="row.blocked_tasks ? 'text-amber-600 dark:text-amber-400' : 'text-ink'">{{ row.blocked_tasks }}</p>
            <p class="text-[10px] uppercase tracking-wide text-faint">Blocked</p>
          </div>
          <div class="rounded-lg bg-elevated py-2">
            <p class="text-lg font-semibold text-ink">{{ row.completed_tasks }}</p>
            <p class="text-[10px] uppercase tracking-wide text-faint">Done</p>
          </div>
        </div>
        <p class="mt-3 text-xs text-faint">{{ row.open_assignments }} open assignment(s) across the team</p>
      </NuxtLink>

      <div v-if="!workload.departments.length" class="rounded-2xl border border-line bg-surface p-10 text-center text-sm text-faint sm:col-span-2 lg:col-span-3">
        No departments in your reporting scope.
      </div>
    </div>
    </ClientOnly>
  </div>
</template>

<script setup lang="ts">
import type { DepartmentWorkloadReport } from '~/types/api'

const { data: workload, pending, error } = await useFetch<DepartmentWorkloadReport>('/api/v1/reports/department-workload', {
  server: false,
})

useHead({ title: 'Departments - DecOps' })
</script>
