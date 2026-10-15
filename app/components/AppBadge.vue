<template>
  <span
    class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium"
    :class="{
      'bg-brand-50 text-brand-700': tone === 'green',
      'bg-amber-50 text-amber-700': tone === 'amber',
      'bg-slate-100 text-slate-600': tone === 'gray',
      'bg-rose-50 text-rose-700': tone === 'rose',
    }"
  >
    <slot />
  </span>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ tone?: 'green' | 'amber' | 'gray' | 'rose' }>(), { tone: 'gray' })
</script>
