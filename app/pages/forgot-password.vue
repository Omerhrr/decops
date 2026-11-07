<template>
  <div class="w-full max-w-md rounded-2xl border border-line bg-surface p-8 shadow-xl">
    <div class="mb-6 flex items-center justify-between">
      <BrandLogo mark-only :size="40" />
      <ThemeToggle />
    </div>
    <h1 class="text-2xl font-semibold tracking-tight text-ink">Reset your password</h1>

    <div v-if="sent" class="mt-6 space-y-4" role="status">
      <p class="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2.5 text-sm text-emerald-800 dark:border-emerald-900/50 dark:bg-emerald-500/10 dark:text-emerald-300">
        If that email belongs to an account, a reset link is on its way. It expires in 30 minutes.
      </p>
      <NuxtLink to="/login" class="btn-secondary w-full">Back to sign in</NuxtLink>
    </div>

    <form v-else class="mt-2" method="post" action="/forgot-password" novalidate @submit.prevent="submit">
      <p class="text-sm text-muted">Enter your work email and we will send you a link to choose a new password.</p>
      <label for="email" class="mt-6 block text-sm font-medium text-body">Work email</label>
      <input
        id="email" v-model="email" type="email" autocomplete="email" autofocus required
        class="input-field mt-1.5" placeholder="you@interdec.com"
        :aria-invalid="!!errorMessage" :aria-describedby="errorMessage ? 'fp-error' : undefined"
      >
      <p v-if="errorMessage" id="fp-error" role="alert" class="alert-error mt-4">{{ errorMessage }}</p>
      <button type="submit" :disabled="submitting" :aria-busy="submitting" class="btn-primary mt-6 w-full py-2.5">
        {{ submitting ? 'Sending' : 'Send reset link' }}
      </button>
      <NuxtLink to="/login" class="mt-4 block text-center text-sm text-muted hover:text-ink">Back to sign in</NuxtLink>
    </form>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'auth' })
useHead({ title: 'Reset password - DecOps' })
import { ApiError } from '~/composables/useApi'

const api = useApi()
const email = ref('')
const sent = ref(false)
const submitting = ref(false)
const errorMessage = ref('')

async function submit() {
  errorMessage.value = ''
  if (!email.value.trim()) {
    errorMessage.value = 'Enter your work email.'
    return
  }
  submitting.value = true
  try {
    await api.post('/api/v1/auth/forgot-password', { email: email.value.trim() })
    sent.value = true
  } catch (err) {
    errorMessage.value = err instanceof ApiError ? err.message : 'Unable to reach the server. Please try again.'
  } finally {
    submitting.value = false
  }
}
</script>
