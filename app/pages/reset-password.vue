<template>
  <div class="w-full max-w-md rounded-2xl border border-line bg-surface p-8 shadow-xl">
    <div class="mb-6 flex items-center justify-between">
      <BrandLogo mark-only :size="40" />
      <ThemeToggle />
    </div>
    <h1 class="text-2xl font-semibold tracking-tight text-ink">Choose a new password</h1>

    <div v-if="done" class="mt-6 space-y-4" role="status">
      <p class="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2.5 text-sm text-emerald-800 dark:border-emerald-900/50 dark:bg-emerald-500/10 dark:text-emerald-300">
        Your password has been changed. You have been signed out everywhere.
      </p>
      <NuxtLink to="/login" class="btn-primary w-full">Sign in</NuxtLink>
    </div>

    <p v-else-if="!token" class="alert-error mt-6" role="alert">
      This reset link is incomplete. Request a new one from the sign-in page.
    </p>

    <form v-else class="mt-4 space-y-5" method="post" action="/reset-password" novalidate @submit.prevent="submit">
      <div>
        <label for="pw" class="block text-sm font-medium text-body">New password</label>
        <input id="pw" v-model="password" type="password" autocomplete="new-password" autofocus required class="input-field mt-1.5"
               aria-describedby="pw-help">
        <p id="pw-help" class="mt-1.5 text-xs text-muted">At least 10 characters, with letters and numbers or symbols.</p>
      </div>
      <div>
        <label for="pw2" class="block text-sm font-medium text-body">Confirm new password</label>
        <input id="pw2" v-model="confirm" type="password" autocomplete="new-password" required class="input-field mt-1.5">
      </div>
      <p v-if="errorMessage" role="alert" class="alert-error">{{ errorMessage }}</p>
      <button type="submit" :disabled="submitting" :aria-busy="submitting" class="btn-primary w-full py-2.5">
        {{ submitting ? 'Saving' : 'Change password' }}
      </button>
    </form>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'auth' })
useHead({ title: 'New password - DecOps' })
import { ApiError } from '~/composables/useApi'

const api = useApi()
const route = useRoute()
const token = computed(() => String(route.query.token ?? ''))
const password = ref('')
const confirm = ref('')
const done = ref(false)
const submitting = ref(false)
const errorMessage = ref('')

async function submit() {
  errorMessage.value = ''
  if (password.value !== confirm.value) {
    errorMessage.value = 'The two passwords do not match.'
    return
  }
  submitting.value = true
  try {
    await api.post('/api/v1/auth/reset-password', { token: token.value, new_password: password.value })
    done.value = true
  } catch (err) {
    errorMessage.value = err instanceof ApiError ? err.message : 'Unable to reach the server. Please try again.'
  } finally {
    submitting.value = false
  }
}
</script>
