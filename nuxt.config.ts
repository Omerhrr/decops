import tailwindcss from '@tailwindcss/vite'

export default defineNuxtConfig({
  compatibilityDate: '2026-10-01',
  devtools: { enabled: false },

  // FastAPI backend runs on 127.0.0.1:8000; the Nuxt server proxies /api/*
  // so the browser only ever talks to this origin (first-party session cookies).
  routeRules: {
    '/api/**': { proxy: { to: 'http://127.0.0.1:8000/api/**' } },
  },

  css: ['~/assets/css/main.css'],

  components: [
    // Flat names: components are addressed by file name only, so nested
    // folders (charts/, settings/) stay organizational, not part of the tag.
    { path: '~/components', pathPrefix: false },
  ],

  vite: {
    plugins: [tailwindcss()],
    server: {
      // The app is reached through an ephemeral preview/proxy gateway whose
      // hostname changes per session (ws-*.fcapp.run). Vite blocks unknown
      // Host headers by default; allow any host in this sandbox dev setup.
      allowedHosts: true,
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
      link: [{ rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' }],
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
