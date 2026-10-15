<template>
  <nav :aria-label="collapsed ? 'Main (collapsed)' : 'Main'" class="space-y-4">
    <div v-for="section in sections" :key="section.label">
      <p
        v-if="!collapsed && section.items.length"
        class="mb-1 px-3 text-[11px] font-semibold uppercase tracking-wider text-faint"
      >
        {{ section.label }}
      </p>
      <div class="space-y-1" :class="collapsed && 'border-t border-line pt-2 first:border-0 first:pt-0'">
        <NuxtLink
          v-for="item in section.items"
          :key="item.to"
          :to="item.to"
          :title="collapsed ? item.label : undefined"
          class="group relative flex items-center rounded-lg text-sm font-medium transition-colors"
          :class="[
            collapsed ? 'justify-center px-2 py-2.5' : 'gap-3 px-3 py-2.5',
            isActive(item)
              ? 'bg-brand-50 dark:bg-brand-500/10 text-brand-700 dark:text-brand-300 dark:bg-brand-500/10 dark:text-brand-300'
              : 'text-body hover:bg-hover hover:text-ink',
          ]"
          :aria-current="isActive(item) ? 'page' : undefined"
          @click="emit('navigate')"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            stroke-width="1.6"
            stroke="currentColor"
            class="h-5 w-5 shrink-0"
            :class="isActive(item) ? 'text-brand-600 dark:text-brand-400' : 'text-faint group-hover:text-body'"
            aria-hidden="true"
          >
            <path stroke-linecap="round" stroke-linejoin="round" :d="iconPath(item.icon)" />
          </svg>
          <span v-if="!collapsed" class="truncate">{{ item.label }}</span>
          <span
            v-if="isActive(item)"
            class="absolute left-0 top-1/2 h-6 w-1 -translate-y-1/2 rounded-r-full bg-brand-600"
            aria-hidden="true"
          />
        </NuxtLink>
      </div>
    </div>
  </nav>
</template>

<script setup lang="ts">
const ICONS = {
  home: 'M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75',
  tasks: 'M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25zM6.75 12h.008v.008H6.75V12zm0 3h.008v.008H6.75V15zm0 3h.008v.008H6.75V18z',
  myTasks: 'M9 5.25H6A2.25 2.25 0 003.75 7.5v12a2.25 2.25 0 002.25 2.25h9a2.25 2.25 0 002.25-2.25v-1.5m-6-13.5L16.5 3.75l3.75 3.75-6 6-4.5.75.75-4.5 4.5-4.5z',
  reports: 'M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z',
  users: 'M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z',
  departments: 'M2.25 21h19.5m-18-18v18m10.5-18v18m6-13.5V21M6.75 6.75h.75m-.75 3h.75m-.75 3h.75m3-6h.75m-.75 3h.75m-.75 3h.75M6.75 21v-3.375c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21',
  imports: 'M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z',
  settings: 'M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z M15 12a3 3 0 11-6 0 3 3 0 016 0z',
} as const

interface NavItem {
  to: string
  label: string
  icon: keyof typeof ICONS
  exact?: boolean
}

interface NavSection {
  label: string
  items: NavItem[]
}

withDefaults(defineProps<{ collapsed?: boolean }>(), { collapsed: false })
const emit = defineEmits<{ navigate: [] }>()

const auth = useAuth()
const route = useRoute()

const sections = computed<NavSection[]>(() => {
  const workspace: NavItem[] = [
    { to: '/', label: 'Dashboard', icon: 'home', exact: true },
    // The register lists engine-authorized tasks only, so it is safe for everyone.
    { to: '/tasks', label: 'Tasks', icon: 'tasks' },
    { to: '/my-tasks', label: 'My Tasks', icon: 'myTasks' },
  ]
  const insights: NavItem[] = []
  // Department workspaces and reports re-use the reporting permission matrix:
  // leads see their departments, management sees everything they may view.
  if (auth.hasPermission('reports.view', 'reports.department.view', 'workload.view')) {
    insights.push({ to: '/departments', label: 'Departments', icon: 'departments' })
  }
  if (auth.hasPermission('reports.view', 'reports.department.view', 'exports.approved')) {
    insights.push({ to: '/reports', label: 'Reports', icon: 'reports' })
  }
  const administration: NavItem[] = []
  if (auth.hasPermission('users.manage')) {
    administration.push({ to: '/admin/users', label: 'Users', icon: 'users' })
  }
  if (auth.hasPermission('departments.manage', 'users.manage')) {
    administration.push({ to: '/admin/departments', label: 'Departments Admin', icon: 'departments' })
  }
  // Import center: Company Administration only (spec restriction).
  if (auth.hasPermission('imports.manage', 'imports.view')) {
    administration.push({ to: '/imports', label: 'Imports', icon: 'imports' })
  }
  const general: NavItem[] = [
    { to: '/settings', label: 'Settings', icon: 'settings' },
  ]
  return [
    { label: 'Workspace', items: workspace },
    { label: 'Insights', items: insights },
    { label: 'Administration', items: administration },
    { label: 'General', items: general },
  ].filter((s) => s.items.length)
})

function isActive(item: NavItem): boolean {
  return item.exact ? route.path === item.to : route.path.startsWith(item.to)
}

function iconPath(icon: keyof typeof ICONS): string {
  return ICONS[icon]
}
</script>
