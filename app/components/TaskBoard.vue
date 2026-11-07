<template>
  <div class="mt-4 flex gap-3 overflow-x-auto pb-3" data-test="task-board">
    <section
      v-for="col in columns" :key="col"
      class="flex w-64 shrink-0 flex-col rounded-2xl border border-line bg-elevated"
      :class="over === col ? 'ring-2 ring-brand-500' : ''"
      :aria-label="`${label(col)} column`"
      @dragover.prevent="over = col"
      @dragleave="over = ''"
      @drop.prevent="drop(col)"
    >
      <header class="flex items-center justify-between px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted">
        <span>{{ label(col) }}</span><span>{{ byStatus[col]?.length ?? 0 }}</span>
      </header>
      <ul class="min-h-16 space-y-2 px-2 pb-3">
        <li
          v-for="t in byStatus[col] ?? []" :key="t.id"
          class="card cursor-grab p-3 text-sm" draggable="true"
          @dragstart="dragging = t.id" @dragend="dragging = ''; over = ''"
        >
          <NuxtLink :to="`/tasks/${t.id}`" class="font-medium text-ink hover:text-brand-700">{{ t.title }}</NuxtLink>
          <div class="mt-1 flex items-center justify-between text-xs text-muted">
            <span class="font-mono">{{ t.task_number }}</span>
            <AppBadge :tone="priorityTone(t.priority)">{{ capitalize(t.priority) }}</AppBadge>
          </div>
          <p class="mt-1 text-xs" :class="isOverdue(t.due_date, t.status) ? 'font-medium text-rose-600 dark:text-rose-400' : 'text-muted'">Due {{ formatDate(t.due_date) }}</p>
          <label class="mt-2 block">
            <span class="sr-only">Move {{ t.task_number }} to</span>
            <select class="select-field !py-1 text-xs" :value="col" @change="emit('move', t.id, ($event.target as HTMLSelectElement).value)">
              <option v-for="s in columns" :key="s" :value="s">{{ label(s) }}</option>
            </select>
          </label>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts">
import type { Task } from '~/types/api'

const props = defineProps<{ tasks: Task[] }>()
const emit = defineEmits<{ (e: 'move', id: string, status: string): void }>()

const columns = ['draft', 'open', 'in_progress', 'blocked', 'under_review', 'completed']
const dragging = ref('')
const over = ref('')
const label = (s: string) => capitalize(s.replaceAll('_', ' '))

const byStatus = computed(() => {
  const out: Record<string, Task[]> = {}
  for (const t of props.tasks) (out[t.status] ??= []).push(t)
  return out
})

function drop(status: string): void {
  const id = dragging.value
  over.value = ''
  dragging.value = ''
  const task = props.tasks.find(t => t.id === id)
  if (task && task.status !== status) emit('move', id, status)
}
</script>
