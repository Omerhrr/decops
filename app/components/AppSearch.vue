<template>
  <div>
    <button type="button" class="flex items-center gap-2 rounded-lg border border-line bg-elevated px-3 py-1.5 text-sm text-muted hover:text-ink" aria-label="Search tasks (Ctrl+K)" data-test="search-open" @click="show">
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.6" stroke="currentColor" class="h-4 w-4" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m21 21-4.35-4.35M17 10.5a6.5 6.5 0 1 1-13 0 6.5 6.5 0 0 1 13 0Z" /></svg>
      <span class="hidden sm:inline">Search</span>
      <kbd class="hidden rounded border border-line px-1 text-[10px] sm:inline">Ctrl K</kbd>
    </button>

    <div v-if="open" class="fixed inset-0 z-50 flex items-start justify-center bg-overlay p-4 pt-[12vh]" role="dialog" aria-modal="true" aria-label="Search" v-dialog="{ close: hide }" @click.self="hide">
      <div class="w-full max-w-lg rounded-2xl bg-surface p-4 shadow-xl">
        <input ref="inputEl" v-model="q" type="search" class="input-field" placeholder="Search tasks by number, title or description" aria-label="Search tasks" data-test="search-input" @input="onInput" @keydown.enter.prevent="go(results[0])">
        <ul class="mt-3 space-y-1" aria-label="Results">
          <li v-for="r in results" :key="r.id">
            <button type="button" class="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm hover:bg-hover" @click="go(r)">
              <span class="min-w-0 truncate text-ink">{{ r.title }}</span>
              <span class="shrink-0 font-mono text-xs text-muted">{{ r.task_number }}</span>
            </button>
          </li>
          <li v-if="searched && !results.length" class="px-3 py-2 text-sm text-muted">No authorized tasks match “{{ q }}”.</li>
          <li v-else-if="!searched" class="px-3 py-2 text-xs text-faint">Only tasks you are allowed to see are searched.</li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Hit { id: string, task_number: string, title: string, status: string }

const api = useApi()
const open = ref(false)
const q = ref('')
const results = ref<Hit[]>([])
const searched = ref(false)
const inputEl = ref<HTMLInputElement | null>(null)
let timer: ReturnType<typeof setTimeout> | undefined

function show(): void {
  open.value = true
  nextTick(() => inputEl.value?.focus())
}
function hide(): void {
  open.value = false
  q.value = ''
  results.value = []
  searched.value = false
}
function onInput(): void {
  clearTimeout(timer)
  if (q.value.trim().length < 2) { results.value = []; searched.value = false; return }
  timer = setTimeout(async () => {
    try {
      results.value = (await api.get<{ tasks: Hit[] }>(`/api/v1/search?q=${encodeURIComponent(q.value.trim())}`)).tasks
    } catch { results.value = [] }
    searched.value = true
  }, 200)
}
function go(hit?: Hit): void {
  if (!hit) return
  hide()
  navigateTo(`/tasks/${hit.id}`)
}
function onKey(e: KeyboardEvent): void {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    open.value ? hide() : show()
  }
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>
