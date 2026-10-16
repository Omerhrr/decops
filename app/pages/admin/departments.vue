<template>
  <div class="mx-auto max-w-7xl px-4 py-8 sm:px-6">
    <section class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <nav class="text-xs text-faint" aria-label="Breadcrumb">
          <NuxtLink to="/" class="hover:text-body">Dashboard</NuxtLink>
          <span class="mx-1">/</span>
          <span class="text-body">Departments</span>
        </nav>
        <h1 class="mt-1 text-xl font-semibold text-ink">Department management</h1>
        <p class="mt-1 text-sm text-muted">
          Departments, leads, and employee memberships. All changes are audited.
        </p>
      </div>
      <button
        v-if="canManage"
        type="button"
        class="btn-primary"
        @click="showCreate = true"
      >
        + Create department
      </button>
    </section>

    <section class="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
      <div v-if="loading" class="empty-state rounded-2xl border border-line bg-surface lg:col-span-2">
        Loading departments…
      </div>
      <div v-else-if="!departments.length" class="empty-state rounded-2xl border border-line bg-surface lg:col-span-2">
        No departments yet. Create the first one to start assigning employees.
      </div>

      <article
        v-for="d in departments"
        :key="d.id"
        class="rounded-2xl border border-line bg-surface p-5"
        :class="d.status === 'inactive' ? 'opacity-70' : ''"
      >
        <header class="flex items-start justify-between gap-3">
          <div>
            <h2 class="text-base font-semibold text-ink">{{ d.name }}</h2>
            <p class="mt-0.5 text-sm text-muted">{{ d.description || 'No description' }}</p>
          </div>
          <AppBadge :tone="d.status === 'active' ? 'green' : 'gray'">{{ d.status }}</AppBadge>
        </header>

        <dl class="mt-3 grid grid-cols-2 gap-2 text-sm">
          <div>
            <dt class="text-xs uppercase tracking-wide text-faint">Lead</dt>
            <dd class="mt-0.5 text-ink">{{ d.lead?.full_name || 'Unassigned' }}</dd>
          </div>
          <div>
            <dt class="text-xs uppercase tracking-wide text-faint">Members</dt>
            <dd class="mt-0.5 text-ink">{{ d.member_count }}</dd>
          </div>
        </dl>

        <!-- Members -->
        <div v-if="detailOf(d.id)?.memberships?.length" class="mt-3 space-y-1.5 border-t border-line pt-3">
          <div
            v-for="m in detailOf(d.id)!.memberships"
            :key="m.id"
            class="flex items-center justify-between text-sm"
          >
            <span class="text-body">
              {{ m.user?.full_name || m.user_id }}
              <span class="ml-1 text-xs text-faint">({{ m.membership_role }})</span>
            </span>
            <button
              v-if="canManage"
              type="button"
              class="text-xs text-rose-600 hover:text-rose-700 dark:text-rose-400"
              @click="removeMember(d, m.user_id, m.user?.full_name)"
            >
              Remove
            </button>
          </div>
        </div>

        <!-- Add member -->
        <div v-if="canManage" class="mt-3 flex gap-2 border-t border-line pt-3">
          <select v-model="memberPick[d.id]" class="select-field flex-1" aria-label="Add employee to department">
            <option value="" disabled>Add employee…</option>
            <option v-for="u in addableUsers(d)" :key="u.id" :value="u.id">{{ u.full_name }}</option>
          </select>
          <select v-model="rolePick[d.id]" class="select-field" aria-label="Membership role">
            <option value="member">member</option>
            <option value="lead">lead</option>
          </select>
          <button
            type="button"
            :disabled="!memberPick[d.id]"
            class="btn-primary !px-3 !py-1.5 text-xs"
            @click="addMember(d)"
          >
            Add
          </button>
        </div>
      </article>
    </section>

    <p v-if="actionError" role="alert" class="alert-error mt-4">{{ actionError }}</p>

    <div v-if="showCreate" class="fixed inset-0 z-50 flex items-center justify-center bg-overlay p-4" role="dialog" aria-modal="true" aria-label="Create department" v-dialog="{ close: () => showCreate = false }" @click.self="showCreate = false">
      <div class="w-full max-w-md rounded-2xl bg-surface p-6 shadow-xl">
        <h2 class="text-base font-semibold text-ink">Create department</h2>
        <form class="mt-4 space-y-3" @submit.prevent="createDepartment">
          <div>
            <label class="text-xs font-medium text-body" for="dep-name">Name</label>
            <input id="dep-name" v-model="depForm.name" required class="input-field mt-1" />
          </div>
          <div>
            <label class="text-xs font-medium text-body" for="dep-desc">Description</label>
            <textarea id="dep-desc" v-model="depForm.description" rows="2" class="input-field mt-1"></textarea>
          </div>
          <div>
            <label class="text-xs font-medium text-body" for="dep-lead">Department lead</label>
            <select id="dep-lead" v-model="depForm.lead_user_id" class="input-field mt-1">
              <option value="">No lead yet</option>
              <option v-for="u in allUsers" :key="u.id" :value="u.id">{{ u.full_name }} ({{ u.employee_code }})</option>
            </select>
          </div>
          <p v-if="formError" role="alert" class="alert-error">{{ formError }}</p>
          <div class="flex justify-end gap-2 pt-2">
            <button type="button" class="btn-secondary" @click="showCreate = false">Cancel</button>
            <button type="submit" :disabled="busy" class="btn-primary">
              {{ busy ? 'Creating…' : 'Create department' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Department, DepartmentDetail, DepartmentMembership, UserOut, UserPage } from '~/types/api'

const auth = useAuth()
const api = useApi()
const { confirm } = useConfirm()

const canManage = computed(() => auth.hasPermission('departments.manage'))

const departments = ref<Department[]>([])
const details = ref<Record<string, DepartmentDetail>>({})
const allUsers = ref<UserOut[]>([])
const loading = ref(true)
const showCreate = ref(false)
const busy = ref(false)
const formError = ref('')
const actionError = ref('')
const depForm = reactive({ name: '', description: '', lead_user_id: '' })
const memberPick = reactive<Record<string, string>>({})
const rolePick = reactive<Record<string, 'member' | 'lead'>>({})

function detailOf(id: string): DepartmentDetail | undefined {
  return details.value[id]
}

function addableUsers(d: Department): UserOut[] {
  const memberIds = new Set((detailOf(d.id)?.memberships ?? []).map(m => m.user_id))
  return allUsers.value.filter(u => !memberIds.has(u.id))
}

async function loadDepartments() {
  loading.value = true
  try {
    departments.value = await api.get<Department[]>('/api/v1/departments')
    await Promise.all(departments.value.map(async (d) => {
      try {
        details.value[d.id] = await api.get<DepartmentDetail>(`/api/v1/departments/${d.id}`)
      } catch { /* transient */ }
    }))
  } finally {
    loading.value = false
  }
}

async function loadUsers() {
  if (!canManage.value) return
  try {
    const res = await api.get<UserPage>('/api/v1/users?page=1&page_size=100')
    allUsers.value = res.items
  } catch { /* users.manage not held: leave picker empty */ }
}

async function createDepartment() {
  busy.value = true
  formError.value = ''
  try {
    await api.post('/api/v1/departments', {
      name: depForm.name,
      description: depForm.description || null,
      lead_user_id: depForm.lead_user_id || null,
    })
    showCreate.value = false
    Object.assign(depForm, { name: '', description: '', lead_user_id: '' })
    await loadDepartments()
  } catch (e) {
    formError.value = e instanceof Error ? e.message : 'Could not create the department.'
  } finally {
    busy.value = false
  }
}

async function addMember(d: Department) {
  const userId = memberPick[d.id]
  if (!userId) return
  busy.value = true
  actionError.value = ''
  try {
    const detail = await api.post<DepartmentDetail>(`/api/v1/departments/${d.id}/members`, {
      user_id: userId,
      membership_role: rolePick[d.id] ?? 'member',
    })
    details.value[d.id] = detail
    const idx = departments.value.findIndex(x => x.id === d.id)
    if (idx >= 0) departments.value[idx] = detail
    memberPick[d.id] = ''
  } catch (e) {
    actionError.value = e instanceof Error ? e.message : 'Could not add the member.'
  } finally {
    busy.value = false
  }
}

async function removeMember(d: Department, userId: string, name?: string) {
  const ok = await confirm({
    title: 'Remove member',
    message: `Remove ${name || 'this employee'} from ${d.name}?`,
    confirmLabel: 'Remove',
    tone: 'danger',
  })
  if (!ok) return
  actionError.value = ''
  try {
    await api.delete(`/api/v1/departments/${d.id}/members/${userId}`)
    await loadDepartments()
  } catch (e) {
    actionError.value = e instanceof Error ? e.message : 'Could not remove the member.'
  }
}

onMounted(async () => {
  await Promise.all([loadDepartments(), loadUsers()])
})

useHead({ title: 'Departments - DecOps' })
</script>
