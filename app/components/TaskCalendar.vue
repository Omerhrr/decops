<template>
  <section class="card mt-4 p-4" data-test="task-calendar" aria-label="Task calendar">
    <div class="flex items-center justify-between">
      <button type="button" class="btn-secondary px-3 py-1.5" aria-label="Previous month" @click="shift(-1)">‹</button>
      <h2 class="text-sm font-semibold text-ink">{{ title }}</h2>
      <button type="button" class="btn-secondary px-3 py-1.5" aria-label="Next month" @click="shift(1)">›</button>
    </div>
    <div class="mt-3 grid grid-cols-7 gap-px overflow-hidden rounded-xl border border-line bg-line text-xs">
      <div v-for="d in ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']" :key="d" class="bg-elevated px-2 py-1 text-center font-medium text-muted">{{ d }}</div>
      <div v-for="cell in cells" :key="cell.key" class="min-h-20 bg-surface p-1" :class="cell.inMonth ? '' : 'opacity-40'">
        <p class="text-right text-[11px]" :class="cell.today ? 'font-bold text-brand-700 dark:text-brand-300' : 'text-muted'">{{ cell.day }}</p>
        <NuxtLink
          v-for="t in cell.tasks.slice(0, 3)" :key="t.id" :to="`/tasks/${t.id}`"
          class="mt-0.5 block truncate rounded px-1 py-0.5"
          :class="isOverdue(t.due_date, t.status) ? 'bg-rose-100 text-rose-800 dark:bg-rose-500/20 dark:text-rose-200' : 'bg-hover text-body'"
          :title="`${t.task_number} ${t.title}`"
        >{{ t.title }}</NuxtLink>
        <p v-if="cell.tasks.length > 3" class="mt-0.5 text-[11px] text-muted">+{{ cell.tasks.length - 3 }} more</p>
      </div>
    </div>
    <p class="mt-2 text-xs text-muted">Tasks are placed on their due date.</p>
  </section>
</template>

<script setup lang="ts">
import type { Task } from '~/types/api'

const props = defineProps<{ tasks: Task[] }>()
const cursor = ref(new Date(new Date().getFullYear(), new Date().getMonth(), 1))

const title = computed(() => cursor.value.toLocaleDateString(undefined, { month: 'long', year: 'numeric' }))
function shift(n: number): void {
  cursor.value = new Date(cursor.value.getFullYear(), cursor.value.getMonth() + n, 1)
}
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

const cells = computed(() => {
  const first = cursor.value
  const offset = (first.getDay() + 6) % 7 // Monday-first
  const start = new Date(first.getFullYear(), first.getMonth(), 1 - offset)
  const today = iso(new Date())
  const byDay: Record<string, Task[]> = {}
  for (const t of props.tasks) if (t.due_date) (byDay[t.due_date.slice(0, 10)] ??= []).push(t)
  return Array.from({ length: 42 }, (_, i) => {
    const d = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i)
    const key = iso(d)
    return { key, day: d.getDate(), inMonth: d.getMonth() === first.getMonth(), today: key === today, tasks: byDay[key] ?? [] }
  })
})
</script>
