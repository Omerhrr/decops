<template>
  <div class="min-h-screen flex flex-col">
    <header class="sticky top-0 z-30 border-b border-slate-200 bg-white">
      <div class="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6">
        <NuxtLink to="/" class="flex items-center gap-3">
          <span class="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 font-bold text-white">D</span>
          <span class="flex flex-col leading-tight">
            <span class="text-base font-semibold text-slate-900">DecOps</span>
            <span class="text-[11px] uppercase tracking-wider text-slate-400">Interdec Operations</span>
          </span>
        </NuxtLink>

        <div v-if="auth.isAuthenticated.value" class="flex items-center gap-4">
          <nav v-if="navItems.length" class="hidden items-center gap-1 md:flex" aria-label="Main">
            <NuxtLink
              v-for="item in navItems"
              :key="item.to"
              :to="item.to"
              class="rounded-lg px-3 py-2 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900"
              active-class="bg-slate-100 text-slate-900"
            >
              {{ item.label }}
            </NuxtLink>
          </nav>
          <div class="hidden text-right sm:block">
            <p class="text-sm font-medium text-slate-900">{{ auth.displayName.value }}</p>
            <p class="text-xs text-slate-500">{{ auth.roleNames.value.join(' · ') || 'No roles assigned' }}</p>
          </div>
          <button
            type="button"
            class="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-100"
            @click="handleLogout"
          >
            Sign out
          </button>
        </div>
      </div>
    </header>

    <main class="flex-1">
      <slot />
    </main>

    <footer class="border-t border-slate-200 bg-white">
      <div class="mx-auto flex max-w-7xl flex-col gap-1 px-4 py-4 text-xs text-slate-400 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p>DecOps v1.1.0 — Internal Operations Management System</p>
        <p>Interdec · Phase 3 release (Identity &amp; Authorization)</p>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
const auth = useAuth()

const navItems = computed(() => {
  const items: { to: string, label: string }[] = []
  if (auth.hasPermission('users.manage')) items.push({ to: '/admin/users', label: 'Users' })
  if (auth.hasPermission('departments.manage', 'users.manage')) items.push({ to: '/admin/departments', label: 'Departments' })
  return items
})

async function handleLogout() {
  await auth.logout()
}
</script>
