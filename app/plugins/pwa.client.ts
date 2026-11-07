// Register the service worker in production only (dev HMR must not be cached).
export default defineNuxtPlugin(() => {
  if (!import.meta.dev && 'serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js').catch(() => { /* optional enhancement */ })
    })
  }
})
