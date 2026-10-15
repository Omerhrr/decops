<template>
  <div class="space-y-6">
    <section class="card p-5 sm:p-6" aria-labelledby="org-title">
      <h2 id="org-title" class="text-base font-semibold text-ink">Organization profile</h2>
      <p class="page-subtitle">
        Shown in the PDF header, the footer, and anywhere the workspace refers to your organization.
      </p>

      <form class="mt-5 max-w-xl space-y-4" novalidate @submit.prevent="save">
        <div>
          <label for="org-name" class="block text-sm font-medium text-body">Organization name</label>
          <input
            id="org-name"
            v-model="form.org_name"
            type="text"
            class="input-field mt-1.5"
            maxlength="200"
            required
          >
        </div>
        <div>
          <label for="org-tagline" class="block text-sm font-medium text-body">Tagline</label>
          <input
            id="org-tagline"
            v-model="form.org_tagline"
            type="text"
            class="input-field mt-1.5"
            maxlength="200"
            placeholder="e.g. Operations Management"
          >
        </div>

        <div class="flex items-center gap-3 pt-1">
          <button type="submit" class="btn-primary" :disabled="saving || !dirty">
            {{ saving ? 'Saving' : 'Save changes' }}
          </button>
          <p v-if="savedFlash" role="status" class="text-sm text-brand-700 dark:text-brand-300">Organization updated.</p>
          <p v-if="errorMessage" role="alert" class="text-sm text-rose-600 dark:text-rose-400">{{ errorMessage }}</p>
        </div>
      </form>
    </section>

    <section class="card p-5 sm:p-6">
      <h2 class="text-base font-semibold text-ink">Branding preview</h2>
      <p class="page-subtitle">How the name appears on exports and the interface footer.</p>
      <div class="mt-4 rounded-xl border border-line bg-elevated p-5">
        <div class="flex items-center gap-3">
          <BrandLogo :product-name="form.org_name || 'DecOps'" :tagline="form.org_tagline" />
        </div>
        <p class="mt-3 border-t border-line pt-3 text-xs text-faint">
          {{ [form.org_name, form.org_tagline].filter(Boolean).join(' · ') || 'Organization footer line' }}
        </p>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import type { OrgSettings } from '~/types/api'

const api = useApi()
const form = ref<OrgSettings>({ org_name: '', org_tagline: '' })
const baseline = ref('')
const saving = ref(false)
const savedFlash = ref(false)
const errorMessage = ref('')

const dirty = computed(() => JSON.stringify(form.value) !== baseline.value)

async function load(): Promise<void> {
  const stored = await api.get<OrgSettings>('/api/v1/settings/org')
  form.value = { ...stored }
  baseline.value = JSON.stringify(stored)
}

async function save(): Promise<void> {
  saving.value = true
  errorMessage.value = ''
  try {
    const updated = await api.put<OrgSettings>('/api/v1/settings/org', {
      org_name: form.value.org_name.trim(),
      org_tagline: form.value.org_tagline.trim(),
    })
    form.value = { ...updated }
    baseline.value = JSON.stringify(updated)
    savedFlash.value = true
    window.setTimeout(() => { savedFlash.value = false }, 2500)
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : 'Unable to save organization settings.'
  } finally {
    saving.value = false
  }
}

onMounted(() => void load())
</script>
