# syntax=docker/dockerfile:1.7
# ---- DecOps web (Nuxt 4 / Nitro) -------------------------------------------
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json nuxt.config.ts ./
RUN npm ci
COPY app ./app
COPY server ./server
COPY public ./public
RUN npm run build

FROM node:22-alpine AS runtime
ENV NODE_ENV=production PORT=3000 HOST=0.0.0.0
WORKDIR /app
COPY --from=build --chown=node:node /app/.output ./.output
USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:'+(process.env.PORT||3000)+'/login').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", ".output/server/index.mjs"]
