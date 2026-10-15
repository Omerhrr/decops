<template>
  <div ref="rootEl" class="relative">
    <button
      type="button"
      class="rounded-lg p-2 text-muted transition-colors hover:bg-hover hover:text-ink"
      :aria-label="`Theme: ${label}`"
      :aria-expanded="open"
      aria-haspopup="menu"
      data-test="theme-toggle"
      @click="open = !open"
    >
      <svg v-if="appearance.resolvedMode.value === 'dark'" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.6" stroke="currentColor" class="h-5 w-5" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" d="M21.752 15.002A9.72 9.72 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z" />
      </svg>
      <svg v-else xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.6" stroke="currentColor" class="h-5 w-5" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z" />
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
        class="absolute right-0 z-50 mt-2 w-44 overflow-hidden rounded-xl border border-line bg-surface py-1 shadow-xl"
        role="menu"
        :aria-label="'Theme'"
      >
        <button
          v-for="option in THEME_MODES"
          :key="option.value"
          type="button"
          role="menuitemradio"
          :aria-checked="appearance.state.value.mode === option.value"
          class="flex w-full items-center justify-between px-3 py-2 text-sm transition-colors hover:bg-hover"
          :class="appearance.state.value.mode === option.value ? 'font-semibold text-ink' : 'text-body'"
          @click="select(option.value)"
        >
          {{ option.label }}
          <svg v-if="appearance.state.value.mode === option.value" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="h-4 w-4 text-brand-600 dark:text-brand-400" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" />
          </svg>
        </button>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
const appearance = useAppearance()
const rootEl = ref<HTMLElement | null>(null)
const open = ref(false)

const label = computed(() => THEME_MODES.find(m => m.value === appearance.state.value.mode)?.label ?? 'System')

function select(mode: ThemeMode): void {
  appearance.setMode(mode)
  open.value = false
}

function onDocumentClick(event: MouseEvent): void {
  if (open.value && rootEl.value && !rootEl.value.contains(event.target as Node)) {
    open.value = false
  }
}

onMounted(() => document.addEventListener('click', onDocumentClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocumentClick))
</script>
