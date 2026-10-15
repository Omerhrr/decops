<template>
  <div class="rounded-xl border border-slate-200 bg-white p-6">
    <div class="flex items-start justify-between gap-4">
      <div>
        <p class="text-sm font-medium text-slate-500">{{ label }}</p>
        <p class="mt-2 text-3xl font-semibold text-slate-900">{{ value }}</p>
      </div>
      <div v-if="icon" class="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-50 text-lg text-brand-700">
        {{ icon }}
      </div>
    </div>
    <p v-if="note" class="mt-3 text-xs text-slate-400">{{ note }}</p>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  label: string
  value: string | number
  icon?: string
  note?: string
}>()
</script>
