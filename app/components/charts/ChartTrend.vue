<template>
  <figure class="w-full" role="img" :aria-label="chartLabel">
    <svg :viewBox="`0 0 ${width} ${height}`" class="w-full" xmlns="http://www.w3.org/2000/svg">
      <!-- grid lines -->
      <g v-for="tick in ticks" :key="tick.value">
        <line
          :x1="padLeft" :x2="width - padRight"
          :y1="yFor(tick.value)" :y2="yFor(tick.value)"
          class="stroke-line" stroke-width="1" stroke-dasharray="2 4"
        />
        <text
          :x="padLeft - 8" :y="yFor(tick.value) + 3"
          text-anchor="end" class="fill-faint" font-size="10"
        >{{ tick.value }}</text>
      </g>

      <!-- bars -->
      <g v-for="(point, i) in data" :key="i">
        <rect
          :x="xCenter(i) - barWidth - 1.5"
          :y="yFor(point.completed)"
          :width="barWidth"
          :height="Math.max(plotBottom - yFor(point.completed), point.completed > 0 ? 2 : 0)"
          rx="3" class="fill-brand-500"
        >
          <title>{{ `Completed ${point.completed}` }}</title>
        </rect>
        <rect
          :x="xCenter(i) + 1.5"
          :y="yFor(point.created)"
          :width="barWidth"
          :height="Math.max(plotBottom - yFor(point.created), point.created > 0 ? 2 : 0)"
          rx="3" class="fill-brand-500/35"
        >
          <title>{{ `Created ${point.created}` }}</title>
        </rect>
        <text
          :x="xCenter(i)" :y="plotBottom + 16"
          text-anchor="middle" class="fill-faint" font-size="10"
        >{{ weekLabel(point.week_start) }}</text>
      </g>

      <line
        :x1="padLeft" :x2="width - padRight"
        :y1="plotBottom" :y2="plotBottom"
        class="stroke-line-strong" stroke-width="1"
      />
    </svg>
    <figcaption class="mt-2 flex items-center justify-center gap-5 text-xs text-muted">
      <span class="inline-flex items-center gap-1.5">
        <span class="h-2.5 w-2.5 rounded-sm bg-brand-500" aria-hidden="true" /> Completed
      </span>
      <span class="inline-flex items-center gap-1.5">
        <span class="h-2.5 w-2.5 rounded-sm bg-brand-500/35" aria-hidden="true" /> Created
      </span>
    </figcaption>
  </figure>
</template>

<script setup lang="ts">
const props = defineProps<{
  data: { week_start: string, created: number, completed: number }[]
  label?: string
}>()

const width = 640
const height = 220
const padLeft = 34
const padRight = 8
const padTop = 12
const plotBottom = height - 30

const chartLabel = computed(() => props.label ?? 'Weekly tasks created versus completed')

const peak = computed(() => {
  const values = props.data.flatMap((p) => [p.created, p.completed])
  const max = Math.max(1, ...values)
  const step = max > 40 ? 10 : max > 12 ? 5 : 1
  return Math.ceil(max / step) * step
})

const ticks = computed(() => {
  const step = peak.value > 40 ? 10 : peak.value > 12 ? 5 : 1
  const result = []
  for (let v = 0; v <= peak.value; v += step) result.push({ value: v })
  return result
})

const slot = computed(() => (width - padLeft - padRight) / Math.max(props.data.length, 1))
const barWidth = computed(() => Math.min(Math.max(slot.value * 0.26, 6), 22))

function xCenter(index: number): number {
  return padLeft + index * slot.value + slot.value / 2
}

function yFor(value: number): number {
  const usable = plotBottom - padTop
  return plotBottom - (value / peak.value) * usable
}

function weekLabel(iso: string): string {
  const date = new Date(`${iso}T00:00:00`)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}
</script>
