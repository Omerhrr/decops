<template>
  <section class="card mt-6 p-6" aria-labelledby="int-title">
    <h2 id="int-title" class="text-base font-semibold text-ink">API tokens</h2>
    <p class="mt-1 text-sm text-muted">Tokens act as you, with your permissions. Send as <code>Authorization: Bearer &lt;token&gt;</code>. Read-only tokens cannot change anything.</p>
    <form class="mt-3 flex flex-wrap items-end gap-2" @submit.prevent="createToken">
      <label class="block"><span class="text-xs text-body">Name</span><input v-model="tokenName" class="input-field mt-1 !w-48" maxlength="80" required placeholder="e.g. reporting script"></label>
      <label class="block"><span class="text-xs text-body">Access</span>
        <select v-model="tokenScope" class="select-field mt-1 !w-auto"><option value="read">Read-only</option><option value="write">Read and write</option></select></label>
      <button type="submit" class="btn-primary">Create token</button>
    </form>
    <div v-if="newSecret" class="mt-3 rounded-xl border border-amber-400/50 bg-amber-50 p-3 text-sm dark:bg-amber-500/10" role="status">
      <p class="font-medium text-ink">Copy this token now - it will not be shown again.</p>
      <code class="mt-1 block break-all select-all text-xs">{{ newSecret }}</code>
    </div>
    <p v-if="tokenError" role="alert" class="mt-2 text-sm text-rose-600 dark:text-rose-400">{{ tokenError }}</p>
    <ul class="mt-3 divide-y divide-line text-sm">
      <li v-for="t in tokens" :key="t.id" class="flex items-center justify-between gap-3 py-2">
        <span><span class="font-medium text-ink">{{ t.name }}</span> <span class="font-mono text-xs text-muted">{{ t.prefix }}…</span> · {{ t.scope }}
          <span class="text-xs text-muted">· {{ t.last_used_at ? 'used ' + formatDateTime(t.last_used_at) : 'never used' }}{{ t.expires_at ? ' · expires ' + formatDate(t.expires_at) : '' }}</span></span>
        <button type="button" class="btn-ghost text-rose-600 dark:text-rose-400" @click="revokeToken(t.id)">Revoke</button>
      </li>
      <li v-if="!tokens.length" class="py-2 text-muted">No active tokens.</li>
    </ul>

    <template v-if="auth.hasPermission('settings.manage')">
      <h2 class="mt-8 text-base font-semibold text-ink">Webhooks</h2>
      <p class="mt-1 text-sm text-muted">POSTs a signed JSON event (ids and task numbers only, never titles) when something happens. Verify <code>X-DecOps-Signature</code> = HMAC-SHA256 of <code>timestamp.body</code>.</p>
      <form class="mt-3 flex flex-wrap items-end gap-2" @submit.prevent="createHook">
        <label class="block grow"><span class="text-xs text-body">HTTPS URL</span><input v-model="hookUrl" type="url" class="input-field mt-1" required placeholder="https://example.com/decops-hook"></label>
        <button type="submit" class="btn-primary">Add webhook</button>
      </form>
      <div v-if="newHookSecret" class="mt-3 rounded-xl border border-amber-400/50 bg-amber-50 p-3 text-sm dark:bg-amber-500/10" role="status">
        <p class="font-medium text-ink">Signing secret - copy it now, it will not be shown again.</p>
        <code class="mt-1 block break-all select-all text-xs">{{ newHookSecret }}</code>
      </div>
      <p v-if="hookError" role="alert" class="mt-2 text-sm text-rose-600 dark:text-rose-400">{{ hookError }}</p>
      <ul class="mt-3 divide-y divide-line text-sm">
        <li v-for="h in hooks" :key="h.id" class="flex flex-wrap items-center justify-between gap-3 py-2">
          <span class="min-w-0"><span class="break-all text-ink">{{ h.url }}</span>
            <span class="block text-xs text-muted">{{ h.active ? 'active' : 'disabled' }}{{ h.last_status ? ' · last: ' + h.last_status : '' }}</span></span>
          <span class="flex gap-2">
            <button type="button" class="btn-secondary px-3 py-1.5" @click="toggleHook(h.id)">{{ h.active ? 'Disable' : 'Enable' }}</button>
            <button type="button" class="btn-ghost text-rose-600 dark:text-rose-400" @click="deleteHook(h.id)">Delete</button>
          </span>
        </li>
        <li v-if="!hooks.length" class="py-2 text-muted">No webhooks.</li>
      </ul>
    </template>
  </section>
</template>

<script setup lang="ts">
interface Tok { id: string, name: string, prefix: string, scope: string, expires_at: string | null, last_used_at: string | null }
interface Hook { id: string, url: string, active: boolean, last_status: string | null }

const api = useApi()
const auth = useAuth()
const tokens = ref<Tok[]>([])
const hooks = ref<Hook[]>([])
const tokenName = ref('')
const tokenScope = ref('read')
const newSecret = ref('')
const tokenError = ref('')
const hookUrl = ref('')
const newHookSecret = ref('')
const hookError = ref('')

async function loadTokens() { try { tokens.value = await api.get<Tok[]>('/api/v1/integrations/api-tokens') } catch { tokens.value = [] } }
async function loadHooks() {
  if (!auth.hasPermission('settings.manage')) return
  try { hooks.value = await api.get<Hook[]>('/api/v1/integrations/webhooks') } catch { hooks.value = [] }
}
async function createToken() {
  tokenError.value = ''
  newSecret.value = ''
  try {
    const r = await api.post<{ token: string }>('/api/v1/integrations/api-tokens', { name: tokenName.value, scope: tokenScope.value })
    newSecret.value = r.token
    tokenName.value = ''
    await loadTokens()
  } catch (e) { tokenError.value = e instanceof Error ? e.message : 'Could not create the token.' }
}
async function revokeToken(id: string) { try { await api.delete(`/api/v1/integrations/api-tokens/${id}`) } finally { await loadTokens() } }
async function createHook() {
  hookError.value = ''
  newHookSecret.value = ''
  try {
    const r = await api.post<{ secret: string }>('/api/v1/integrations/webhooks', { url: hookUrl.value })
    newHookSecret.value = r.secret
    hookUrl.value = ''
    await loadHooks()
  } catch (e) { hookError.value = e instanceof Error ? e.message : 'Could not add the webhook.' }
}
async function toggleHook(id: string) { try { await api.post(`/api/v1/integrations/webhooks/${id}/toggle`) } finally { await loadHooks() } }
async function deleteHook(id: string) { try { await api.delete(`/api/v1/integrations/webhooks/${id}`) } finally { await loadHooks() } }

onMounted(() => { loadTokens(); loadHooks() })
</script>
