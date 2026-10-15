<template>
  <div class="space-y-6">
    <section class="card p-5 sm:p-6" aria-labelledby="pdf-design-title">
      <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 id="pdf-design-title" class="text-base font-semibold text-ink">PDF export design</h2>
          <p class="page-subtitle">
            Controls the look of every PDF report (WeasyPrint): cover, header, footer, tables.
          </p>
        </div>
        <button type="button" class="btn-secondary shrink-0" :disabled="previewing" @click="preview">
          <svg v-if="previewing" class="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          {{ previewing ? 'Rendering' : 'Preview PDF' }}
        </button>
      </div>

      <div v-if="design" class="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div class="space-y-5">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label for="pdf-paper" class="block text-sm font-medium text-body">Paper size</label>
              <select id="pdf-paper" v-model="design.paper_size" class="input-field mt-1.5 w-full">
                <option value="A4">A4</option>
                <option value="Letter">Letter</option>
              </select>
            </div>
            <div>
              <label for="pdf-orientation" class="block text-sm font-medium text-body">Orientation</label>
              <select id="pdf-orientation" v-model="design.orientation" class="input-field mt-1.5 w-full">
                <option value="portrait">Portrait</option>
                <option value="landscape">Landscape</option>
              </select>
            </div>
          </div>

          <div class="grid grid-cols-2 gap-4">
            <div>
              <label for="pdf-accent" class="block text-sm font-medium text-body">Accent color</label>
              <div class="mt-1.5 flex items-center gap-2">
                <input
                  id="pdf-accent"
                  v-model="design.accent_color"
                  type="color"
                  class="h-10 w-12 cursor-pointer rounded-lg border border-line-strong bg-surface p-1"
                  aria-label="Accent color picker"
                >
                <input
                  v-model="design.accent_color"
                  type="text"
                  class="input-field font-mono text-xs"
                  maxlength="7"
                  aria-label="Accent hex value"
                >
              </div>
            </div>
            <div>
              <label for="pdf-font" class="block text-sm font-medium text-body">Document font</label>
              <select id="pdf-font" v-model="design.font_family" class="input-field mt-1.5 w-full">
                <option value="sans">Sans (DejaVu Sans)</option>
                <option value="serif">Serif (DejaVu Serif)</option>
                <option value="mono">Mono (DejaVu Mono)</option>
              </select>
            </div>
          </div>

          <div>
            <label for="pdf-size" class="block text-sm font-medium text-body">
              Body font size: {{ design.font_size_pt }}pt
            </label>
            <input
              id="pdf-size"
              v-model.number="design.font_size_pt"
              type="range"
              min="7"
              max="12"
              step="0.5"
              class="mt-2 w-full accent-brand-600"
            >
          </div>

          <div>
            <span class="block text-sm font-medium text-body">Table style</span>
            <div class="mt-2 flex gap-2" role="radiogroup" aria-label="Table style">
              <button
                v-for="style in ['striped', 'plain', 'bordered']"
                :key="style"
                type="button"
                role="radio"
                :aria-checked="design.table_style === style"
                class="rounded-lg border px-3 py-1.5 text-sm capitalize transition-colors"
                :class="design.table_style === style
                  ? 'border-brand-500 bg-brand-50 text-brand-700 dark:bg-brand-500/10 dark:text-brand-300'
                  : 'border-line text-body hover:border-line-strong'"
                @click="design.table_style = style as PdfDesign['table_style']"
              >
                {{ style }}
              </button>
            </div>
          </div>

          <div>
            <label for="pdf-footer" class="block text-sm font-medium text-body">Footer text</label>
            <input
              id="pdf-footer"
              v-model="design.footer_text"
              type="text"
              class="input-field mt-1.5"
              maxlength="200"
              placeholder="Confidential. For internal use only."
            >
          </div>

          <fieldset class="space-y-2.5">
            <legend class="text-sm font-medium text-body">Document options</legend>
            <label v-for="toggle in TOGGLES" :key="toggle.key" class="flex items-center gap-3 text-sm text-body">
              <input
                v-model="design[toggle.key]"
                type="checkbox"
                class="h-4 w-4 rounded border-line-strong text-brand-600 focus:ring-brand-500/25 accent-brand-600"
              >
              {{ toggle.label }}
            </label>
          </fieldset>
        </div>

        <div>
          <p class="text-sm font-medium text-body">Live document sketch</p>
          <div class="mt-2 overflow-hidden rounded-xl border border-line bg-elevated p-4">
            <div class="rounded-lg bg-white p-4 shadow-sm dark:bg-[#122036]">
              <div class="flex items-center gap-2 border-b pb-2" :style="{ borderColor: design.accent_color + '66' }">
                <span v-if="design.header_show_logo" class="flex h-5 w-5 items-center justify-center rounded" :style="{ backgroundColor: design.accent_color }">
                  <span class="text-[9px] font-bold text-white">D</span>
                </span>
                <span v-if="design.header_show_org_name" class="text-[10px] font-bold" :style="{ color: design.accent_color }">Interdec</span>
                <span class="ml-auto text-[9px] text-slate-400">{{ design.paper_size }} · {{ design.orientation }}</span>
              </div>
              <div class="mt-3">
                <p class="text-[10px] font-bold" :style="{ color: design.accent_color }">Task Register Report</p>
                <table class="mt-2 w-full border-collapse text-[8px]">
                  <thead>
                    <tr :style="design.table_style === 'bordered'
                      ? { background: design.accent_color + '1a' }
                      : { background: design.accent_color, color: '#fff' }">
                      <th
                        v-for="col in ['Task', 'Title', 'Status', 'Due']"
                        :key="col"
                        class="px-1.5 py-1 text-left font-semibold"
                        :class="design.table_style === 'bordered' ? 'text-slate-800 dark:text-slate-200' : ''"
                        :style="design.table_style !== 'bordered' ? { color: '#fff' } : {}"
                      >
                        {{ col }}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(row, i) in [['TSK-2026-0007', 'Vendor invoice reconciliation', 'In progress', '02 Nov'], ['TSK-2026-0011', 'Quarterly compliance audit', 'Review', '28 Oct'], ['TSK-2026-0014', 'Warehouse stock migration', 'Open', '15 Dec']]"
                      :key="i"
                      :class="design.table_style === 'bordered' ? 'border' : ''"
                      :style="design.table_style === 'striped' && i % 2 === 1 ? { background: design.accent_color + '14' } : {}"
                    >
                      <td
                        v-for="cell in row"
                        :key="cell"
                        class="px-1.5 py-1 text-slate-700 dark:text-slate-300"
                      >
                        {{ cell }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div
                class="mt-3 flex items-center justify-between border-t pt-2 text-[8px] text-slate-400"
                :style="{ borderColor: design.accent_color + '66' }"
              >
                <span>{{ design.footer_text }}</span>
                <span v-if="design.show_page_numbers">1 / 4</span>
              </div>
            </div>
            <p class="mt-3 text-xs text-muted">
              Sketch only. Use Preview PDF for the exact WeasyPrint output with sample data.
            </p>
          </div>
        </div>
      </div>

      <div class="mt-6 flex items-center gap-3 border-t border-line pt-4">
        <button type="button" class="btn-primary" :disabled="saving || !dirty" @click="save">
          {{ saving ? 'Saving' : 'Save design' }}
        </button>
        <button v-if="dirty" type="button" class="btn-ghost" @click="reset">Discard changes</button>
        <p v-if="savedFlash" role="status" class="text-sm text-brand-700 dark:text-brand-300">PDF design saved.</p>
        <p v-if="errorMessage" role="alert" class="text-sm text-rose-600 dark:text-rose-400">{{ errorMessage }}</p>
      </div>
    </section>

    <section class="card p-5 sm:p-6">
      <h2 class="text-base font-semibold text-ink">Where PDFs appear</h2>
      <ul class="mt-3 space-y-2 text-sm text-body">
        <li class="flex items-start gap-2">
          <span class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" aria-hidden="true" />
          Reports page: export the task register, task completion report, and department workload as PDF.
        </li>
        <li class="flex items-start gap-2">
          <span class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" aria-hidden="true" />
          Every export is audited and covers only the task records you are authorized to view.
        </li>
        <li class="flex items-start gap-2">
          <span class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" aria-hidden="true" />
          The design applies to all users automatically; no per-user configuration needed.
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts">
import type { PdfDesign } from '~/types/api'

const TOGGLES = [
  { key: 'show_cover_page', label: 'Cover page' },
  { key: 'header_show_logo', label: 'Logo in header' },
  { key: 'header_show_org_name', label: 'Organization name in header' },
  { key: 'show_page_numbers', label: 'Page numbers' },
] as const

const api = useApi()
const design = ref<PdfDesign | null>(null)
const baseline = ref<string>('')
const saving = ref(false)
const previewing = ref(false)
const savedFlash = ref(false)
const errorMessage = ref('')

const dirty = computed(() =>
  design.value !== null && JSON.stringify(normalize(design.value)) !== baseline.value,
)

function normalize(value: PdfDesign): PdfDesign {
  return {
    ...value,
    accent_color: value.accent_color.toUpperCase(),
  }
}

async function load(): Promise<void> {
  const stored = await api.get<PdfDesign>('/api/v1/settings/pdf-design')
  design.value = { ...stored }
  baseline.value = JSON.stringify(normalize(stored))
}

function reset(): void {
  void load()
}

async function save(): Promise<void> {
  if (!design.value) return
  saving.value = true
  errorMessage.value = ''
  try {
    const updated = await api.put<PdfDesign>('/api/v1/settings/pdf-design', {
      paper_size: design.value.paper_size,
      orientation: design.value.orientation,
      accent_color: design.value.accent_color,
      font_family: design.value.font_family,
      font_size_pt: design.value.font_size_pt,
      show_cover_page: design.value.show_cover_page,
      header_show_logo: design.value.header_show_logo,
      header_show_org_name: design.value.header_show_org_name,
      footer_text: design.value.footer_text,
      show_page_numbers: design.value.show_page_numbers,
      table_style: design.value.table_style,
    })
    design.value = { ...updated }
    baseline.value = JSON.stringify(normalize(updated))
    savedFlash.value = true
    window.setTimeout(() => { savedFlash.value = false }, 2500)
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : 'Unable to save the PDF design.'
  } finally {
    saving.value = false
  }
}

async function preview(): Promise<void> {
  if (!design.value) return
  previewing.value = true
  errorMessage.value = ''
  try {
    const { blob } = await api.download('/api/v1/settings/pdf-preview', {
      design: {
        paper_size: design.value.paper_size,
        orientation: design.value.orientation,
        accent_color: design.value.accent_color,
        font_family: design.value.font_family,
        font_size_pt: design.value.font_size_pt,
        show_cover_page: design.value.show_cover_page,
        header_show_logo: design.value.header_show_logo,
        header_show_org_name: design.value.header_show_org_name,
        footer_text: design.value.footer_text,
        show_page_numbers: design.value.show_page_numbers,
        table_style: design.value.table_style,
      },
    })
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank', 'noopener')
    window.setTimeout(() => URL.revokeObjectURL(url), 30_000)
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : 'Unable to render the preview.'
  } finally {
    previewing.value = false
  }
}

onMounted(() => void load())
</script>
