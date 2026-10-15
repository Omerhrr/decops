<template>
  <div class="w-full max-w-5xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl lg:grid lg:grid-cols-2">
    <div class="hidden flex-col justify-between bg-slate-900 p-10 text-white lg:flex">
      <NuxtLink to="/" class="flex items-center gap-3">
        <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-500 text-lg font-bold">D</span>
        <span class="flex flex-col leading-tight">
          <span class="text-base font-semibold">DecOps</span>
          <span class="text-xs text-slate-400">Interdec Operations</span>
        </span>
      </NuxtLink>

      <div>
        <h2 class="text-2xl font-semibold leading-snug">
          One register for every operational task,
          <span class="text-brand-400">with access you can prove.</span>
        </h2>
        <ul class="mt-8 space-y-4 text-sm text-slate-300">
          <li class="flex items-start gap-3">
            <svg class="mt-0.5 h-5 w-5 shrink-0 text-brand-400" fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Full lifecycle tracking with audited transitions and required reasons
          </li>
          <li class="flex items-start gap-3">
            <svg class="mt-0.5 h-5 w-5 shrink-0 text-brand-400" fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Department workspaces, reporting and authorized CSV exports
          </li>
          <li class="flex items-start gap-3">
            <svg class="mt-0.5 h-5 w-5 shrink-0 text-brand-400" fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Spreadsheet migration with validation, duplicate checks and safe retries
          </li>
        </ul>
      </div>

      <p class="text-xs text-slate-500">Every sign-in and permission change is audited.</p>
    </div>

    <div class="flex flex-col justify-center px-6 py-10 sm:px-10 lg:px-12">
      <div class="mb-8 lg:hidden">
        <span class="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-brand-600 text-xl font-bold text-white">D</span>
      </div>
      <h1 class="text-2xl font-semibold tracking-tight text-slate-900">Sign in to DecOps</h1>
      <p class="mt-2 text-sm text-slate-500">Use your Interdec work account.</p>

      <form class="mt-8" novalidate @submit.prevent="submit">
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
              class="input-field mt-1.5"
              placeholder="you@interdec.com"
            >
          </div>

          <div>
            <div class="flex items-center justify-between">
              <label for="password" class="block text-sm font-medium text-slate-700">Password</label>
              <button
                type="button"
                class="text-xs font-medium text-slate-500 hover:text-slate-700"
                :aria-pressed="showPassword"
                @click="showPassword = !showPassword"
              >
                {{ showPassword ? 'Hide' : 'Show' }}
              </button>
            </div>
            <input
              id="password"
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              name="password"
              autocomplete="current-password"
              required
              class="input-field mt-1.5"
              placeholder="Enter your password"
            >
          </div>

          <p
            v-if="errorMessage"
            role="alert"
            class="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2.5 text-sm text-rose-700"
          >
            <svg class="mt-0.5 h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
            </svg>
            {{ errorMessage }}
          </p>

          <button type="submit" :disabled="submitting || !email || !password" class="btn-primary w-full py-2.5">
            <svg v-if="submitting" class="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            {{ submitting ? 'Signing in' : 'Sign in' }}
          </button>
        </div>
      </form>

      <p class="mt-8 text-center text-xs text-slate-400">
        Access is restricted to authorized Interdec personnel.<br>
        All sign-in activity is audited.
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'auth' })
import { ApiError } from '~/composables/useApi'

const auth = useAuth()
const email = ref('')
const password = ref('')
const showPassword = ref(false)
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
      errorMessage.value = err.message
    } else {
      errorMessage.value = 'Unable to reach the server. Please try again.'
    }
  } finally {
    submitting.value = false
  }
}
</script>
