// Global auth guard: resolve the session before any page renders.
// Unauthenticated visitors are pushed to /login (except on /login itself).

export default defineNuxtRouteMiddleware(async (to) => {
  const auth = useAuth()

  if (!auth.loaded.value) {
    await auth.fetchMe()
  }

  const isLoginPage = to.path === '/login'
  if (!auth.isAuthenticated.value && !isLoginPage) {
    return navigateTo('/login', { replace: true })
  }
  if (auth.isAuthenticated.value && isLoginPage) {
    return navigateTo('/', { replace: true })
  }
})
