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

  vite: {
    plugins: [tailwindcss()],
  },

  typescript: {
    strict: true,
    typeCheck: false,
  },

  app: {
    head: {
      title: 'DecOps — Interdec Operations Management',
      htmlAttrs: { lang: 'en' },
      meta: [
        { charset: 'utf-8' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
        { name: 'description', content: 'DecOps Operations Management System for Interdec' },
      ],
    },
  },
})
