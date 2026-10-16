<template>
  <span
    class="inline-flex items-center whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium"
    :class="{
      'bg-brand-50 text-brand-700 dark:bg-brand-500/10 dark:text-brand-300': tone === 'green',
      'bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300': tone === 'amber',
      'bg-sky-50 text-sky-700 dark:bg-sky-500/10 dark:text-sky-300': tone === 'blue',
      'bg-violet-50 text-violet-700 dark:bg-violet-500/10 dark:text-violet-300': tone === 'violet',
      'bg-hover text-muted': tone === 'gray',
      'bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300': tone === 'rose',
    }"
  >
    <slot />
  </span>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ tone?: 'green' | 'amber' | 'blue' | 'violet' | 'gray' | 'rose' }>(), { tone: 'gray' })
</script>
