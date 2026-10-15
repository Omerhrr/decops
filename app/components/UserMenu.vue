<template>
  <div ref="rootEl" class="relative">
    <button
      type="button"
      class="flex items-center gap-2.5 rounded-full p-1 pr-2.5 transition-colors hover:bg-hover"
      :aria-expanded="open"
      aria-haspopup="menu"
      :aria-label="'Account menu'"
      data-test="user-menu-button"
      @click="open = !open"
    >
      <span
        class="flex h-8 w-8 items-center justify-center rounded-full bg-brand-600 text-xs font-bold text-white"
        aria-hidden="true"
      >{{ initials }}</span>
      <span class="hidden max-w-[10rem] flex-col items-start leading-tight lg:flex">
        <span class="truncate text-sm font-semibold text-ink">{{ auth.displayName.value }}</span>
        <span class="truncate text-[11px] text-muted">{{ primaryRole }}</span>
      </span>
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="h-3.5 w-3.5 text-faint" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
      </svg>
    </button>

    <transition
      enter-active-class="transition duration-100 ease-out"
      enter-from-class="scale-95 opacity-0"
      enter-to-class="scale-100 opacity-100"
      leave-active-class="transition duration-75 ease-in"
      leave-from-class="scale-100 opacity-100"
      leave-to-class="scale-95 opacity-0"
    >
      <div
        v-if="open"
        class="absolute right-0 z-50 mt-2 w-60 overflow-hidden rounded-xl border border-line bg-surface shadow-xl"
        role="menu"
        aria-label="Account"
        data-test="user-menu"
      >
        <div class="border-b border-line px-4 py-3">
          <p class="truncate text-sm font-semibold text-ink">{{ auth.displayName.value }}</p>
          <p class="truncate text-xs text-muted">{{ auth.user.value?.email }}</p>
          <p class="mt-1 truncate text-[11px] text-faint">{{ auth.roleNames.value.join(' · ') || 'No roles assigned' }}</p>
        </div>
        <div class="py-1">
          <NuxtLink
            v-for="item in menuItems"
            :key="item.to"
            :to="item.to"
            role="menuitem"
            class="flex items-center gap-2.5 px-4 py-2 text-sm text-body transition-colors hover:bg-hover hover:text-ink"
            data-test="user-menu-settings"
            @click="open = false"
          >
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.6" stroke="currentColor" class="h-4 w-4 text-faint" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" :d="item.icon" />
            </svg>
            {{ item.label }}
          </NuxtLink>
        </div>
        <div class="border-t border-line py-1">
          <button
            type="button"
            role="menuitem"
            class="flex w-full items-center gap-2.5 px-4 py-2 text-left text-sm text-rose-600 dark:text-rose-400 transition-colors hover:bg-hover dark:text-rose-400"
            @click="handleLogout"
          >
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.6" stroke="currentColor" class="h-4 w-4" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9" />
            </svg>
            Sign out
          </button>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
const auth = useAuth()
const rootEl = ref<HTMLElement | null>(null)
const open = ref(false)

const ICONS = {
  user: 'M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z',
  tasks: 'M9 5.25H6A2.25 2.25 0 003.75 7.5v12a2.25 2.25 0 002.25 2.25h9a2.25 2.25 0 002.25-2.25v-1.5m-6-13.5L16.5 3.75l3.75 3.75-6 6-4.5.75.75-4.5 4.5-4.5z',
  settings: 'M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z M15 12a3 3 0 11-6 0 3 3 0 016 0z',
}

const menuItems = computed(() => {
  const items = [{ to: '/my-tasks', label: 'My Tasks', icon: ICONS.tasks }]
  items.push({ to: '/settings', label: 'Settings', icon: ICONS.settings })
  return items
})

const initials = computed(() => {
  const parts = auth.displayName.value.trim().split(/\s+/)
  if (parts.length === 0 || !parts[0]) return '?'
  const first = parts[0]!.charAt(0)
  const last = parts.length > 1 ? parts[parts.length - 1]!.charAt(0) : ''
  return (first + last).toUpperCase()
})

const primaryRole = computed(() => auth.roleNames.value[0] ?? 'No roles assigned')

function onDocumentClick(event: MouseEvent): void {
  if (open.value && rootEl.value && !rootEl.value.contains(event.target as Node)) {
    open.value = false
  }
}

async function handleLogout(): Promise<void> {
  open.value = false
  await auth.logout()
}

onMounted(() => document.addEventListener('click', onDocumentClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocumentClick))
</script>
