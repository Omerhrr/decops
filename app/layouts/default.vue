<template>
  <div class="min-h-screen bg-slate-50">
    <!-- Desktop sidebar (collapsible icon rail) -->
    <aside
      class="fixed inset-y-0 left-0 z-40 hidden flex-col border-r border-slate-200 bg-white transition-[width] duration-200 lg:flex"
      :class="collapsed ? 'w-20' : 'w-64'"
    >
      <div class="flex h-16 shrink-0 items-center border-b border-slate-200" :class="collapsed ? 'justify-center px-0' : 'gap-3 px-4'">
        <NuxtLink to="/" class="flex items-center gap-3" :title="collapsed ? 'DecOps' : undefined">
          <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-600 font-bold text-white">D</span>
          <span v-if="!collapsed" class="flex flex-col leading-tight">
            <span class="text-base font-semibold text-slate-900">DecOps</span>
            <span class="text-[11px] uppercase tracking-wider text-slate-400">Interdec Operations</span>
          </span>
        </NuxtLink>
      </div>

      <nav class="flex-1 overflow-y-auto p-3">
        <AppSidebarNav :collapsed="collapsed" />
      </nav>

      <div class="border-t border-slate-200 p-3">
        <button
          type="button"
          class="flex w-full items-center rounded-lg px-3 py-2.5 text-sm font-medium text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-800"
          :class="collapsed && 'justify-center px-2'"
          :aria-label="collapsed ? 'Expand sidebar' : 'Collapse sidebar'"
          data-test="sidebar-toggle"
          @click="toggleCollapsed"
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.6" stroke="currentColor" class="h-5 w-5 shrink-0 transition-transform duration-200" :class="collapsed ? '' : 'rotate-180'" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
          </svg>
          <span v-if="!collapsed" class="ml-3">Collapse</span>
        </button>
      </div>
    </aside>

    <!-- Mobile drawer -->
    <div v-if="mobileOpen" class="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
      <div class="absolute inset-0 bg-slate-900/50" data-test="drawer-backdrop" @click="closeMobile" />
      <aside class="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col bg-white shadow-xl">
        <div class="flex h-16 shrink-0 items-center justify-between border-b border-slate-200 px-4">
          <NuxtLink to="/" class="flex items-center gap-3" @click="closeMobile">
            <span class="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 font-bold text-white">D</span>
            <span class="flex flex-col leading-tight">
              <span class="text-base font-semibold text-slate-900">DecOps</span>
              <span class="text-[11px] uppercase tracking-wider text-slate-400">Interdec Operations</span>
            </span>
          </NuxtLink>
          <button type="button" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label="Close menu" @click="closeMobile">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.6" stroke="currentColor" class="h-5 w-5" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <nav class="flex-1 overflow-y-auto p-3">
          <AppSidebarNav @navigate="closeMobile" />
        </nav>

        <div class="border-t border-slate-200 p-4">
          <p class="truncate text-sm font-medium text-slate-900">{{ auth.displayName.value }}</p>
          <p class="truncate text-xs text-slate-500">{{ auth.roleNames.value.join(' · ') || 'No roles assigned' }}</p>
          <button
            type="button"
            class="mt-3 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
            @click="handleLogout"
          >
            Sign out
          </button>
        </div>
      </aside>
    </div>

    <!-- Content column: padded by the sidebar width on desktop -->
    <div class="flex min-h-screen flex-col transition-[padding] duration-200" :class="collapsed ? 'lg:pl-20' : 'lg:pl-64'">
      <header class="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div class="flex h-16 items-center justify-between gap-3 px-4 sm:px-6">
          <div class="flex items-center gap-2">
            <button
              type="button"
              class="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-700 lg:hidden"
              aria-label="Open menu"
              data-test="mobile-menu-button"
              @click="mobileOpen = true"
            >
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.6" stroke="currentColor" class="h-6 w-6" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
              </svg>
            </button>
            <span class="flex items-center gap-2 lg:hidden">
              <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-sm font-bold text-white">D</span>
              <span class="text-sm font-semibold text-slate-900">DecOps</span>
            </span>
          </div>

          <div v-if="auth.isAuthenticated.value" class="flex items-center gap-2 sm:gap-4">
            <AppNotifications />
            <div class="hidden text-right sm:block">
              <p class="text-sm font-medium text-slate-900">{{ auth.displayName.value }}</p>
              <p class="text-xs text-slate-500">{{ auth.roleNames.value.join(' · ') || 'No roles assigned' }}</p>
            </div>
            <button
              type="button"
              class="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-100"
              @click="handleLogout"
            >
              <span class="hidden sm:inline">Sign out</span>
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.6" stroke="currentColor" class="h-5 w-5 sm:hidden" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9" />
              </svg>
            </button>
          </div>
        </div>
      </header>

      <main class="flex-1">
        <slot />
      </main>

      <footer class="border-t border-slate-200 bg-white">
        <div class="mx-auto flex max-w-7xl flex-col gap-1 px-4 py-4 text-xs text-slate-400 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p>DecOps v1.0 — Internal Operations Management System</p>
          <p>Interdec · v1.0 production launch (Phase 10)</p>
        </div>
      </footer>
    </div>
  </div>
</template>

<script setup lang="ts">
const auth = useAuth()

// Collapsed state persists per browser (desktop rail only).
const collapsed = useState<boolean>('ui.sidebar-collapsed', () => false)
const mobileOpen = useState<boolean>('ui.mobile-nav-open', () => false)

const STORAGE_KEY = 'decops.sidebar-collapsed'

onMounted(() => {
  try {
    if (localStorage.getItem(STORAGE_KEY) === '1') collapsed.value = true
  } catch {
    /* storage unavailable (private mode) — default expanded */
  }
})

watch(collapsed, (value) => {
  try {
    localStorage.setItem(STORAGE_KEY, value ? '1' : '0')
  } catch {
    /* ignore */
  }
})

function toggleCollapsed(): void {
  collapsed.value = !collapsed.value
}

function closeMobile(): void {
  mobileOpen.value = false
}

async function handleLogout(): Promise<void> {
  mobileOpen.value = false
  await auth.logout()
}

// Navigating closes the mobile drawer so content is visible immediately.
const route = useRoute()
watch(() => route.fullPath, () => {
  mobileOpen.value = false
})
</script>
