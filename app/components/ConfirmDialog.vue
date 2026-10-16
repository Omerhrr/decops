<template>
  <div
    v-if="request"
    class="fixed inset-0 z-[60] flex items-center justify-center bg-overlay p-4"
    role="alertdialog"
    aria-modal="true"
    aria-label="Confirm action"
    v-dialog="{ close: cancel }"
    @click.self="cancel"
  >
    <div class="w-full max-w-sm rounded-2xl bg-surface p-6 shadow-xl">
      <h2 class="text-base font-semibold text-ink">{{ request.title }}</h2>
      <p class="mt-2 text-sm text-muted">{{ request.message }}</p>
      <div class="mt-5 flex justify-end gap-2">
        <button type="button" class="btn-secondary" @click="cancel">
          {{ request.cancelLabel ?? 'Cancel' }}
        </button>
        <button
          type="button"
          :class="request.tone === 'danger' ? 'btn-danger' : 'btn-primary'"
          @click="accept"
        >
          {{ request.confirmLabel ?? 'Confirm' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const { request, settle } = useConfirm()

function cancel(): void {
  settle(false)
}

function accept(): void {
  settle(true)
}
</script>
