<template>
  <div class="min-h-screen bg-canvas">
    <!-- Desktop sidebar (collapsible icon rail) -->
    <aside
      class="fixed inset-y-0 left-0 z-40 hidden flex-col border-r border-line bg-surface transition-[width] duration-200 lg:flex"
      :class="collapsed ? 'w-20' : 'w-64'"
    >
      <div class="flex h-16 shrink-0 items-center border-b border-line" :class="collapsed ? 'justify-center px-0' : 'px-4'">
        <NuxtLink to="/" class="flex items-center" :title="collapsed ? 'DecOps' : undefined" aria-label="DecOps home">
          <BrandLogo :compact="collapsed" />
        </NuxtLink>
      </div>

      <nav class="flex-1 overflow-y-auto p-3">
        <AppSidebarNav :collapsed="collapsed" />
      </nav>

      <div class="border-t border-line p-3">
        <button
          type="button"
          class="flex w-full items-center rounded-lg px-3 py-2.5 text-sm font-medium text-muted transition-colors hover:bg-hover hover:text-ink"
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
      <div class="absolute inset-0 bg-overlay" data-test="drawer-backdrop" @click="closeMobile" />
      <aside class="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col bg-surface shadow-xl">
        <div class="flex h-16 shrink-0 items-center justify-between border-b border-line px-4">
          <NuxtLink to="/" aria-label="DecOps home" @click="closeMobile">
            <BrandLogo />
          </NuxtLink>
          <button type="button" class="rounded-lg p-2 text-faint hover:bg-hover hover:text-ink" aria-label="Close menu" @click="closeMobile">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.6" stroke="currentColor" class="h-5 w-5" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <nav class="flex-1 overflow-y-auto p-3">
          <AppSidebarNav @navigate="closeMobile" />
        </nav>

        <div class="border-t border-line p-4">
          <p class="truncate text-sm font-medium text-ink">{{ auth.displayName.value }}</p>
          <p class="truncate text-xs text-muted">{{ auth.roleNames.value.join(' · ') || 'No roles assigned' }}</p>
          <button
            type="button"
            class="mt-3 w-full rounded-lg border border-line-strong px-3 py-2 text-sm font-medium text-body hover:bg-hover"
            @click="handleLogout"
          >
            Sign out
          </button>
        </div>
      </aside>
    </div>

    <!-- Content column: padded by the sidebar width on desktop -->
    <div class="flex min-h-screen flex-col transition-[padding] duration-200" :class="collapsed ? 'lg:pl-20' : 'lg:pl-64'">
      <header class="sticky top-0 z-30 border-b border-line bg-surface/90 backdrop-blur">
        <div class="flex h-16 items-center justify-between gap-3 px-4 sm:px-6">
          <div class="flex items-center gap-2">
            <button
              type="button"
              class="rounded-lg p-2 text-muted hover:bg-hover hover:text-ink lg:hidden"
              aria-label="Open menu"
              data-test="mobile-menu-button"
              @click="mobileOpen = true"
            >
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.6" stroke="currentColor" class="h-6 w-6" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
              </svg>
            </button>
            <NuxtLink to="/" class="lg:hidden" aria-label="DecOps home">
              <BrandLogo compact :size="26" />
            </NuxtLink>
          </div>

          <div v-if="auth.isAuthenticated.value" class="flex items-center gap-1 sm:gap-2">
            <ThemeToggle />
            <AppNotifications />
            <span class="mx-1 hidden h-6 w-px bg-line sm:block" aria-hidden="true" />
            <UserMenu />
          </div>
        </div>
      </header>

      <main class="flex-1">
        <slot />
      </main>

      <footer class="border-t border-line bg-surface">
        <div class="mx-auto flex max-w-7xl flex-col gap-1 px-4 py-4 text-xs text-faint sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p>DecOps v1.1 · Internal Operations Management System</p>
          <p>{{ orgName }}</p>
        </div>
      </footer>
    </div>
  </div>
</template>

<script setup lang="ts">
const auth = useAuth()
const api = useApi()

const orgName = useState<string>('ui.org-name', () => 'Interdec Operations')

// Collapsed state persists per browser (desktop rail only).
const collapsed = useState<boolean>('ui.sidebar-collapsed', () => false)
const mobileOpen = useState<boolean>('ui.mobile-nav-open', () => false)

const STORAGE_KEY = 'decops.sidebar-collapsed'

onMounted(() => {
  try {
    if (localStorage.getItem(STORAGE_KEY) === '1') collapsed.value = true
  } catch {
    /* storage unavailable (private mode) - default expanded */
  }
  void api.get<{ org_name: string; org_tagline: string }>('/api/v1/settings/org')
    .then((org) => {
      orgName.value = [org.org_name, org.org_tagline].filter(Boolean).join(' · ') || 'Interdec Operations'
    })
    .catch(() => undefined)
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
