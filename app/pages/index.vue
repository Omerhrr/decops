<template>
  <div class="mx-auto max-w-7xl px-4 py-8 sm:px-6">
    <!-- Welcome -->
    <section class="rounded-2xl border border-slate-200 bg-white p-6 sm:p-8">
      <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 class="text-xl font-semibold text-slate-900">Welcome back, {{ firstName }}</h1>
          <p class="mt-1 text-sm text-slate-500">
            Signed in as {{ auth.user.value?.email }} · {{ auth.user.value?.employee_code }}
          </p>
        </div>
        <AppBadge tone="green">{{ systemHealth }}</AppBadge>
      </div>
    </section>

    <!-- Stat cards -->
    <section class="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Overview">
      <StatCard label="Assigned to me" value="—" icon="📋" note="Tasks module · Phase 4" />
      <StatCard label="Accountable for" value="—" icon="🎯" note="Tasks module · Phase 4" />
      <StatCard label="Overdue" value="—" icon="⏰" note="Dashboards · Phase 7" />
      <StatCard label="Blocked" value="—" icon="⛔" note="Workflow engine · Phase 5" />
    </section>

    <div class="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
      <!-- Roadmap -->
      <section class="rounded-2xl border border-slate-200 bg-white p-6 lg:col-span-2">
        <h2 class="text-base font-semibold text-slate-900">Implementation roadmap</h2>
        <p class="mt-1 text-sm text-slate-500">
          This foundation release ships authentication, RBAC seed data, audit logging,
          and database migrations. Remaining modules land in the phases below.
        </p>
        <ol class="mt-5 space-y-3">
          <li
            v-for="item in roadmap"
            :key="item.phase"
            class="flex items-start gap-3 rounded-xl border border-slate-100 p-3"
            :class="item.done ? 'bg-brand-50/50' : 'bg-white'"
          >
            <span
              class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold"
              :class="item.done ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-500'"
            >
              {{ item.phase }}
            </span>
            <div>
              <p class="text-sm font-medium text-slate-800">
                {{ item.name }}
                <AppBadge v-if="item.done" tone="green" class="ml-2">Shipped</AppBadge>
                <AppBadge v-else tone="gray" class="ml-2">Planned</AppBadge>
              </p>
              <p class="mt-0.5 text-xs text-slate-500">{{ item.detail }}</p>
            </div>
          </li>
        </ol>
      </section>

      <!-- Session / roles -->
      <section class="rounded-2xl border border-slate-200 bg-white p-6">
        <h2 class="text-base font-semibold text-slate-900">Your access</h2>
        <p class="mt-1 text-sm text-slate-500">Global roles and permissions resolved from the RBAC seed matrix.</p>

        <h3 class="mt-5 text-xs font-semibold uppercase tracking-wide text-slate-400">Roles</h3>
        <div class="mt-2 flex flex-wrap gap-2">
          <AppBadge v-for="role in auth.roleNames.value" :key="role" tone="green">{{ role }}</AppBadge>
          <span v-if="!auth.roleNames.value.length" class="text-sm text-slate-400">No roles assigned</span>
        </div>

        <h3 class="mt-5 text-xs font-semibold uppercase tracking-wide text-slate-400">Permissions ({{ auth.user.value?.permissions.length ?? 0 }})</h3>
        <div class="mt-2 max-h-56 space-y-1 overflow-y-auto rounded-lg bg-slate-50 p-3">
          <code
            v-for="perm in auth.user.value?.permissions ?? []"
            :key="perm"
            class="block text-xs text-slate-600"
          >
            {{ perm }}
          </code>
          <p v-if="!auth.user.value?.permissions.length" class="text-sm text-slate-400">No permissions resolved</p>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
const auth = useAuth()
const firstName = computed(() => auth.displayName.value.split(' ')[0] || 'there')

const { data: health } = await useFetch('/api/v1/health', { lazy: true })
const systemHealth = computed(() =>
  health.value ? `System: ${health.value.status} (${health.value.environment})` : 'System status unknown',
)

const roadmap = [
  { phase: 2, name: 'Application Foundation', detail: 'Auth, users/sessions, RBAC seeds, migrations, audit log, tests', done: true },
  { phase: 3, name: 'Identity & Authorization', detail: 'User/department administration, task access policies, isolation tests', done: false },
  { phase: 4, name: 'Task Management', detail: 'Task register, detail pages, assignments, lifecycle transitions', done: false },
  { phase: 5, name: 'Workflow Engine', detail: 'Stages, milestones, subtasks, dependencies, progress calculation', done: false },
  { phase: 6, name: 'Collaboration & Notifications', detail: 'Comments, attachments, notification center, outbox worker', done: false },
  { phase: 7, name: 'Dashboards & Reporting', detail: 'Kanban/Gantt views, workload reports, authorized exports', done: false },
  { phase: 8, name: 'CSV Migration', detail: 'Import center: mapping, preview, validation, reconciliation', done: false },
]

useHead({ title: 'Dashboard — DecOps' })
</script>
