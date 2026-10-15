<template>
  <div class="space-y-6">
    <section class="card overflow-hidden">
      <div class="flex flex-wrap gap-3 border-b border-line p-5 sm:p-6 lg:flex-nowrap lg:items-center lg:justify-between">
        <div class="min-w-0">
          <h2 class="text-base font-semibold text-ink">Users &amp; access</h2>
          <p class="page-subtitle">
            Create accounts to grant login, assign roles, and control access. Every change is audited.
          </p>
        </div>
        <div class="flex shrink-0 items-center gap-2">
          <input
            v-model="search"
            type="search"
            class="select-field !w-40"
            placeholder="Search name or email"
            aria-label="Search users"
          >
          <button type="button" class="btn-primary shrink-0" @click="openCreate">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="h-4 w-4" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            New user
          </button>
        </div>
      </div>

      <p v-if="loadError" role="alert" class="px-5 py-4 text-sm text-rose-600 dark:text-rose-400 sm:px-6">{{ loadError }}</p>

      <div v-else-if="pendingUsers" class="p-6 space-y-3" aria-busy="true">
        <div v-for="i in 5" :key="i" class="h-12 animate-pulse rounded-lg bg-elevated" />
      </div>

      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="table-head">
              <th class="table-cell">Name</th>
              <th class="table-cell">Email</th>
              <th class="table-cell">Roles</th>
              <th class="table-cell">Status</th>
              <th class="table-cell">Last login</th>
              <th class="table-cell"><span class="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-line">
            <tr v-for="user in filteredUsers" :key="user.id" class="transition-colors hover:bg-hover">
              <td class="table-cell">
                <div class="flex items-center gap-2.5">
                  <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-elevated text-xs font-bold text-muted" aria-hidden="true">
                    {{ initials(user.full_name) }}
                  </span>
                  <span class="min-w-0">
                    <span class="block truncate font-medium text-ink">{{ user.full_name }}</span>
                    <span class="block text-xs text-muted">{{ user.employee_code }}</span>
                  </span>
                </div>
              </td>
              <td class="table-cell text-body">{{ user.email }}</td>
              <td class="table-cell">
                <div class="flex flex-wrap gap-1">
                  <AppBadge v-for="role in roleNameMap(user)" :key="role" tone="blue">{{ role }}</AppBadge>
                  <span v-if="!detailRoles[user.id]?.length" class="text-xs text-faint">No roles</span>
                </div>
              </td>
              <td class="table-cell">
                <AppBadge :tone="user.account_status === 'active' ? 'green' : 'gray'">
                  {{ user.account_status }}
                </AppBadge>
              </td>
              <td class="table-cell text-xs text-muted">{{ formatDate(user.last_login_at) }}</td>
              <td class="table-cell text-right">
                <div class="flex justify-end gap-1">
                  <button type="button" class="btn-ghost !px-2 !py-1 text-xs" @click="openRoles(user)">
                    Roles
                  </button>
                  <button
                    v-if="user.account_status === 'active'"
                    type="button"
                    class="btn-ghost !px-2 !py-1 text-xs text-rose-600 dark:text-rose-400"
                    @click="setStatus(user, 'deactivated')"
                  >
                    Revoke login
                  </button>
                  <button
                    v-else
                    type="button"
                    class="btn-ghost !px-2 !py-1 text-xs text-brand-700 dark:text-brand-300"
                    @click="setStatus(user, 'active')"
                  >
                    Grant login
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!pendingUsers && !filteredUsers.length">
              <td colspan="6" class="empty-state">No users match the search.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Create user modal -->
    <div
      v-if="creating"
      class="fixed inset-0 z-50 flex items-center justify-center bg-overlay p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Create user"
      @click.self="creating = false"
    >
      <div class="w-full max-w-md overflow-hidden rounded-2xl border border-line bg-surface shadow-2xl">
        <div class="border-b border-line px-5 py-4">
          <h3 class="text-sm font-semibold text-ink">Grant login to a new user</h3>
          <p class="mt-0.5 text-xs text-muted">The person signs in with the email and the password you set here.</p>
        </div>
        <form class="space-y-4 px-5 py-4" novalidate @submit.prevent="createUser">
          <div>
            <label for="nu-name" class="block text-sm font-medium text-body">Full name</label>
            <input id="nu-name" v-model="createForm.full_name" type="text" class="input-field mt-1.5" required maxlength="200">
          </div>
          <div>
            <label for="nu-email" class="block text-sm font-medium text-body">Work email</label>
            <input id="nu-email" v-model="createForm.email" type="email" class="input-field mt-1.5" required autocomplete="off">
          </div>
          <div>
            <label for="nu-code" class="block text-sm font-medium text-body">Employee code</label>
            <input id="nu-code" v-model="createForm.employee_code" type="text" class="input-field mt-1.5" required maxlength="32">
          </div>
          <div>
            <label for="nu-password" class="block text-sm font-medium text-body">Initial password</label>
            <input
              id="nu-password"
              v-model="createForm.password"
              type="text"
              class="input-field mt-1.5 font-mono text-sm"
              required
              minlength="10"
              autocomplete="new-password"
            >
            <p class="mt-1 text-xs text-muted">At least 10 characters. Share it through a secure channel; it is audited on first login.</p>
          </div>
          <div>
            <span class="block text-sm font-medium text-body">Roles</span>
            <div class="mt-2 max-h-40 space-y-1.5 overflow-y-auto rounded-xl border border-line p-3">
              <label
                v-for="role in assignableRoles"
                :key="role.id"
                class="flex items-center gap-2.5 rounded-lg px-2 py-1 text-sm transition-colors hover:bg-hover"
              >
                <input v-model="createForm.role_ids" type="checkbox" :value="role.id" class="h-4 w-4 rounded border-line-strong accent-brand-600">
                <span class="text-ink">{{ role.name }}</span>
              </label>
              <p v-if="!assignableRoles.length" class="empty-state !py-4">Loading roles...</p>
            </div>
          </div>
          <p v-if="createFormError" role="alert" class="text-sm text-rose-600 dark:text-rose-400">{{ createFormError }}</p>
          <div class="flex justify-end gap-2 border-t border-line pt-4">
            <button type="button" class="btn-ghost" @click="creating = false">Cancel</button>
            <button type="submit" class="btn-primary" :disabled="working">
              {{ working ? 'Creating' : 'Create user' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Roles modal -->
    <div
      v-if="rolesTarget"
      class="fixed inset-0 z-50 flex items-center justify-center bg-overlay p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Assign roles"
      @click.self="rolesTarget = null"
    >
      <div class="w-full max-w-md overflow-hidden rounded-2xl border border-line bg-surface shadow-2xl">
        <div class="border-b border-line px-5 py-4">
          <h3 class="text-sm font-semibold text-ink">Roles for {{ rolesTarget.full_name }}</h3>
        </div>
        <div class="max-h-80 space-y-1.5 overflow-y-auto px-5 py-4">
          <label
            v-for="role in assignableRoles"
            :key="role.id"
            class="flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-sm transition-colors hover:bg-hover"
          >
            <input
              type="checkbox"
              class="h-4 w-4 rounded border-line-strong accent-brand-600"
              :checked="detailRoles[rolesTarget.id]?.includes(role.id)"
              @change="toggleRole(rolesTarget, role.id, ($event.target as HTMLInputElement).checked)"
            >
            <span class="text-ink">{{ role.name }}</span>
          </label>
        </div>
        <p v-if="rolesError" role="alert" class="px-5 pb-2 text-sm text-rose-600 dark:text-rose-400">{{ rolesError }}</p>
        <div class="flex justify-end border-t border-line px-5 py-4">
          <button type="button" class="btn-secondary" @click="rolesTarget = null">Done</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Role, UserDetail, UserOut } from '~/types/api'

const api = useApi()
const users = ref<UserOut[]>([])
const detailRoles = ref<Record<string, string[]>>({})
const assignableRoles = ref<Role[]>([])
const pendingUsers = ref(true)
const loadError = ref('')
const search = ref('')
const creating = ref(false)
const createForm = ref({ full_name: '', email: '', employee_code: '', password: '', role_ids: [] as string[] })
const createFormError = ref('')
const rolesTarget = ref<UserOut | null>(null)
const rolesError = ref('')
const working = ref(false)

const filteredUsers = computed(() => {
  const needle = search.value.trim().toLowerCase()
  if (!needle) return users.value
  return users.value.filter((u) =>
    u.full_name.toLowerCase().includes(needle) || u.email.toLowerCase().includes(needle),
  )
})

function initials(name: string): string {
  const parts = name.trim().split(/\s+/)
  if (!parts[0]) return '?'
  const first = parts[0]!.charAt(0)
  const last = parts.length > 1 ? parts[parts.length - 1]!.charAt(0) : ''
  return (first + last).toUpperCase()
}

function roleNameMap(user: UserOut): string[] {
  return detailRoles.value[user.id] ?? []
}

function formatDate(value: string | null): string {
  if (!value) return 'Never'
  return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

async function load(): Promise<void> {
  pendingUsers.value = true
  loadError.value = ''
  try {
    const [page, rolePage] = await Promise.all([
      api.get<{ items: UserOut[]; total: number }>('/api/v1/users?page=1&page_size=100'),
      api.get<{ items: Role[]; total: number }>('/api/v1/roles'),
    ])
    users.value = page.items
    assignableRoles.value = rolePage.items
    await Promise.all(page.items.map((u) => api.get<UserDetail>(`/api/v1/users/${u.id}`).then((detail) => {
      detailRoles.value[u.id] = detail.roles.map((r) => r.name)
    }).catch(() => undefined)))
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : 'Unable to load users.'
  } finally {
    pendingUsers.value = false
  }
}

function openCreate(): void {
  createFormError.value = ''
  createForm.value = { full_name: '', email: '', employee_code: '', password: generatePassword(), role_ids: [] }
  creating.value = true
}

function generatePassword(): string {
  const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789!@#$%'
  let out = ''
  const random = crypto.getRandomValues(new Uint32Array(14))
  for (const n of random) out += alphabet[n % alphabet.length]
  return out
}

async function createUser(): Promise<void> {
  working.value = true
  createFormError.value = ''
  try {
    await api.post('/api/v1/users', { ...createForm.value })
    creating.value = false
    await load()
  } catch (err) {
    createFormError.value = err instanceof Error ? err.message : 'Unable to create the user.'
  } finally {
    working.value = false
  }
}

async function openRoles(user: UserOut): Promise<void> {
  rolesError.value = ''
  rolesTarget.value = user
  if (!detailRoles.value[user.id]) {
    try {
      const detail = await api.get<UserDetail>(`/api/v1/users/${user.id}`)
      detailRoles.value[user.id] = detail.roles.map((r) => r.name)
    } catch {
      detailRoles.value[user.id] = []
    }
  }
}

async function toggleRole(user: UserOut, roleId: string, granted: boolean): Promise<void> {
  rolesError.value = ''
  try {
    if (granted) {
      await api.post(`/api/v1/users/${user.id}/roles`, { role_id: roleId })
    } else {
      await api.delete(`/api/v1/users/${user.id}/roles/${roleId}`)
    }
    const detail = await api.get<UserDetail>(`/api/v1/users/${user.id}`)
    detailRoles.value[user.id] = detail.roles.map((r) => r.name)
  } catch (err) {
    rolesError.value = err instanceof Error ? err.message : 'Unable to update roles.'
  }
}

async function setStatus(user: UserOut, status: 'active' | 'deactivated'): Promise<void> {
  loadError.value = ''
  try {
    await api.post(`/api/v1/users/${user.id}/status`, {
      status,
      reason: status === 'deactivated' ? 'Login revoked from settings' : 'Login granted from settings',
    })
    await load()
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : 'Unable to update the account.'
  }
}

onMounted(() => void load())
</script>
