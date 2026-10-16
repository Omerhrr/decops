<template>
  <div class="w-full max-w-5xl overflow-hidden rounded-2xl border border-line bg-surface shadow-xl lg:grid lg:grid-cols-2">
    <div class="relative hidden flex-col justify-between overflow-hidden bg-brand-800 p-10 text-white lg:flex">
      <div class="pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full bg-brand-600/40 blur-3xl" aria-hidden="true" />
      <div class="pointer-events-none absolute -bottom-32 -left-16 h-80 w-80 rounded-full bg-brand-500/20 blur-3xl" aria-hidden="true" />
      <NuxtLink to="/" class="relative flex items-center gap-3">
        <BrandLogo mark-only :size="40" />
        <span class="flex flex-col leading-tight">
          <span class="text-base font-semibold">DecOps</span>
          <span class="text-xs text-brand-200">Interdec Operations</span>
        </span>
      </NuxtLink>

      <div class="relative">
        <h2 class="text-2xl font-semibold leading-snug">
          One register for every operational task,
          <span class="text-brand-300">with access you can prove.</span>
        </h2>
        <ul class="mt-8 space-y-4 text-sm text-brand-100/85">
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

      <p class="relative text-xs text-brand-200/80">Every sign-in and permission change is audited.</p>
    </div>

    <div class="relative flex flex-col justify-center px-6 py-10 sm:px-10 lg:px-12">
      <div class="absolute right-4 top-4">
        <ThemeToggle />
      </div>
      <div class="mb-8 lg:hidden">
        <BrandLogo mark-only :size="44" />
      </div>
      <h1 class="text-2xl font-semibold tracking-tight text-ink">Sign in to DecOps</h1>
      <p class="mt-2 text-sm text-muted">Use your Interdec work account.</p>

      <form class="mt-8" novalidate @submit.prevent="submit">
        <div class="space-y-5">
          <div>
            <label for="email" class="block text-sm font-medium text-body">Work email</label>
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
              <label for="password" class="block text-sm font-medium text-body">Password</label>
              <button
                type="button"
                class="text-xs font-medium text-muted hover:text-ink"
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
            class="flex items-start gap-2 rounded-lg border border-rose-200 dark:border-rose-900/50 bg-rose-50 dark:bg-rose-500/10 px-3 py-2.5 text-sm text-rose-700 dark:text-rose-300"
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

      <p class="mt-8 text-center text-xs text-faint">
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
