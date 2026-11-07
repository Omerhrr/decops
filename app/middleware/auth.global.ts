// Global auth guard: resolve the session before any page renders.
// Unauthenticated visitors are pushed to /login (public pages excepted);
// accounts that must change their password are held on /account until they do.

const PUBLIC_PATHS = ['/login', '/forgot-password', '/reset-password']

export default defineNuxtRouteMiddleware(async (to) => {
  const auth = useAuth()

  if (!auth.loaded.value) {
    await auth.fetchMe()
  }

  const isPublic = PUBLIC_PATHS.includes(to.path)
  if (!auth.isAuthenticated.value && !isPublic) {
    return navigateTo('/login', { replace: true })
  }
  if (auth.isAuthenticated.value && to.path === '/login') {
    return navigateTo('/', { replace: true })
  }
  if (auth.isAuthenticated.value && auth.user.value?.must_change_password && to.path !== '/account') {
    return navigateTo('/account?forced=1', { replace: true })
  }
})
