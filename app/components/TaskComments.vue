<template>
  <section class="rounded-2xl border border-line bg-surface p-5" data-test="task-comments">
    <div class="flex items-center justify-between">
      <h2 class="text-sm font-semibold text-ink">Comments</h2>
      <span v-if="comments.length" class="text-xs text-faint">{{ comments.length }}</span>
    </div>
    <p class="mt-1 text-xs text-faint">Visible to everyone who can see this task. Access is re-checked on every request.</p>

    <form class="mt-4" @submit.prevent="submit">
      <div class="relative">
        <textarea
          ref="inputEl"
          v-model="draft"
          rows="3"
          placeholder="Write a comment… type @ to mention someone"
          class="input-field"
          :disabled="submitting"
          data-test="comment-input"
          @input="onInput"
          @keydown.esc="people = []"
        />
        <ul v-if="people.length" class="absolute left-0 right-0 top-full z-20 mt-1 max-h-48 overflow-y-auto rounded-xl border border-line bg-surface py-1 shadow-lg" role="listbox" aria-label="People you can mention">
          <li v-for="p in people" :key="p.id" role="option">
            <button type="button" class="block w-full px-3 py-1.5 text-left text-sm text-body hover:bg-hover" @mousedown.prevent="pick(p)">{{ p.full_name }}</button>
          </li>
        </ul>
      </div>
      <div class="mt-2 flex items-center justify-between gap-2">
        <p v-if="error" class="text-xs text-rose-600 dark:text-rose-400">{{ error }}</p>
        <span v-else />
        <button
          type="submit"
          class="btn-primary !px-4 text-xs"
          :disabled="submitting || !draft.trim()"
          data-test="comment-submit"
        >
          {{ submitting ? 'Posting…' : 'Comment' }}
        </button>
      </div>
    </form>

    <ul v-if="comments.length" class="mt-5 space-y-4">
      <li v-for="comment in comments" :key="comment.id" class="flex gap-3">
        <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-hover text-xs font-semibold text-body">
          {{ initials(comment.author.full_name) }}
        </span>
        <div class="min-w-0 flex-1 rounded-xl bg-elevated px-3 py-2.5">
          <div class="flex items-baseline justify-between gap-2">
            <p class="truncate text-xs font-semibold text-ink">{{ comment.author.full_name }}</p>
            <div class="flex shrink-0 items-center gap-2">
              <span class="text-[11px] text-faint">{{ relativeTime(comment.created_at) }}</span>
              <button
                v-if="auth.user.value && comment.author.id === auth.user.value.id"
                type="button"
                class="text-[11px] text-faint transition-colors hover:text-rose-600 dark:hover:text-rose-400"
                :data-test="`comment-delete-${comment.id}`"
                @click="remove(comment)"
              >
                Delete
              </button>
            </div>
          </div>
          <p class="mt-1 whitespace-pre-line text-sm text-body"><template v-for="(seg, i) in segments(comment.body)" :key="i"><strong v-if="seg.mention" class="font-semibold text-brand-700 dark:text-brand-300">@{{ seg.text }}</strong><template v-else>{{ seg.text }}</template></template></p>
        </div>
      </li>
    </ul>
    <p v-else class="mt-5 text-sm text-faint">No comments yet - start the discussion.</p>
  </section>
</template>

<script setup lang="ts">
import type { Comment } from '~/types/api'

const props = defineProps<{ taskId: string }>()

const auth = useAuth()
const api = useApi()
const comments = ref<Comment[]>([])
const draft = ref('')
const submitting = ref(false)
const error = ref('')

async function load(): Promise<void> {
  try {
    comments.value = await api.get<Comment[]>(`/api/v1/tasks/${props.taskId}/comments`)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load comments.'
  }
}

async function submit(): Promise<void> {
  if (!draft.value.trim()) return
  submitting.value = true
  error.value = ''
  try {
    const created = await api.post<Comment>(`/api/v1/tasks/${props.taskId}/comments`, {
      body: draft.value.trim(),
    })
    comments.value.push(created)
    draft.value = ''
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not post the comment.'
  } finally {
    submitting.value = false
  }
}

async function remove(comment: Comment): Promise<void> {
  error.value = ''
  try {
    await api.delete(`/api/v1/tasks/${props.taskId}/comments/${comment.id}`)
    comments.value = comments.value.filter(c => c.id !== comment.id)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not delete the comment.'
  }
}

// ---- @mentions: stored as @[Name](user:<id>); rendered as text (never HTML) ----
const inputEl = ref<HTMLTextAreaElement | null>(null)
const people = ref<{ id: string, full_name: string }[]>([])
let mentionTimer: ReturnType<typeof setTimeout> | undefined

function onInput(): void {
  const match = /(?:^|\s)@([^\s@\[\]]{0,30})$/.exec(draft.value)
  clearTimeout(mentionTimer)
  if (!match) { people.value = []; return }
  const q = match[1] ?? ''
  mentionTimer = setTimeout(async () => {
    try {
      people.value = await api.get<{ id: string, full_name: string }[]>(
        `/api/v1/tasks/${props.taskId}/mentionable?q=${encodeURIComponent(q)}`)
    } catch { people.value = [] }
  }, 150)
}

function pick(p: { id: string, full_name: string }): void {
  draft.value = draft.value.replace(/@([^\s@\[\]]{0,30})$/, `@[${p.full_name}](user:${p.id}) `)
  people.value = []
  inputEl.value?.focus()
}

function segments(body: string): { text: string, mention: boolean }[] {
  const out: { text: string, mention: boolean }[] = []
  const re = /@\[([^\]\n]{1,120})\]\(user:[0-9a-fA-F-]{36}\)/g
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(body)) !== null) {
    if (m.index > last) out.push({ text: body.slice(last, m.index), mention: false })
    out.push({ text: m[1] ?? '', mention: true })
    last = m.index + m[0].length
  }
  if (last < body.length) out.push({ text: body.slice(last), mention: false })
  return out
}

function initials(name: string): string {
  return name.split(/\s+/).map(p => p[0]).filter(Boolean).slice(0, 2).join('').toUpperCase()
}

function relativeTime(iso: string): string {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return new Date(iso).toLocaleDateString()
}

onMounted(load)

watch(() => props.taskId, load)
</script>
