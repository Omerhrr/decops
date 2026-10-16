<template>
  <section class="rounded-2xl border border-line bg-surface p-5">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div>
        <h2 class="text-sm font-semibold text-ink">Timeline (Gantt)</h2>
        <p class="mt-1 text-xs text-faint">
          Stage bars with milestones as diamonds; lines show which work blocks which.
        </p>
      </div>
      <div class="flex items-center gap-3 text-xs text-faint">
        <span class="flex items-center gap-1"><span class="inline-block h-2 w-4 rounded-sm bg-brand-500" /> stage</span>
        <span class="flex items-center gap-1"><span class="inline-block h-2 w-4 rounded-sm bg-line-strong" /> done/cancelled</span>
        <span class="flex items-center gap-1"><span class="inline-block h-2 w-2 rotate-45 bg-amber-500" /> milestone</span>
        <span class="flex items-center gap-1"><span class="inline-block h-3 w-px bg-rose-400" /> today</span>
      </div>
    </div>

    <div v-if="!rows.length" class="mt-4 rounded-xl bg-elevated px-4 py-6 text-center text-sm text-faint">
      Add stages with dates to see the timeline.
    </div>

    <div v-else class="mt-4 overflow-x-auto">
      <svg :viewBox="`0 0 ${width} ${height}`" :width="width" :height="height" class="min-w-full" role="img" aria-label="Workflow Gantt chart">
        <!-- month/week grid -->
        <g v-for="tick in ticks" :key="`tick-${tick.x}`">
          <line :x1="tick.x" :x2="tick.x" y1="18" :y2="height - 8" class="stroke-line" stroke-width="1" />
          <text :x="tick.x + 4" y="12" class="fill-faint" font-size="10">{{ tick.label }}</text>
        </g>

        <!-- today marker -->
        <line v-if="todayX !== null" :x1="todayX" :x2="todayX" y1="18" :y2="height - 8" class="stroke-rose-400" stroke-width="1.5" stroke-dasharray="4 3" />

        <!-- dependency lines (successor start <- predecessor end) -->
        <g v-for="dep in dependencyPaths" :key="`dep-${dep.id}`">
          <path :d="dep.d" fill="none" class="stroke-faint" stroke-width="1.2" stroke-dasharray="3 2" marker-end="url(#arrow)" />
        </g>
        <defs>
          <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0,0 L8,4 L0,8 z" class="fill-faint" />
          </marker>
        </defs>

        <!-- rows -->
        <g v-for="(row, index) in rows" :key="row.key">
          <text x="0" :y="rowY(index) + 14" class="fill-body" font-size="11" font-weight="600">
            {{ row.label.length > 34 ? `${row.label.slice(0, 33)}…` : row.label }}
          </text>
          <template v-if="row.kind === 'stage' && row.x1 !== null && row.x2 !== null">
            <rect
              :x="row.x1" :y="rowY(index) + 2" :width="Math.max(row.x2 - row.x1, 4)" height="16" rx="8"
              :fill="row.fill" opacity="0.9"
            />
            <text :x="row.x1 + 6" :y="rowY(index) + 14" font-size="10" class="fill-white" font-weight="600">
              {{ row.percent }}%
            </text>
          </template>
          <template v-else-if="row.kind === 'milestone' && row.x1 !== null">
            <path
              :d="diamondPath(row.x1, rowY(index) + 10, 5)"
              :fill="row.fill" class="stroke-surface" stroke-width="1"
            />
          </template>
        </g>
      </svg>
    </div>
    <p v-if="undatedCount" class="mt-2 text-xs text-faint">
      {{ undatedCount }} item(s) without dates are not shown on the timeline.
    </p>
  </section>
</template>

<script setup lang="ts">
import type { WorkItem, Workflow, WorkflowStage } from '~/types/api'

const props = defineProps<{ workflow: Workflow, taskStart: string | null, taskDue: string | null }>()

const ROW_H = 30
const TOP = 24
const LEFT = 260
const RIGHT = 40
const width = 980

const stageRows = computed(() => {
  const rows: { key: string, kind: 'stage' | 'milestone', label: string, start: string, end: string, fill: string, percent: number }[] = []
  for (const stage of props.workflow.stages) {
    const start = stage.start_date ?? props.taskStart ?? earliest(props.workflow)
    const end = stage.due_date ?? props.taskDue ?? latest(props.workflow)
    if (!start || !end) continue
    rows.push({
      key: stage.id, kind: 'stage', label: `${stage.sequence_number}. ${stage.name}`,
      start, end,
      fill: barFill(stage.status),
      percent: stageProgressPercent(stage.id),
    })
    for (const m of milestoneRows(stage)) {
      rows.push({ key: m.id, kind: 'milestone', label: `◆ ${m.title}`, start: m.due_date!, end: m.due_date!, fill: milestoneFill(m), percent: 0 })
    }
  }
  return rows
})

const rows = computed(() =>
  stageRows.value.map(r => ({ ...r, x1: xOf(r.start), x2: xOf(r.end) })),
)
const height = computed(() => TOP + rows.value.length * ROW_H + 16)
const undatedCount = computed(() => props.workflow.items.filter(i => i.item_type === 'milestone' && !i.due_date).length)

function rowY(index: number): number {
  return TOP + index * ROW_H
}

function earliest(wf: Workflow): string | null {
  const dates = [...wf.stages.map(s => s.start_date).filter(Boolean)] as string[]
  return dates.length ? dates.sort()[0] : null
}
function latest(wf: Workflow): string | null {
  const dates = [...wf.stages.map(s => s.due_date).filter(Boolean)] as string[]
  return dates.length ? dates.sort().at(-1)! : null
}

function barFill(status: string): string {
  if (status === 'completed') return 'var(--line-strong)'
  if (status === 'cancelled') return 'var(--line)'
  if (status === 'in_progress') return 'var(--brand-500)'
  return 'color-mix(in srgb, var(--brand-500) 35%, transparent)'
}
function milestoneFill(m: WorkItem): string {
  if (m.status === 'completed') return 'var(--line-strong)'
  if (m.status === 'in_progress') return '#d97706'
  return '#f59e0b'
}

function milestoneRows(stage: WorkflowStage): WorkItem[] {
  return props.workflow.items.filter(
    i => i.stage_id === stage.id && i.item_type === 'milestone' && i.due_date,
  )
}
function stageProgressPercent(stageId: string): number {
  return props.workflow.progress.stages.find(s => s.stage_id === stageId)?.percent ?? 0
}

const domain = computed<[number, number] | null>(() => {
  // Reads stageRows (raw dates) - never `rows`, which itself derives from
  // the domain via xOf (a cycle would throw "rows.value is not iterable").
  const dates: string[] = []
  for (const r of stageRows.value) { dates.push(r.start, r.end) }
  if (props.taskStart) dates.push(props.taskStart)
  if (props.taskDue) dates.push(props.taskDue)
  if (!dates.length) return null
  const times = dates.map(d => new Date(d).getTime()).filter(t => !Number.isNaN(t))
  const min = Math.min(...times)
  const max = Math.max(...times)
  if (!Number.isFinite(min) || !Number.isFinite(max)) return null
  const span = Math.max(max - min, 7 * 86400_000)
  return [min, min + span]
})

function xOf(dateStr: string): number | null {
  const [min, max] = domain.value ?? [0, 0]
  const t = new Date(dateStr).getTime()
  if (Number.isNaN(t)) return null
  return LEFT + (Math.min(Math.max(t, min), max) - min) / (max - min) * (width - LEFT - RIGHT)
}

const ticks = computed(() => {
  const [min, max] = domain.value ?? [0, 0]
  if (!min) return []
  const out: { x: number, label: string }[] = []
  const cursor = new Date(min)
  cursor.setDate(1)
  while (cursor.getTime() <= max && out.length < 14) {
    const x = xOf(cursor.toISOString().slice(0, 10))
    if (x !== null && x >= LEFT) {
      out.push({ x, label: cursor.toLocaleDateString(undefined, { month: 'short', year: '2-digit' }) })
    }
    cursor.setMonth(cursor.getMonth() + 1)
  }
  return out
})

const todayX = computed(() => xOf(new Date().toISOString().slice(0, 10)))

function diamondPath(cx: number, cy: number, r: number): string {
  return `M${cx},${cy - r} L${cx + r},${cy} L${cx},${cy + r} L${cx - r},${cy} Z`
}

const dependencyPaths = computed(() => {
  const out: { id: string, d: string }[] = []
  const stageById = new Map(props.workflow.stages.map(s => [s.id, s]))
  const itemById = new Map(props.workflow.items.map(i => [i.id, i]))
  for (const dep of props.workflow.dependencies) {
    const pred = itemById.get(dep.predecessor_id)
    const succ = itemById.get(dep.successor_id)
    if (!pred || !succ) continue
    // Row positions: milestones are rows; subtasks map to their stage row.
    const predRow = rows.value.findIndex(r => r.key === pred.id || r.key === pred.stage_id)
    const succRow = rows.value.findIndex(r => r.key === succ.id || r.key === succ.stage_id)
    if (predRow < 0 || succRow < 0) continue
    const x1 = xOf(pred.due_date ?? stageById.get(pred.stage_id)?.due_date ?? '')
    const x2 = xOf(succ.start_date ?? succ.due_date ?? '')
    if (x1 === null || x2 === null) continue
    const y1 = rowY(predRow) + 10
    const y2 = rowY(succRow) + 10
    const midX = (x1 + x2) / 2
    out.push({ id: dep.id, d: `M${x1},${y1} C${midX},${y1} ${midX},${y2} ${x2},${y2}` })
  }
  return out
})
</script>
