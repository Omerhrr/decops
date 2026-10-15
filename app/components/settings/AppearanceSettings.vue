<template>
  <div class="space-y-6">
    <section class="card p-5 sm:p-6" aria-labelledby="appearance-mode">
      <h2 id="appearance-mode" class="text-base font-semibold text-ink">Theme mode</h2>
      <p class="page-subtitle">Choose how DecOps looks. System follows your device setting.</p>
      <div class="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3" role="radiogroup" aria-label="Theme mode">
        <button
          v-for="option in THEME_MODES"
          :key="option.value"
          type="button"
          role="radio"
          :aria-checked="appearance.state.value.mode === option.value"
          class="rounded-xl border p-4 text-left transition-colors"
          :class="appearance.state.value.mode === option.value
            ? 'border-brand-500 ring-2 ring-brand-500/25'
            : 'border-line hover:border-line-strong'"
          @click="appearance.setMode(option.value)"
        >
          <span class="flex items-center justify-between">
            <span class="text-sm font-semibold text-ink">{{ option.label }}</span>
            <svg v-if="appearance.state.value.mode === option.value" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="h-4 w-4 text-brand-600 dark:text-brand-400" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" />
            </svg>
          </span>
          <span
            class="mt-3 block h-14 overflow-hidden rounded-lg border"
            :class="option.value === 'dark'
              || (option.value === 'system' && appearance.resolvedMode.value === 'dark')
              ? 'bg-[#0b1220]'
              : 'bg-[#eef1f5]'"
            aria-hidden="true"
          >
            <span class="flex h-full gap-1.5 p-2">
              <span
                class="w-1/4 rounded"
                :class="option.value === 'dark'
                  || (option.value === 'system' && appearance.resolvedMode.value === 'dark')
                  ? 'bg-[#111a2c]'
                  : 'bg-white'"
              />
              <span class="flex-1 space-y-1.5">
                <span
                  class="block h-3 rounded"
                  :class="option.value === 'dark'
                    || (option.value === 'system' && appearance.resolvedMode.value === 'dark')
                    ? 'bg-[#1b2740]'
                    : 'bg-slate-200'"
                />
                <span class="block h-3 w-2/3 rounded bg-brand-500/70" />
              </span>
            </span>
          </span>
          <span class="mt-2 block text-xs text-muted">{{ option.hint }}</span>
        </button>
      </div>
    </section>

    <section class="card p-5 sm:p-6" aria-labelledby="appearance-accent">
      <h2 id="appearance-accent" class="text-base font-semibold text-ink">Accent color</h2>
      <p class="page-subtitle">Used for buttons, highlights, charts and active navigation.</p>
      <div class="mt-4 flex flex-wrap gap-3" role="radiogroup" aria-label="Accent color">
        <button
          v-for="color in ACCENT_COLORS"
          :key="color.value"
          type="button"
          role="radio"
          :aria-checked="appearance.state.value.accent === color.value"
          :aria-label="color.label"
          class="group relative flex h-11 w-11 items-center justify-center rounded-full transition-transform hover:scale-105"
          @click="appearance.setAccent(color.value)"
        >
          <span class="h-8 w-8 rounded-full ring-1 ring-black/10" :style="{ backgroundColor: color.swatch }" aria-hidden="true" />
          <span
            v-if="appearance.state.value.accent === color.value"
            class="absolute inset-0 rounded-full ring-2 ring-offset-2 ring-brand-600 ring-offset-surface"
            aria-hidden="true"
          />
        </button>
      </div>
    </section>

    <section class="card p-5 sm:p-6" aria-labelledby="appearance-font">
      <h2 id="appearance-font" class="text-base font-semibold text-ink">Font</h2>
      <p class="page-subtitle">The typeface used across the interface.</p>
      <div class="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4" role="radiogroup" aria-label="Interface font">
        <button
          v-for="font in FONT_CHOICES"
          :key="font.value"
          type="button"
          role="radio"
          :aria-checked="appearance.state.value.font === font.value"
          class="rounded-xl border p-4 text-left transition-colors"
          :class="appearance.state.value.font === font.value
            ? 'border-brand-500 ring-2 ring-brand-500/25'
            : 'border-line hover:border-line-strong'"
          @click="appearance.setFont(font.value)"
        >
          <span class="block text-lg text-ink" :style="{ fontFamily: font.stack }">Aa</span>
          <span class="mt-1 block text-xs font-medium text-body">{{ font.label }}</span>
        </button>
      </div>
    </section>

    <p v-if="savedFlash" role="status" class="text-sm text-brand-700 dark:text-brand-300">
      Preferences saved to your profile.
    </p>
  </div>
</template>

<script setup lang="ts">
const appearance = useAppearance()
const savedFlash = ref(false)

// The composable already applies changes immediately; confirm the server sync
// with a brief status message.
watch(() => [
  appearance.state.value.mode,
  appearance.state.value.accent,
  appearance.state.value.font,
], () => {
  savedFlash.value = true
  window.setTimeout(() => { savedFlash.value = false }, 2500)
})
</script>
