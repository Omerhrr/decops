// Reverse proxy: /api/** -> FastAPI. Runtime-configurable (NUXT_API_BASE) so the
// same build works locally, in Docker networks and on Render.
// Streams request/response bodies (uploads, PDF/CSV downloads) and passes
// cookies / Set-Cookie through untouched.

export default defineEventHandler((event) => {
  const { apiBase } = useRuntimeConfig(event)
  // Render's private-network "hostport" has no scheme; accept both forms.
  const base = /^https?:\/\//.test(apiBase) ? apiBase : `http://${apiBase}`
  const target = `${base.replace(/\/$/, '')}${event.path}`
  const clientIp = getRequestIP(event, { xForwardedFor: true })
  return proxyRequest(event, target, {
    headers: clientIp ? { 'x-forwarded-for': clientIp } : {},
  })
})
