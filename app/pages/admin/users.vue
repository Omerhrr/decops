<template>
  <div class="mx-auto max-w-7xl px-4 py-8 sm:px-6">
    <!-- Header -->
    <section class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <nav class="text-xs text-slate-400" aria-label="Breadcrumb">
          <NuxtLink to="/" class="hover:text-slate-600">Dashboard</NuxtLink>
          <span class="mx-1">/</span>
          <span class="text-slate-600">Users</span>
        </nav>
        <h1 class="mt-1 text-xl font-semibold text-slate-900">User administration</h1>
        <p class="mt-1 text-sm text-slate-500">
          Employees, account status, and global role assignment (MOD-002). All changes are audited.
        </p>
      </div>
      <button
        v-if="canManage"
        type="button"
        class="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-700"
        @click="showCreate = true"
      >
        + Create employee
      </button>
    </section>

    <!-- Filters -->
    <section class="mt-6 flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 sm:flex-row sm:items-center">
      <input
        v-model="query"
        type="search"
        placeholder="Search by name or email…"
        class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500 sm:max-w-sm"
        @input="debouncedLoad"
      />
      <select
        v-model="statusFilter"
        class="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500"
        @change="loadUsers"
      >
        <option value="">All statuses</option>
        <option value="active">Active</option>
        <option value="disabled">Disabled</option>
        <option value="deactivated">Deactivated</option>
      </select>
      <span class="text-sm text-slate-400 sm:ml-auto">{{ total }} employees</span>
    </section>

    <!-- Directory table -->
    <section class="mt-4 overflow-hidden rounded-2xl border border-slate-200 bg-white">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <thead class="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th class="px-4 py-3">Employee</th>
            <th class="px-4 py-3">Code</th>
            <th class="px-4 py-3">Status</th>
            <th class="px-4 py-3">Roles</th>
            <th class="px-4 py-3">Last login</th>
            <th class="px-4 py-3 text-right">Actions</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-if="loading">
            <td colspan="6" class="px-4 py-8 text-center text-slate-400">Loading…</td>
          </tr>
          <tr v-else-if="!users.length">
            <td colspan="6" class="px-4 py-8 text-center text-slate-400">No employees match the filters.</td>
          </tr>
          <tr v-for="u in users" :key="u.id" class="hover:bg-slate-50/60">
            <td class="px-4 py-3">
              <p class="font-medium text-slate-900">{{ u.full_name }}</p>
              <p class="text-xs text-slate-500">{{ u.email }}</p>
            </td>
            <td class="px-4 py-3 font-mono text-xs text-slate-600">{{ u.employee_code }}</td>
            <td class="px-4 py-3">
              <AppBadge :tone="statusTone(u.account_status)">{{ u.account_status }}</AppBadge>
            </td>
            <td class="px-4 py-3">
              <div class="flex flex-wrap gap-1">
                <AppBadge
                  v-for="r in detailRoles(u.id)"
                  :key="r.id"
                  tone="gray"
                >{{ r.name }}</AppBadge>
                <span v-if="!detailRoles(u.id).length" class="text-xs text-slate-400"> - </span>
              </div>
            </td>
            <td class="px-4 py-3 text-xs text-slate-500">{{ formatDate(u.last_login_at) }}</td>
            <td class="px-4 py-3">
              <div class="flex justify-end gap-2">
                <button
                  v-if="canManage"
                  type="button"
                  class="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100"
                  @click="openRoles(u)"
                >
                  Roles
                </button>
                <button
                  v-if="canManage && u.account_status === 'active'"
                  type="button"
                  class="rounded-lg border border-red-200 px-2.5 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50"
                  @click="deactivate(u)"
                >
                  Deactivate
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- Pagination -->
    <div v-if="totalPages > 1" class="mt-4 flex items-center justify-end gap-2 text-sm">
      <button
        type="button"
        class="rounded-lg border border-slate-200 px-3 py-1.5 disabled:opacity-40"
        :disabled="page <= 1"
        @click="page--; loadUsers()"
      >
        Previous
      </button>
      <span class="text-slate-500">Page {{ page }} of {{ totalPages }}</span>
      <button
        type="button"
        class="rounded-lg border border-slate-200 px-3 py-1.5 disabled:opacity-40"
        :disabled="page >= totalPages"
        @click="page++; loadUsers()"
      >
        Next
      </button>
    </div>

    <!-- Create modal -->
    <div v-if="showCreate" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" role="dialog" aria-modal="true">
      <div class="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
        <h2 class="text-base font-semibold text-slate-900">Create employee</h2>
        <form class="mt-4 space-y-3" @submit.prevent="createUser">
          <div>
            <label class="text-xs font-medium text-slate-600" for="new-name">Full name</label>
            <input id="new-name" v-model="form.full_name" required class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          </div>
          <div>
            <label class="text-xs font-medium text-slate-600" for="new-email">Email</label>
            <input id="new-email" v-model="form.email" type="email" required class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="text-xs font-medium text-slate-600" for="new-code">Employee code</label>
              <input id="new-code" v-model="form.employee_code" required class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500" placeholder="INT-0000" />
            </div>
            <div>
              <label class="text-xs font-medium text-slate-600" for="new-password">Temp password</label>
              <input id="new-password" v-model="form.password" type="password" required minlength="10" class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500" />
            </div>
          </div>
          <div>
            <label class="text-xs font-medium text-slate-600" for="new-role">Initial role</label>
            <select id="new-role" v-model="form.roleId" class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500">
              <option value="">No role yet</option>
              <option v-for="r in roles" :key="r.id" :value="r.id">{{ r.name }}</option>
            </select>
          </div>
          <p v-if="formError" class="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600">{{ formError }}</p>
          <div class="flex justify-end gap-2 pt-2">
            <button type="button" class="rounded-lg border border-slate-200 px-3 py-2 text-sm" @click="showCreate = false">Cancel</button>
            <button type="submit" :disabled="busy" class="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50">
              {{ busy ? 'Creating…' : 'Create employee' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Roles modal -->
    <div v-if="rolesTarget" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" role="dialog" aria-modal="true">
      <div class="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
        <h2 class="text-base font-semibold text-slate-900">Global roles - {{ rolesTarget.full_name }}</h2>
        <p class="mt-1 text-xs text-slate-500">Permission changes are audited and take effect on the next request.</p>

        <div class="mt-4 flex flex-wrap gap-2">
          <span
            v-for="r in rolesTargetRoles"
            :key="r.id"
            class="flex items-center gap-1.5 rounded-full bg-brand-50 py-1 pl-3 pr-2 text-xs font-medium text-brand-700"
          >
            {{ r.name }}
            <button type="button" class="text-brand-400 hover:text-brand-700" aria-label="Revoke role" @click="revokeRole(r)">✕</button>
          </span>
          <span v-if="!rolesTargetRoles.length" class="text-xs text-slate-400">No global roles assigned.</span>
        </div>

        <div class="mt-4 flex gap-2">
          <select v-model="roleToAdd" class="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500">
            <option value="" disabled>Select a role to assign…</option>
            <option v-for="r in assignableRoles" :key="r.id" :value="r.id">{{ r.name }}</option>
          </select>
          <button
            type="button"
            :disabled="!roleToAdd || busy"
            class="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            @click="assignRole"
          >
            Assign
          </button>
        </div>
        <p v-if="formError" class="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600">{{ formError }}</p>
        <div class="mt-4 flex justify-end">
          <button type="button" class="rounded-lg border border-slate-200 px-3 py-2 text-sm" @click="closeRoles">Done</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Role, RoleListPage, UserDetail, UserOut, UserPage } from '~/types/api'

const auth = useAuth()
const api = useApi()

const canManage = computed(() => auth.hasPermission('users.manage'))

const users = ref<UserOut[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(true)
const query = ref('')
const statusFilter = ref('')
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

// Role cache + per-user detail (roles are only on the detail endpoint)
const roles = ref<Role[]>([])
const roleDetails = ref<Record<string, UserDetail>>({})

const showCreate = ref(false)
const busy = ref(false)
const formError = ref('')
const form = reactive({ full_name: '', email: '', employee_code: '', password: '', roleId: '' })

const rolesTarget = ref<UserOut | null>(null)
const rolesTargetRoles = ref<Role[]>([])
const roleToAdd = ref('')

const assignableRoles = computed(() =>
  roles.value.filter(r => !rolesTargetRoles.value.some(t => t.id === r.id)),
)

function detailRoles(userId: string): Role[] {
  return (roleDetails.value[userId]?.roles ?? []).map(r => ({
    id: r.id, name: r.name, description: r.description, is_system_role: true, permissions: [],
  }))
}

function statusTone(status: string): 'green' | 'red' | 'gray' {
  if (status === 'active') return 'green'
  if (status === 'deactivated') return 'red'
  return 'gray'
}

function formatDate(value: string | null): string {
  if (!value) return 'Never'
  return new Date(value).toLocaleString()
}

async function loadUsers() {
  loading.value = true
  try {
    const params = new URLSearchParams({ page: String(page.value), page_size: String(pageSize) })
    if (query.value.trim()) params.set('q', query.value.trim())
    if (statusFilter.value) params.set('status', statusFilter.value)
    const res = await api.get<UserPage>(`/api/v1/users?${params.toString()}`)
    users.value = res.items
    total.value = res.total
    await loadRolesForPage()
  } catch (e) {
    formError.value = e instanceof Error ? e.message : 'Failed to load users.'
  } finally {
    loading.value = false
  }
}

async function loadRolesForPage() {
  if (!canManage.value) return
  await Promise.all(users.value.map(async (u) => {
    try {
      roleDetails.value[u.id] = await api.get<UserDetail>(`/api/v1/users/${u.id}`)
    } catch { /* permission or transient error: leave roles blank */ }
  }))
}

async function loadRoles() {
  const res = await api.get<RoleListPage>('/api/v1/roles')
  roles.value = res.items
}

let debounceTimer: ReturnType<typeof setTimeout> | undefined
function debouncedLoad() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    page.value = 1
    loadUsers()
  }, 300)
}

async function createUser() {
  busy.value = true
  formError.value = ''
  try {
    await api.post('/api/v1/users', {
      full_name: form.full_name,
      email: form.email,
      employee_code: form.employee_code,
      password: form.password,
      role_ids: form.roleId ? [form.roleId] : [],
    })
    showCreate.value = false
    Object.assign(form, { full_name: '', email: '', employee_code: '', password: '', roleId: '' })
    await loadUsers()
  } catch (e) {
    formError.value = e instanceof Error ? e.message : 'Could not create the employee.'
  } finally {
    busy.value = false
  }
}

async function deactivate(u: UserOut) {
  if (!confirm(`Deactivate ${u.full_name}? Their sessions are revoked immediately.`)) return
  try {
    await api.post(`/api/v1/users/${u.id}/status`, {
      status: 'deactivated',
      reason: 'Deactivated from user administration UI',
    })
    await loadUsers()
  } catch (e) {
    alert(e instanceof Error ? e.message : 'Could not deactivate the employee.')
  }
}

async function openRoles(u: UserOut) {
  rolesTarget.value = u
  roleToAdd.value = ''
  formError.value = ''
  try {
    const detail = await api.get<UserDetail>(`/api/v1/users/${u.id}`)
    roleDetails.value[u.id] = detail
    rolesTargetRoles.value = detail.roles.map(r => ({
      id: r.id, name: r.name, description: r.description, is_system_role: true, permissions: [],
    }))
  } catch {
    rolesTargetRoles.value = []
  }
}

function closeRoles() {
  rolesTarget.value = null
}

async function assignRole() {
  if (!rolesTarget.value || !roleToAdd.value) return
  busy.value = true
  formError.value = ''
  try {
    const detail = await api.post<UserDetail>(
      `/api/v1/users/${rolesTarget.value.id}/roles`,
      { role_id: roleToAdd.value },
    )
    roleDetails.value[detail.id] = detail
    rolesTargetRoles.value = detail.roles.map(r => ({
      id: r.id, name: r.name, description: r.description, is_system_role: true, permissions: [],
    }))
    roleToAdd.value = ''
  } catch (e) {
    formError.value = e instanceof Error ? e.message : 'Could not assign the role.'
  } finally {
    busy.value = false
  }
}

async function revokeRole(r: Role) {
  if (!rolesTarget.value) return
  busy.value = true
  formError.value = ''
  try {
    const detail = await api.delete<UserDetail>(`/api/v1/users/${rolesTarget.value.id}/roles/${r.id}`)
    roleDetails.value[detail.id] = detail
    rolesTargetRoles.value = detail.roles.map(x => ({
      id: x.id, name: x.name, description: x.description, is_system_role: true, permissions: [],
    }))
  } catch (e) {
    formError.value = e instanceof Error ? e.message : 'Could not revoke the role.'
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  await loadUsers()
  if (canManage.value) await loadRoles()
})

useHead({ title: 'Users - DecOps' })
</script>
