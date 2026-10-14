<template>
  <div class="w-full max-w-md">
      <div class="mb-8 text-center">
        <span class="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-600 text-2xl font-bold text-white">D</span>
        <h1 class="text-2xl font-semibold text-slate-900">Sign in to DecOps</h1>
        <p class="mt-2 text-sm text-slate-500">Interdec Operations Management System</p>
      </div>

      <form
        class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8"
        novalidate
        @submit.prevent="submit"
      >
        <div class="space-y-5">
          <div>
            <label for="email" class="block text-sm font-medium text-slate-700">Work email</label>
            <input
              id="email"
              v-model="email"
              type="email"
              name="email"
              autocomplete="email"
              required
              class="mt-1.5 block w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm text-slate-900 placeholder-slate-400 transition-colors focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
              placeholder="you@interdec.com"
            >
          </div>

          <div>
            <label for="password" class="block text-sm font-medium text-slate-700">Password</label>
            <input
              id="password"
              v-model="password"
              type="password"
              name="password"
              autocomplete="current-password"
              required
              class="mt-1.5 block w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm text-slate-900 placeholder-slate-400 transition-colors focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
              placeholder="••••••••"
            >
          </div>

          <p
            v-if="errorMessage"
            role="alert"
            class="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2.5 text-sm text-rose-700"
          >
            {{ errorMessage }}
          </p>

          <button
            type="submit"
            :disabled="submitting || !email || !password"
            class="w-full rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <span v-if="submitting">Signing in…</span>
            <span v-else>Sign in</span>
          </button>
        </div>
      </form>

      <p class="mt-6 text-center text-xs text-slate-400">
        Access is restricted to authorized Interdec personnel.<br>
        All sign-in activity is audited.
      </p>
    </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'auth' })
import { ApiError } from '~/composables/useApi'

const auth = useAuth()
const email = ref('')
const password = ref('')
const submitting = ref(false)
const errorMessage = ref('')

async function submit() {
  errorMessage.value = ''
  submitting.value = true
  try {
    await auth.login(email.value.trim(), password.value)
    await navigateTo('/', { replace: true })
  } catch (err) {
    if (err instanceof ApiError) {
      // Account locked messages arrive as 401 with a reason detail
      errorMessage.value = err.message
    } else {
      errorMessage.value = 'Unable to reach the server. Please try again.'
    }
  } finally {
    submitting.value = false
  }
}
</script>
