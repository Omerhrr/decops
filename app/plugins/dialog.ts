// Modal dialog behavior: Escape closes the dialog and the first focusable
// control receives focus when it opens, so keyboard users are never stranded.
// Focus returns to the previously focused element on close.

const cleanups = new WeakMap<Element, () => void>()

interface DialogBinding {
  close?: () => void
}

export default defineNuxtPlugin((nuxtApp) => {
  nuxtApp.vueApp.directive('dialog', {
    mounted(el: HTMLElement, binding: { value?: DialogBinding }) {
      const close = binding.value?.close
      const previouslyFocused = document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null

      const onKeydown = (event: KeyboardEvent) => {
        if (event.key === 'Escape' && close) {
          event.stopPropagation()
          close()
        }
      }
      document.addEventListener('keydown', onKeydown)

      const target = el.querySelector<HTMLElement>('[data-autofocus]')
        ?? el.querySelector<HTMLElement>('input:not([type="hidden"]), textarea, select, button')
      target?.focus()

      cleanups.set(el, () => {
        document.removeEventListener('keydown', onKeydown)
        previouslyFocused?.focus()
      })
    },
    unmounted(el: HTMLElement) {
      cleanups.get(el)?.()
      cleanups.delete(el)
    },
  })
})
