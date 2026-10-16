<template>
  <section class="rounded-2xl border border-line bg-surface p-5" data-test="task-attachments">
    <div class="flex items-center justify-between">
      <h2 class="text-sm font-semibold text-ink">Attachments</h2>
      <span v-if="attachments.length" class="text-xs text-faint">{{ attachments.length }}</span>
    </div>
    <p class="mt-1 text-xs text-faint">Private to this task. Downloads are authorization-checked; files up to 25 MB (pdf, images, office, txt/csv, zip).</p>

    <label
      class="mt-4 flex cursor-pointer items-center justify-center gap-2 rounded-xl border-2 border-dashed border-line px-4 py-4 text-sm text-muted transition-colors hover:border-brand-300 hover:text-brand-600 dark:hover:text-brand-400"
      :class="{ 'pointer-events-none opacity-60': uploading }"
    >
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.6" stroke="currentColor" class="h-5 w-5" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
      </svg>
      {{ uploading ? 'Uploading…' : 'Click to attach a file' }}
      <input type="file" class="hidden" :disabled="uploading" data-test="attachment-input" @change="onFileChange">
    </label>
    <p v-if="error" class="mt-2 text-xs text-rose-600 dark:text-rose-400" data-test="attachment-error">{{ error }}</p>

    <ul v-if="attachments.length" class="mt-4 divide-y divide-line">
      <li v-for="attachment in attachments" :key="attachment.id" class="flex items-center gap-3 py-3">
        <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-hover text-[10px] font-bold uppercase text-muted">
          {{ extension(attachment.original_filename) }}
        </span>
        <div class="min-w-0 flex-1">
          <p class="truncate text-sm font-medium text-ink">{{ attachment.original_filename }}</p>
          <p class="text-[11px] text-faint">
            {{ formatSize(attachment.size_bytes) }} · {{ attachment.uploaded_by?.full_name ?? 'Unknown' }} · {{ new Date(attachment.created_at).toLocaleDateString() }}
          </p>
        </div>
        <a
          :href="`/api/v1/tasks/${taskId}/attachments/${attachment.id}/download`"
          class="shrink-0 rounded-lg border border-line px-2.5 py-1.5 text-xs font-medium text-body transition-colors hover:bg-hover"
          :data-test="`attachment-download-${attachment.id}`"
        >
          Download
        </a>
        <button
          v-if="auth.user.value && attachment.uploaded_by?.id === auth.user.value.id"
          type="button"
          class="shrink-0 rounded-lg border border-transparent px-2 py-1.5 text-xs text-faint transition-colors hover:text-rose-600 dark:hover:text-rose-400"
          :data-test="`attachment-delete-${attachment.id}`"
          @click="remove(attachment)"
        >
          Delete
        </button>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import type { Attachment } from '~/types/api'

const props = defineProps<{ taskId: string }>()

const auth = useAuth()
const api = useApi()
const attachments = ref<Attachment[]>([])
const uploading = ref(false)
const error = ref('')

async function load(): Promise<void> {
  try {
    attachments.value = await api.get<Attachment[]>(`/api/v1/tasks/${props.taskId}/attachments`)
  } catch {
    // Panel is informational; errors surface on interaction.
  }
}

async function onFileChange(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  await upload(file)
  input.value = '' // allow re-selecting the same file
}

async function upload(file: File): Promise<void> {
  uploading.value = true
  error.value = ''
  const form = new FormData()
  form.append('file', file)
  try {
    const ssfCookieHeader = import.meta.server ? useRequestHeaders(['cookie']) : {}
    const response = await $fetch.raw(`/api/v1/tasks/${props.taskId}/attachments`, {
      method: 'POST',
      body: form,
      headers: { ...ssfCookieHeader },
      credentials: 'include',
      ignoreResponseError: true,
    })
    if (response.status >= 400) {
      const body = (response._data ?? {}) as { error?: { message?: string } }
      error.value = body.error?.message ?? 'Upload failed.'
      return
    }
    attachments.value.unshift(response._data as Attachment)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Upload failed.'
  } finally {
    uploading.value = false
  }
}

async function remove(attachment: Attachment): Promise<void> {
  error.value = ''
  try {
    await api.delete(`/api/v1/tasks/${props.taskId}/attachments/${attachment.id}`)
    attachments.value = attachments.value.filter(a => a.id !== attachment.id)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not delete the attachment.'
  }
}

function extension(filename: string): string {
  const dot = filename.lastIndexOf('.')
  return dot === -1 ? '?' : filename.slice(dot + 1)
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

onMounted(load)

watch(() => props.taskId, load)
</script>
