// Appearance state: theme mode (light/dark/system), accent color, and UI font.
// LocalStorage is the fast, flash-free source at boot; saved values also sync
// to the user profile so the look follows the person across devices.

export type ThemeMode = 'light' | 'dark' | 'system'
export type AccentColor = 'emerald' | 'blue' | 'violet' | 'rose' | 'amber' | 'slate'
export type FontChoice = 'inter' | 'system' | 'serif' | 'mono'

export const THEME_MODES: { value: ThemeMode, label: string, hint: string }[] = [
  { value: 'light', label: 'Light', hint: 'Bright surfaces for offices and daylight' },
  { value: 'dark', label: 'Dark', hint: 'Low glare for late shifts' },
  { value: 'system', label: 'System', hint: 'Follows your device setting' },
]

export const ACCENT_COLORS: { value: AccentColor, label: string, swatch: string }[] = [
  { value: 'emerald', label: 'Emerald', swatch: '#059669' },
  { value: 'blue', label: 'Blue', swatch: '#2563eb' },
  { value: 'violet', label: 'Violet', swatch: '#7c3aed' },
  { value: 'rose', label: 'Rose', swatch: '#e11d48' },
  { value: 'amber', label: 'Amber', swatch: '#d97706' },
  { value: 'slate', label: 'Slate', swatch: '#475569' },
]

export const FONT_CHOICES: { value: FontChoice, label: string, stack: string }[] = [
  { value: 'inter', label: 'Inter', stack: '"Inter", "Segoe UI", system-ui, sans-serif' },
  { value: 'system', label: 'System', stack: 'system-ui, sans-serif' },
  { value: 'serif', label: 'Serif', stack: 'Georgia, Cambria, serif' },
  { value: 'mono', label: 'Mono', stack: 'ui-monospace, Menlo, Consolas, monospace' },
]

const STORAGE_KEY = 'decops.appearance'

interface Appearance {
  mode: ThemeMode
  accent: AccentColor
  font: FontChoice
}

const DEFAULTS: Appearance = { mode: 'system', accent: 'emerald', font: 'inter' }

function readLocal(): Appearance {
  if (typeof document === 'undefined') return { ...DEFAULTS }
  const el = document.documentElement
  const fromDom: Appearance = {
    mode: (el.dataset.mode as ThemeMode) || DEFAULTS.mode,
    accent: (el.dataset.accent as AccentColor) || DEFAULTS.accent,
    font: (el.dataset.font as FontChoice) || DEFAULTS.font,
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return fromDom
    const saved = JSON.parse(raw) as Partial<Appearance>
    return { ...DEFAULTS, ...fromDom, ...saved }
  } catch {
    return fromDom
  }
}

export function useAppearance() {
  const state = useState<Appearance>('appearance.state', () => ({ ...DEFAULTS }))
  const systemDark = useState<boolean>('appearance.system-dark', () => false)
  const api = useApi()

  const resolvedMode = computed<'light' | 'dark'>(() => {
    if (state.value.mode !== 'system') return state.value.mode
    return systemDark.value ? 'dark' : 'light'
  })

  function apply(): void {
    if (typeof document === 'undefined') return
    const el = document.documentElement
    el.classList.toggle('dark', resolvedMode.value === 'dark')
    el.dataset.mode = state.value.mode
    el.dataset.accent = state.value.accent
    el.dataset.font = state.value.font
  }

  function saveLocal(): void {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state.value))
    } catch {
      /* storage unavailable (private mode) */
    }
  }

  let syncTimer: ReturnType<typeof setTimeout> | null = null
  function syncToServer(): void {
    if (!useAuth().isAuthenticated.value) return
    if (syncTimer) clearTimeout(syncTimer)
    syncTimer = setTimeout(() => {
      void api.put('/api/v1/me/preferences', {
        theme_mode: state.value.mode,
        accent_color: state.value.accent,
        font_family: state.value.font,
      }).catch(() => undefined)
    }, 600)
  }

  function set(mode: ThemeMode | null, accent: AccentColor | null, font: FontChoice | null): void {
    if (mode) state.value.mode = mode
    if (accent) state.value.accent = accent
    if (font) state.value.font = font
    apply()
    saveLocal()
    syncToServer()
  }

  function setMode(mode: ThemeMode): void { set(mode, null, null) }
  function setAccent(accent: AccentColor): void { set(null, accent, null) }
  function setFont(font: FontChoice): void { set(null, null, font) }

  function toggleMode(): void {
    setMode(resolvedMode.value === 'dark' ? 'light' : 'dark')
  }

  function init(): void {
    if (typeof window === 'undefined') return
    state.value = readLocal()
    const query = window.matchMedia('(prefers-color-scheme: dark)')
    systemDark.value = query.matches
    query.addEventListener('change', (event) => {
      systemDark.value = event.matches
      apply()
    })
    apply()
  }

  // Adopt server-side preferences when the local device has none saved yet,
  // so a fresh browser inherits the user's saved look.
  function hydrateFromUser(preferences: Record<string, string> | undefined): void {
    if (!preferences || typeof localStorage === 'undefined') return
    if (localStorage.getItem(STORAGE_KEY)) return
    set(
      (preferences.theme_mode as ThemeMode) || null,
      (preferences.accent_color as AccentColor) || null,
      (preferences.font_family as FontChoice) || null,
    )
  }

  return {
    state,
    resolvedMode,
    systemDark,
    init,
    apply,
    setMode,
    setAccent,
    setFont,
    toggleMode,
    hydrateFromUser,
  }
}
