<template>
  <span
    class="inline-flex items-center whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium"
    :class="{
      'bg-brand-50 dark:bg-brand-500/10 text-brand-700 dark:text-brand-300 dark:bg-brand-500/10 dark:text-brand-300': tone === 'green',
      'bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300 dark:bg-amber-500/10 dark:text-amber-300': tone === 'amber',
      'bg-sky-50 dark:bg-sky-500/10 text-sky-700 dark:text-sky-300 dark:bg-sky-500/10 dark:text-sky-300': tone === 'blue',
      'bg-hover text-muted': tone === 'gray',
      'bg-rose-50 dark:bg-rose-500/10 text-rose-700 dark:text-rose-300 dark:bg-rose-500/10 dark:text-rose-300': tone === 'rose',
    }"
  >
    <slot />
  </span>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ tone?: 'green' | 'amber' | 'blue' | 'gray' | 'rose' }>(), { tone: 'gray' })
</script>
