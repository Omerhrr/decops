import tailwindcss from '@tailwindcss/vite'

const isProd = process.env.NODE_ENV === 'production'

export default defineNuxtConfig({
  compatibilityDate: '2026-10-01',
  devtools: { enabled: false },

  // The Nuxt server proxies /api/* to FastAPI (see server/api/[...].ts) so the
  // browser only ever talks to this origin (first-party session cookies).
  // The backend location is runtime config: set NUXT_API_BASE (e.g. http://api:8000).
  runtimeConfig: {
    apiBase: 'http://127.0.0.1:8000',
  },

  // Baseline security headers for every page (production only: dev needs HMR).
  routeRules: isProd
    ? {
        '/**': {
          headers: {
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'Referrer-Policy': 'strict-origin-when-cross-origin',
            'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=()',
            'Content-Security-Policy': [
              "default-src 'self'",
              // Nuxt SSR payload + the pre-paint theme script are inline.
              "script-src 'self' 'unsafe-inline'",
              "style-src 'self' 'unsafe-inline'",
              "img-src 'self' data: blob:",
              "font-src 'self' data:",
              "connect-src 'self'",
              // PDF design preview renders a blob: URL in an iframe.
              "frame-src 'self' blob:",
              "object-src 'none'",
              "base-uri 'self'",
              "form-action 'self'",
              "frame-ancestors 'none'",
            ].join('; '),
          },
        },
      }
    : {},

  css: ['~/assets/css/main.css'],

  components: [
    // Flat names: components are addressed by file name only, so nested
    // folders (charts/, settings/) stay organizational, not part of the tag.
    { path: '~/components', pathPrefix: false },
  ],

  vite: {
    plugins: [tailwindcss()],
    server: {
      // Dev only: the app may be reached through a changing preview gateway
      // hostname. Never relevant to production builds.
      allowedHosts: isProd ? undefined : true,
    },
  },

  typescript: {
    strict: true,
    typeCheck: false,
  },

  app: {
    head: {
      title: 'DecOps | Interdec Operations Management',
      htmlAttrs: { lang: 'en' },
      meta: [
        { charset: 'utf-8' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
        { name: 'description', content: 'DecOps Operations Management System for Interdec' },
        { name: 'theme-color', content: '#0b1220' },
      ],
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' },
        { rel: 'manifest', href: '/manifest.webmanifest' },
        { rel: 'apple-touch-icon', href: '/icon-192.png' },
      ],
      script: [
        {
          // Apply the saved theme before first paint to avoid a flash of the
          // wrong mode. Kept tiny and dependency-free on purpose.
          innerHTML: `(function(){try{var s=JSON.parse(localStorage.getItem('decops.appearance')||'{}');var m=s.mode||'system';var dark=m==='dark'||(m!=='light'&&window.matchMedia('(prefers-color-scheme: dark)').matches);var el=document.documentElement;if(dark)el.classList.add('dark');el.dataset.mode=m;el.dataset.accent=s.accent||'emerald';el.dataset.font=s.font||'inter';}catch(e){}})();`,
          tagPosition: 'head',
        },
      ],
    },
  },
})
