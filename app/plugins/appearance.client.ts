// Applies saved appearance after hydration. The inline head script already
// set the html attributes pre-paint (no visual flash); loading the Vue state
// only after hydration keeps the first client render identical to the SSR
// markup, avoiding hydration mismatches on the settings controls.

export default defineNuxtPlugin(() => {
  onNuxtReady(() => {
    const appearance = useAppearance()
    appearance.init()

    const auth = useAuth()
    if (auth.isAuthenticated.value) {
      appearance.hydrateFromUser(auth.user.value?.preferences)
    }
  })
})
