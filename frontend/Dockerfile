# =============================================================================
# Frontend — multi-stage. `dev` roda o Vite; `prod` serve estatico por nginx.
# Nenhum segredo embutido: VITE_API_URL entra em build/runtime, nao em imagem.
# =============================================================================

# ---------- stage 1: dependencias -------------------------------------------
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund

# ---------- stage 2: dev ----------------------------------------------------
FROM node:22-alpine AS dev
WORKDIR /app
ENV NODE_ENV=development
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN addgroup -g 10001 app && adduser -u 10001 -G app -D app && chown -R app:app /app
USER app
EXPOSE 5173
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=6 \
  CMD wget -q --spider http://localhost:5173/ || exit 1
CMD ["npm", "run", "dev"]

# ---------- stage 3: build --------------------------------------------------
FROM node:22-alpine AS build
WORKDIR /app
# A URL da API entra no bundle em tempo de build (Vite). Nao e segredo.
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# ---------- stage 4: producao ------------------------------------------------
FROM nginx:1.27-alpine AS prod
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

# A imagem oficial do nginx assume que o processo roda como root: os diretorios
# de cache e o arquivo de PID nascem pertencendo a root. Com `USER nginx` — que
# e o que queremos, para o container nao ter privilegio — o nginx morre no
# arranque com `mkdir() "/var/cache/nginx/client_temp" failed (13: Permission
# denied)` e o container entra em loop de reinicio.
#
# Isto so aparece RODANDO: o build passa, a imagem sobe, e a falha acontece no
# primeiro comando do processo.
RUN mkdir -p /var/cache/nginx/client_temp /var/cache/nginx/proxy_temp \
             /var/cache/nginx/fastcgi_temp /var/cache/nginx/uwsgi_temp \
             /var/cache/nginx/scgi_temp \
 && chown -R nginx:nginx /var/cache/nginx \
 && touch /var/run/nginx.pid \
 && chown nginx:nginx /var/run/nginx.pid

EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=5 \
  CMD wget -q --spider http://localhost:8080/ || exit 1
USER nginx
CMD ["nginx", "-g", "daemon off;"]
