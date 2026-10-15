<template>
  <div class="card relative overflow-hidden p-5 sm:p-6">
    <span
      class="absolute inset-y-0 left-0 w-1"
      :class="accentClass"
      aria-hidden="true"
    />
    <p class="text-sm font-medium text-muted">{{ label }}</p>
    <p class="mt-2 text-3xl font-semibold tracking-tight" :class="valueClass">{{ value }}</p>
    <p v-if="note" class="mt-2 text-xs text-muted">{{ note }}</p>
  </div>
</template>

<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    label: string
    value: string | number
    note?: string
    tone?: 'neutral' | 'positive' | 'warning' | 'danger'
  }>(),
  { tone: 'neutral' },
)

const accentClass = computed(() => ({
  neutral: 'bg-line-strong',
  positive: 'bg-brand-500',
  warning: 'bg-amber-400',
  danger: 'bg-rose-500',
}[props.tone]))

const valueClass = computed(() => ({
  neutral: 'text-ink',
  positive: 'text-ink',
  warning: 'text-ink',
  danger: 'text-rose-600 dark:text-rose-400',
}[props.tone]))
</script>
