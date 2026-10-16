<template>
  <div class="space-y-6">
    <section class="card overflow-hidden">
      <div class="flex flex-col gap-2 border-b border-line p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div>
          <h2 class="text-base font-semibold text-ink">Roles</h2>
          <p class="page-subtitle">
            System roles ship with a fixed permission set and stay read-only. Custom roles are fully editable.
          </p>
        </div>
        <button type="button" class="btn-primary shrink-0" @click="openCreate">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="h-4 w-4" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          New role
        </button>
      </div>

      <p v-if="loadError" role="alert" class="px-5 py-4 text-sm text-rose-600 dark:text-rose-400 sm:px-6">{{ loadError }}</p>

      <div v-else-if="pendingRoles" class="p-6 space-y-3" aria-busy="true">
        <div v-for="i in 4" :key="i" class="h-12 animate-pulse rounded-lg bg-elevated" />
      </div>

      <ul v-else class="divide-y divide-line">
        <li v-for="role in roles" :key="role.id">
          <button
            type="button"
            class="flex w-full items-center gap-4 px-5 py-4 text-left transition-colors hover:bg-hover sm:px-6"
            @click="openEdit(role)"
          >
            <span class="min-w-0 flex-1">
              <span class="flex items-center gap-2">
                <span class="truncate text-sm font-semibold text-ink">{{ role.name }}</span>
                <AppBadge :tone="role.is_system_role ? 'blue' : 'green'">
                  {{ role.is_system_role ? 'System' : 'Custom' }}
                </AppBadge>
              </span>
              <span class="mt-0.5 block truncate text-xs text-muted">
                {{ role.description || 'No description' }}
              </span>
            </span>
            <span class="shrink-0 text-right text-xs text-muted">
              {{ role.permissions.length }} permission{{ role.permissions.length === 1 ? '' : 's' }}
            </span>
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.6" stroke="currentColor" class="h-4 w-4 shrink-0 text-faint" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
            </svg>
          </button>
        </li>
        <li v-if="!pendingRoles && !roles.length" class="empty-state">
          <p>No roles found.</p>
        </li>
      </ul>
    </section>

    <!-- Editor modal -->
    <div
      v-if="editing"
      class="fixed inset-0 z-50 flex items-center justify-center bg-overlay p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Role editor"
      v-dialog="{ close: closeEditor }"
      @click.self="closeEditor"
    >
      <div class="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-2xl">
        <div class="flex items-center justify-between border-b border-line px-5 py-4">
          <div>
            <h3 class="text-sm font-semibold text-ink">
              {{ editing.isNew ? 'Create custom role' : `Edit role: ${editing.name}` }}
            </h3>
            <p v-if="!editing.isNew && editing.is_system_role" class="mt-0.5 text-xs text-muted">
              System role: view only, changes are not allowed.
            </p>
          </div>
          <button type="button" class="rounded-lg p-1.5 text-faint hover:bg-hover hover:text-ink" aria-label="Close" @click="closeEditor">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.6" stroke="currentColor" class="h-5 w-5" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div class="flex-1 overflow-y-auto px-5 py-4">
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label for="role-name" class="block text-sm font-medium text-body">Name</label>
              <input
                id="role-name"
                v-model="editing.name"
                type="text"
                class="input-field mt-1.5"
                maxlength="100"
                :disabled="!canEdit"
                placeholder="e.g. Reporting Analyst"
              >
            </div>
            <div>
              <label for="role-desc" class="block text-sm font-medium text-body">Description</label>
              <input
                id="role-desc"
                v-model="editing.description"
                type="text"
                class="input-field mt-1.5"
                maxlength="500"
                :disabled="!canEdit"
                placeholder="What this role is for"
              >
            </div>
          </div>

          <div class="mt-5">
            <div class="flex items-center justify-between">
              <p class="text-sm font-medium text-body">
                Permissions
                <span class="ml-1 text-xs text-muted">({{ selectedPermissions.length }} selected)</span>
              </p>
              <input
                v-model="permissionFilter"
                type="search"
                class="select-field !w-44 text-xs"
                placeholder="Filter permissions"
                aria-label="Filter permissions"
              >
            </div>

            <div class="mt-3 max-h-80 space-y-4 overflow-y-auto rounded-xl border border-line p-3">
              <fieldset v-for="group in groupedPermissions" :key="group.prefix" class="space-y-1.5">
                <legend class="px-1 text-xs font-semibold uppercase tracking-wider text-faint">
                  {{ permissionGroupName(group.prefix) }}
                </legend>
                <label
                  v-for="perm in group.items"
                  :key="perm.code"
                  class="flex items-start gap-2.5 rounded-lg px-2 py-1.5 text-sm transition-colors hover:bg-hover"
                >
                  <input
                    v-model="selectedPermissions"
                    type="checkbox"
                    :value="perm.code"
                    :disabled="!canEdit"
                    class="mt-0.5 h-4 w-4 rounded border-line-strong accent-brand-600"
                  >
                  <span class="min-w-0">
                    <span class="block truncate text-sm font-medium text-ink">{{ permissionLabel(perm.code) }}</span>
                    <span
                      v-if="perm.description && perm.description !== perm.code"
                      class="block truncate text-xs text-muted"
                    >{{ perm.description }}</span>
                  </span>
                </label>
              </fieldset>
              <p v-if="!groupedPermissions.length" class="empty-state">No permissions match the filter.</p>
            </div>
          </div>
        </div>

        <div class="flex items-center justify-between gap-3 border-t border-line px-5 py-4">
          <button
            v-if="canDelete"
            type="button"
            class="btn-danger"
            :disabled="working"
            @click="removeRole"
          >
            Delete role
          </button>
          <span v-else />
          <div class="flex items-center gap-2">
            <p v-if="errorMessage" role="alert" class="mr-2 text-sm text-rose-600 dark:text-rose-400">{{ errorMessage }}</p>
            <button type="button" class="btn-ghost" @click="closeEditor">Cancel</button>
            <button
              v-if="canEdit"
              type="button"
              class="btn-primary"
              :disabled="working || !editing.name.trim()"
              @click="saveRole"
            >
              {{ working ? 'Saving' : editing.isNew ? 'Create role' : 'Save changes' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Permission, Role } from '~/types/api'

interface EditorState {
  isNew: boolean
  id: string | null
  name: string
  description: string
  is_system_role: boolean
  users_assigned?: number
}

const api = useApi()
const roles = ref<Role[]>([])
const permissions = ref<Permission[]>([])
const pendingRoles = ref(true)
const loadError = ref('')
const editing = ref<EditorState | null>(null)
const selectedPermissions = ref<string[]>([])
const permissionFilter = ref('')
const working = ref(false)
const errorMessage = ref('')

const canEdit = computed(() => editing.value !== null && (editing.value.isNew || !editing.value.is_system_role))
const canDelete = computed(() => editing.value !== null && !editing.value.isNew && !editing.value.is_system_role)

const groupedPermissions = computed(() => {
  const needle = permissionFilter.value.trim().toLowerCase()
  const groups = new Map<string, Permission[]>()
  for (const perm of permissions.value) {
    if (needle) {
      const haystack = [
        perm.code,
        permissionLabel(perm.code),
        permissionGroupName(perm.code.split('.')[0] ?? 'other'),
        perm.description ?? '',
      ].join(' ').toLowerCase()
      if (!haystack.includes(needle)) continue
    }
    const prefix = perm.code.split('.')[0] ?? 'other'
    if (!groups.has(prefix)) groups.set(prefix, [])
    groups.get(prefix)!.push(perm)
  }
  return [...groups.entries()]
    .map(([prefix, items]) => ({ prefix, items }))
    .sort((a, b) => a.prefix.localeCompare(b.prefix))
})

async function load(): Promise<void> {
  pendingRoles.value = true
  loadError.value = ''
  try {
    const [rolePage, permPage] = await Promise.all([
      api.get<{ items: Role[]; total: number }>('/api/v1/roles'),
      api.get<{ items: Permission[]; total: number }>('/api/v1/roles/permissions'),
    ])
    roles.value = rolePage.items
    permissions.value = permPage.items
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : 'Unable to load roles.'
  } finally {
    pendingRoles.value = false
  }
}

function openCreate(): void {
  errorMessage.value = ''
  editing.value = { isNew: true, id: null, name: '', description: '', is_system_role: false }
  selectedPermissions.value = []
}

function openEdit(role: Role): void {
  errorMessage.value = ''
  editing.value = {
    isNew: false,
    id: role.id,
    name: role.name,
    description: role.description ?? '',
    is_system_role: role.is_system_role,
  }
  selectedPermissions.value = [...role.permissions]
}

function closeEditor(): void {
  editing.value = null
}

async function saveRole(): Promise<void> {
  if (!editing.value) return
  working.value = true
  errorMessage.value = ''
  const payload = {
    name: editing.value.name.trim(),
    description: editing.value.description.trim() || null,
    permissions: selectedPermissions.value,
  }
  try {
    if (editing.value.isNew) {
      await api.post<Role>('/api/v1/roles', payload)
    } else if (editing.value.id) {
      await api.patch<Role>(`/api/v1/roles/${editing.value.id}`, payload)
    }
    editing.value = null
    await load()
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : 'Unable to save the role.'
  } finally {
    working.value = false
  }
}

async function removeRole(): Promise<void> {
  if (!editing.value?.id) return
  working.value = true
  errorMessage.value = ''
  try {
    await api.delete(`/api/v1/roles/${editing.value.id}`)
    editing.value = null
    await load()
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : 'Unable to delete the role.'
  } finally {
    working.value = false
  }
}

onMounted(() => void load())
</script>
