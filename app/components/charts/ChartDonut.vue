<template>
  <figure class="flex flex-col items-center gap-4" role="img" :aria-label="chartLabel">
    <svg :viewBox="`0 0 ${size} ${size}`" class="h-36 w-36 shrink-0" xmlns="http://www.w3.org/2000/svg">
      <g transform="rotate(-90 70 70)">
        <circle
          v-for="(segment, i) in segments"
          :key="i"
          cx="70" cy="70" r="52"
          fill="none"
          :stroke="segment.color"
          stroke-width="24"
          :stroke-dasharray="`${segment.length} ${circumference - segment.length}`"
          :stroke-dashoffset="`${-segment.offset}`"
          class="transition-[stroke-dasharray] duration-300"
        >
          <title>{{ `${segment.label}: ${segment.value}` }}</title>
        </circle>
      </g>
      <text x="70" y="66" text-anchor="middle" class="fill-ink" :font-size="total >= 1000 ? 21 : 26" font-weight="600">{{ total }}</text>
      <text x="70" y="84" text-anchor="middle" class="fill-faint" font-size="10" letter-spacing="1">TASKS</text>
    </svg>

    <ul class="grid w-full max-w-xs grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
      <li
        v-for="segment in segments"
        :key="segment.label"
        class="flex min-w-0 items-center gap-2"
      >
        <span class="h-2.5 w-2.5 shrink-0 rounded-full" :style="{ backgroundColor: segment.color }" aria-hidden="true" />
        <span class="min-w-0 truncate text-muted" :title="segment.label">{{ segment.label }}</span>
        <span class="ml-auto shrink-0 font-semibold tabular-nums text-ink">{{ segment.value }}</span>
      </li>
    </ul>
  </figure>
</template>

<script setup lang="ts">
const props = defineProps<{
  breakdown: Record<string, number>
}>()

const size = 140
const circumference = 2 * Math.PI * 52

const STATUS_STYLES: Record<string, { label: string, color: string }> = {
  draft: { label: 'Draft', color: '#94a3b8' },
  open: { label: 'Open', color: '#0ea5e9' },
  in_progress: { label: 'In progress', color: '#f59e0b' },
  blocked: { label: 'Blocked', color: '#f43f5e' },
  under_review: { label: 'Under review', color: '#8b5cf6' },
  completed: { label: 'Completed', color: '#10b981' },
  cancelled: { label: 'Cancelled', color: '#64748b' },
  archived: { label: 'Archived', color: '#475569' },
}

const total = computed(() =>
  Object.values(props.breakdown).reduce((sum, n) => sum + n, 0),
)

const segments = computed(() => {
  const entries = Object.entries(props.breakdown).filter(([, value]) => value > 0)
  let offset = 0
  return entries.map(([status, value]) => {
    const length = total.value > 0 ? (value / total.value) * circumference : 0
    const segment = {
      label: STATUS_STYLES[status]?.label ?? status,
      color: STATUS_STYLES[status]?.color ?? '#94a3b8',
      value,
      length,
      offset,
    }
    offset += length
    return segment
  })
})

const chartLabel = computed(() => `Tasks by status, ${total.value} total`)
</script>
