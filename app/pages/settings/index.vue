<template>
  <div class="mx-auto max-w-6xl px-4 py-8 sm:px-6">
    <header class="mb-6">
      <h1 class="page-title">Settings</h1>
      <p class="page-subtitle">
        Personalize the workspace, brand your PDF exports, and administer access.
      </p>
    </header>

    <div class="flex flex-col gap-6 lg:flex-row">
      <nav aria-label="Settings sections" class="lg:w-56 lg:shrink-0">
        <ul class="flex gap-1 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible lg:pb-0">
          <li v-for="tab in visibleTabs" :key="tab.key">
            <NuxtLink
              :to="`/settings?tab=${tab.key}`"
              replace
              class="flex items-center gap-2.5 whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium transition-colors"
              :class="activeTab === tab.key
                ? 'bg-brand-50 text-brand-700 dark:bg-brand-500/10 dark:text-brand-300'
                : 'text-body hover:bg-hover hover:text-ink'"
              :aria-current="activeTab === tab.key ? 'page' : undefined"
            >
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.6" stroke="currentColor" class="h-5 w-5" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" :d="tab.icon" />
              </svg>
              {{ tab.label }}
            </NuxtLink>
          </li>
        </ul>
      </nav>

      <div class="min-w-0 flex-1">
        <AppearanceSettings v-if="activeTab === 'appearance'" />
        <PdfDesignSettings v-else-if="activeTab === 'pdf'" />
        <RolesPermissions v-else-if="activeTab === 'roles'" />
        <UsersAccess v-else-if="activeTab === 'users'" />
        <OrganizationSettings v-else-if="activeTab === 'organization'" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const auth = useAuth()
const route = useRoute()

const TABS = [
  {
    key: 'appearance',
    label: 'Appearance',
    icon: 'M4.5 12a7.5 7.5 0 1015 0 7.5 7.5 0 00-15 0z M12 3v2.25m0 13.5V21m9-9h-2.25M5.25 12H3m15.364-6.364l-1.591 1.591M7.227 16.773l-1.591 1.591m0-13.5l1.591 1.591m9.546 9.546l1.591 1.591',
    permissions: [] as string[],
  },
  {
    key: 'pdf',
    label: 'PDF Exports',
    icon: 'M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z',
    permissions: ['settings.org.manage', 'system.settings.manage'],
  },
  {
    key: 'roles',
    label: 'Roles & Permissions',
    icon: 'M13.5 10.5V6.75a4.5 4.5 0 119 0v3.75M3.75 21.75h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H3.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z',
    permissions: ['roles.assign'],
  },
  {
    key: 'users',
    label: 'Users & Access',
    icon: 'M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z',
    permissions: ['users.manage'],
  },
  {
    key: 'organization',
    label: 'Organization',
    icon: 'M2.25 21h19.5m-18-18v18m10.5-18v18m6-13.5V21M6.75 6.75h.75m-.75 3h.75m-.75 3h.75m3-6h.75m-.75 3h.75m-.75 3h.75M6.75 21v-3.375c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21',
    permissions: ['settings.org.manage', 'system.settings.manage'],
  },
] as const

const visibleTabs = computed(() =>
  TABS.filter((tab) => auth.hasPermission(...tab.permissions)),
)

const activeTab = computed(() => {
  const requested = typeof route.query.tab === 'string' ? route.query.tab : 'appearance'
  return visibleTabs.value.some((t) => t.key === requested) ? requested : 'appearance'
})

useHead({ title: 'Settings - DecOps' })
</script>
