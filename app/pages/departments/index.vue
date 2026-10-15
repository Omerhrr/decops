<template>
  <div class="mx-auto max-w-7xl px-4 py-8 sm:px-6">
    <section class="rounded-2xl border border-slate-200 bg-white p-6 sm:p-8">
      <h1 class="text-xl font-semibold text-slate-900">Department workspace</h1>
      <p class="mt-1 text-sm text-slate-500">
        {{ workload?.scope === 'all'
          ? 'All departments (management reporting scope).'
          : 'Departments you lead or belong to.' }}
        Task contents inside each workspace are still filtered by your task access policies.
      </p>
    </section>

    <!-- Dynamic body is client-only: the department-workload fetch is
         client-side, and resolving before hydration would race the SSR tree. -->
    <ClientOnly>
      <div v-if="pending" class="mt-6 rounded-2xl border border-slate-200 bg-white p-10 text-center text-sm text-slate-400">
        Loading departments…
      </div>

      <div v-else-if="error" class="mt-6 rounded-2xl border border-slate-200 bg-white p-10 text-center">
        <p class="text-sm font-medium text-slate-700">No department reporting access</p>
        <p class="mt-1 text-sm text-slate-400">
          Department workspaces require the <code>reports.view</code> or <code>reports.department.view</code> permission.
        </p>
      </div>
    <div v-else-if="workload" class="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <NuxtLink
        v-for="row in workload.departments"
        :key="row.department_id"
        :to="`/departments/${row.department_id}`"
        class="group rounded-2xl border border-slate-200 bg-white p-6 transition-all hover:border-brand-300 hover:shadow-md"
      >
        <div class="flex items-start justify-between">
          <div>
            <h2 class="text-base font-semibold text-slate-900 group-hover:text-brand-700">{{ row.department_name }}</h2>
            <p class="mt-0.5 text-xs text-slate-400">Lead: {{ row.lead ?? '—' }} · {{ row.member_count }} member(s)</p>
          </div>
          <span class="text-slate-300 transition-colors group-hover:text-brand-500">→</span>
        </div>
        <div class="mt-4 grid grid-cols-4 gap-2 text-center">
          <div class="rounded-lg bg-slate-50 py-2">
            <p class="text-lg font-semibold text-slate-900">{{ row.active_tasks }}</p>
            <p class="text-[10px] uppercase tracking-wide text-slate-400">Active</p>
          </div>
          <div class="rounded-lg bg-slate-50 py-2">
            <p class="text-lg font-semibold" :class="row.overdue_tasks ? 'text-rose-600' : 'text-slate-900'">{{ row.overdue_tasks }}</p>
            <p class="text-[10px] uppercase tracking-wide text-slate-400">Overdue</p>
          </div>
          <div class="rounded-lg bg-slate-50 py-2">
            <p class="text-lg font-semibold" :class="row.blocked_tasks ? 'text-amber-600' : 'text-slate-900'">{{ row.blocked_tasks }}</p>
            <p class="text-[10px] uppercase tracking-wide text-slate-400">Blocked</p>
          </div>
          <div class="rounded-lg bg-slate-50 py-2">
            <p class="text-lg font-semibold text-slate-900">{{ row.completed_tasks }}</p>
            <p class="text-[10px] uppercase tracking-wide text-slate-400">Done</p>
          </div>
        </div>
        <p class="mt-3 text-xs text-slate-400">{{ row.open_assignments }} open assignment(s) across the team</p>
      </NuxtLink>

      <div v-if="!workload.departments.length" class="rounded-2xl border border-slate-200 bg-white p-10 text-center text-sm text-slate-400 sm:col-span-2 lg:col-span-3">
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

useHead({ title: 'Departments — DecOps' })
</script>
