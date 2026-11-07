<template>
  <div class="mx-auto max-w-3xl px-4 py-8 sm:px-6">
    <h1 class="page-title">Account security</h1>
    <p class="page-subtitle">Manage your password, two-factor sign-in and signed-in devices.</p>

    <p v-if="forced" role="alert" class="alert-error mt-5">
      Your administrator requires you to choose a new password before you can continue.
    </p>

    <!-- Password -->
    <section class="card mt-6 p-6" aria-labelledby="pw-title">
      <h2 id="pw-title" class="text-base font-semibold text-ink">Password</h2>
      <p class="mt-1 text-sm text-muted">Changing it signs you out of all your other devices.</p>
      <form class="mt-4 grid gap-4 sm:max-w-md" novalidate @submit.prevent="changePassword">
        <div>
          <label for="cur" class="block text-sm font-medium text-body">Current password</label>
          <input id="cur" v-model="pw.current" type="password" autocomplete="current-password" class="input-field mt-1.5">
        </div>
        <div>
          <label for="new" class="block text-sm font-medium text-body">New password</label>
          <input id="new" v-model="pw.next" type="password" autocomplete="new-password" class="input-field mt-1.5" aria-describedby="new-help">
          <p id="new-help" class="mt-1.5 text-xs text-muted">At least 10 characters, with letters and numbers or symbols.</p>
        </div>
        <div>
          <label for="conf" class="block text-sm font-medium text-body">Confirm new password</label>
          <input id="conf" v-model="pw.confirm" type="password" autocomplete="new-password" class="input-field mt-1.5">
        </div>
        <p v-if="pw.error" role="alert" class="alert-error">{{ pw.error }}</p>
        <p v-if="pw.ok" role="status" class="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:border-emerald-900/50 dark:bg-emerald-500/10 dark:text-emerald-300">Password updated.</p>
        <div><button type="submit" class="btn-primary" :disabled="pw.busy">{{ pw.busy ? 'Saving' : 'Update password' }}</button></div>
      </form>
    </section>

    <!-- Two-factor -->
    <section class="card mt-6 p-6" aria-labelledby="mfa-title">
      <div class="flex items-start justify-between gap-3">
        <div>
          <h2 id="mfa-title" class="text-base font-semibold text-ink">Two-factor authentication</h2>
          <p class="mt-1 text-sm text-muted">Require a 6-digit code from an authenticator app (Google Authenticator, Microsoft Authenticator, 1Password) at sign-in.</p>
        </div>
        <AppBadge :tone="mfaEnabled ? 'green' : 'gray'">{{ mfaEnabled ? 'On' : 'Off' }}</AppBadge>
      </div>

      <!-- recovery codes (shown once) -->
      <div v-if="mfa.recovery.length" class="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 dark:border-amber-900/50 dark:bg-amber-500/10" role="status">
        <p class="text-sm font-medium text-amber-900 dark:text-amber-200">Save your recovery codes now. They are shown only once.</p>
        <p class="mt-1 text-xs text-amber-800 dark:text-amber-300">Each code works one time if you lose your phone.</p>
        <ul class="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 font-mono text-sm text-ink">
          <li v-for="c in mfa.recovery" :key="c">{{ c }}</li>
        </ul>
        <div class="mt-4 flex gap-2">
          <button type="button" class="btn-secondary" @click="copyCodes">{{ mfa.copied ? 'Copied' : 'Copy' }}</button>
          <button type="button" class="btn-secondary" @click="downloadCodes">Download</button>
          <button type="button" class="btn-primary ml-auto" @click="mfa.recovery = []">I have saved them</button>
        </div>
      </div>

      <template v-else-if="!mfaEnabled">
        <div v-if="!mfa.setup" class="mt-4">
          <button type="button" class="btn-primary" :disabled="mfa.busy" @click="startSetup">Set up two-factor</button>
        </div>
        <form v-else class="mt-4 grid gap-4 sm:grid-cols-[auto_1fr] sm:items-start" novalidate @submit.prevent="enableMfa">
          <img :src="mfa.setup.qr_svg_data_uri" alt="QR code to add DecOps to your authenticator app" width="176" height="176"
               class="rounded-lg border border-line bg-white p-2">
          <div class="space-y-3">
            <p class="text-sm text-body">1. Scan the code with your authenticator app, or enter this key manually:</p>
            <code class="block break-all rounded-lg bg-hover px-3 py-2 text-xs text-ink">{{ mfa.setup.secret }}</code>
            <label for="mfa-code" class="block text-sm font-medium text-body">2. Enter the 6-digit code it shows</label>
            <input id="mfa-code" v-model="mfa.code" inputmode="numeric" autocomplete="one-time-code" class="input-field max-w-[12rem] tracking-widest" placeholder="123456">
            <p v-if="mfa.error" role="alert" class="alert-error">{{ mfa.error }}</p>
            <div class="flex gap-2">
              <button type="submit" class="btn-primary" :disabled="mfa.busy">Turn on</button>
              <button type="button" class="btn-ghost" @click="mfa.setup = null">Cancel</button>
            </div>
          </div>
        </form>
      </template>

      <form v-else class="mt-4 grid gap-4 sm:max-w-md" novalidate @submit.prevent="disableMfa">
        <p class="text-sm text-muted">To turn it off, confirm your password and a current code.</p>
        <div>
          <label for="d-pw" class="block text-sm font-medium text-body">Password</label>
          <input id="d-pw" v-model="mfa.password" type="password" autocomplete="current-password" class="input-field mt-1.5">
        </div>
        <div>
          <label for="d-code" class="block text-sm font-medium text-body">Authenticator or recovery code</label>
          <input id="d-code" v-model="mfa.code" autocomplete="one-time-code" class="input-field mt-1.5">
        </div>
        <p v-if="mfa.error" role="alert" class="alert-error">{{ mfa.error }}</p>
        <div><button type="submit" class="btn-danger" :disabled="mfa.busy">Turn off two-factor</button></div>
      </form>
      <p v-if="mfa.error && !mfa.recovery.length && !mfa.setup && !mfaEnabled" role="alert" class="alert-error mt-4">{{ mfa.error }}</p>
    </section>

    <!-- Sessions -->
    <section class="card mt-6 p-6" aria-labelledby="sess-title">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="sess-title" class="text-base font-semibold text-ink">Signed-in devices</h2>
          <p class="mt-1 text-sm text-muted">If you do not recognise a device, sign it out and change your password.</p>
        </div>
        <button type="button" class="btn-secondary" :disabled="otherSessions === 0" @click="revokeOthers">Sign out everywhere else</button>
      </div>
      <p v-if="sessions.error" role="alert" class="alert-error mt-4">{{ sessions.error }}</p>
      <ul class="mt-4 divide-y divide-line" aria-label="Active sessions">
        <li v-for="s in sessions.items" :key="s.id" class="flex flex-wrap items-center justify-between gap-3 py-3">
          <div class="min-w-0">
            <p class="truncate text-sm font-medium text-ink">
              {{ describeAgent(s.user_agent) }}
              <AppBadge v-if="s.current" tone="green" class="ml-2">This device</AppBadge>
            </p>
            <p class="text-xs text-muted">{{ s.ip_address || 'Unknown location' }} · signed in {{ formatDateTime(s.created_at) }}</p>
          </div>
          <button v-if="!s.current" type="button" class="btn-ghost text-rose-600 dark:text-rose-400" @click="revoke(s.id)">Sign out</button>
        </li>
        <li v-if="!sessions.items.length && !sessions.loading" class="py-3 text-sm text-muted">No active sessions.</li>
      </ul>
    </section>

    <NotificationPreferences />
    <IntegrationsPanel />
  </div>
</template>

<script setup lang="ts">
import { ApiError } from '~/composables/useApi'

useHead({ title: 'Account security - DecOps' })

const api = useApi()
const auth = useAuth()
const confirm = useConfirm()
const route = useRoute()

const forced = computed(() => !!auth.user.value?.must_change_password)
const mfaEnabled = computed(() => !!auth.user.value?.mfa_enabled)
const msg = (e: unknown) => (e instanceof ApiError ? e.message : 'Something went wrong. Please try again.')

// ---- password
const pw = reactive({ current: '', next: '', confirm: '', busy: false, error: '', ok: false })
async function changePassword() {
  pw.error = ''; pw.ok = false
  if (!pw.current || !pw.next) { pw.error = 'Fill in all fields.'; return }
  if (pw.next !== pw.confirm) { pw.error = 'The new passwords do not match.'; return }
  pw.busy = true
  try {
    await api.post('/api/v1/auth/change-password', { current_password: pw.current, new_password: pw.next })
    pw.current = pw.next = pw.confirm = ''
    pw.ok = true
    const wasForced = forced.value
    await auth.fetchMe()
    if (wasForced) await navigateTo('/', { replace: true })
    else await loadSessions()
  } catch (e) { pw.error = msg(e) } finally { pw.busy = false }
}

// ---- two-factor
const mfa = reactive({
  setup: null as null | { secret: string, otpauth_uri: string, qr_svg_data_uri: string },
  code: '', password: '', busy: false, error: '', recovery: [] as string[], copied: false,
})
async function startSetup() {
  mfa.error = ''; mfa.busy = true
  try { mfa.setup = await api.post('/api/v1/auth/mfa/setup') } catch (e) { mfa.error = msg(e) } finally { mfa.busy = false }
}
async function enableMfa() {
  mfa.error = ''; mfa.busy = true
  try {
    const r = await api.post<{ recovery_codes: string[] }>('/api/v1/auth/mfa/enable', { code: mfa.code })
    mfa.recovery = r.recovery_codes; mfa.setup = null; mfa.code = ''
    await auth.fetchMe()
  } catch (e) { mfa.error = msg(e) } finally { mfa.busy = false }
}
async function disableMfa() {
  const ok = await confirm.confirm({
    title: 'Turn off two-factor?', message: 'Your account will be protected by your password alone.',
    confirmLabel: 'Turn off', tone: 'danger',
  })
  if (!ok) return
  mfa.error = ''; mfa.busy = true
  try {
    await api.post('/api/v1/auth/mfa/disable', { password: mfa.password, code: mfa.code })
    mfa.password = mfa.code = ''
    await auth.fetchMe()
  } catch (e) { mfa.error = msg(e) } finally { mfa.busy = false }
}
async function copyCodes() {
  try { await navigator.clipboard.writeText(mfa.recovery.join('\n')); mfa.copied = true } catch { /* clipboard blocked */ }
}
function downloadCodes() {
  const blob = new Blob([`DecOps recovery codes for ${auth.user.value?.email}\n\n${mfa.recovery.join('\n')}\n`], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = 'decops-recovery-codes.txt'; a.click()
  URL.revokeObjectURL(url)
}

// ---- sessions
interface SessionRow { id: string, created_at: string, expires_at: string, ip_address: string | null, user_agent: string | null, current: boolean }
const sessions = reactive({ items: [] as SessionRow[], loading: true, error: '' })
const otherSessions = computed(() => sessions.items.filter(s => !s.current).length)
async function loadSessions() {
  sessions.loading = true
  try { sessions.items = await api.get<SessionRow[]>('/api/v1/auth/sessions'); sessions.error = '' }
  catch (e) { sessions.error = msg(e) } finally { sessions.loading = false }
}
async function revoke(id: string) {
  try { await api.delete(`/api/v1/auth/sessions/${id}`); await loadSessions() } catch (e) { sessions.error = msg(e) }
}
async function revokeOthers() {
  const ok = await confirm.confirm({
    title: 'Sign out everywhere else?', message: 'Every other device will need to sign in again.',
    confirmLabel: 'Sign out others', tone: 'danger',
  })
  if (!ok) return
  try { await api.post('/api/v1/auth/sessions/revoke-others'); await loadSessions() } catch (e) { sessions.error = msg(e) }
}
function describeAgent(ua: string | null): string {
  if (!ua) return 'Unknown device'
  const browser = /Edg\//.test(ua) ? 'Edge' : /Chrome\//.test(ua) ? 'Chrome' : /Firefox\//.test(ua) ? 'Firefox' : /Safari\//.test(ua) ? 'Safari' : 'Browser'
  const os = /Windows/.test(ua) ? 'Windows' : /Android/.test(ua) ? 'Android' : /iPhone|iPad/.test(ua) ? 'iOS' : /Mac OS X/.test(ua) ? 'macOS' : /Linux/.test(ua) ? 'Linux' : 'Unknown OS'
  return `${browser} on ${os}`
}

onMounted(() => { void loadSessions(); if (route.query.forced) void auth.fetchMe() })
</script>
