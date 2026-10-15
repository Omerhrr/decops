<template>
  <figure class="w-full space-y-3" role="img" :aria-label="chartLabel">
    <div v-for="row in rows" :key="row.name" class="grid grid-cols-[minmax(5rem,9rem)_1fr_2.5rem] items-center gap-3">
      <span class="truncate text-xs font-medium text-body" :title="row.name">{{ row.name }}</span>
      <span class="h-3 overflow-hidden rounded-full bg-hover">
        <span
          class="block h-full rounded-full bg-brand-500/40"
          :style="{ width: `${(row.total / maxValue) * 100}%` }"
          :title="`${row.total} total`"
        >
          <span
            class="block h-full rounded-full bg-brand-500"
            :style="{ width: `${row.total > 0 ? (row.active / row.total) * 100 : 0}%` }"
            :title="`${row.active} active`"
          />
        </span>
      </span>
      <span class="text-right text-xs font-semibold text-ink">{{ row.total }}</span>
    </div>
    <figcaption class="flex items-center gap-5 pt-1 text-xs text-muted">
      <span class="inline-flex items-center gap-1.5">
        <span class="h-2.5 w-2.5 rounded-sm bg-brand-500" aria-hidden="true" /> Active
      </span>
      <span class="inline-flex items-center gap-1.5">
        <span class="h-2.5 w-2.5 rounded-sm bg-brand-500/40" aria-hidden="true" /> Total visible
      </span>
    </figcaption>
  </figure>
</template>

<script setup lang="ts">
const props = defineProps<{
  rows: { name: string, total: number, active: number }[]
}>()

const chartLabel = computed(() => 'Task load by department')

const maxValue = computed(() => Math.max(1, ...props.rows.map((r) => r.total)))
</script>
