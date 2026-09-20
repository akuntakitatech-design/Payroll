# ---- Stage 1: build React (CRA + craco) ----
FROM node:20-alpine AS build
WORKDIR /app

# Backend URL yang di-bake saat build.
#  - kosong (default)  => frontend memanggil /api relatif (di-proxy Nginx ke backend)
#  - https://api.domain => frontend memanggil backend langsung (butuh CORS)
ARG REACT_APP_BACKEND_URL=
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL \
    DISABLE_EMERGENT_OVERLAY=true \
    GENERATE_SOURCEMAP=false \
    CI=false \
    DISABLE_ESLINT_PLUGIN=true

COPY package.json yarn.lock* ./
# Paket khusus Emergent preview tidak dibutuhkan di produksi -> dilepas agar build ringan
RUN node -e "const fs=require('fs');const p=JSON.parse(fs.readFileSync('package.json'));for(const k of Object.keys(p.dependencies||{}))if(k.startsWith('@emergentbase/'))delete p.dependencies[k];for(const k of Object.keys(p.devDependencies||{}))if(k.startsWith('@emergentbase/'))delete p.devDependencies[k];fs.writeFileSync('package.json',JSON.stringify(p,null,2));" \
    && yarn install --network-timeout 600000

COPY . .
RUN yarn build

# ---- Stage 2: serve with Nginx ----
FROM nginx:1.27-alpine

# Upstream backend internal (nama service/container Coolify), bisa dioverride via env
ENV BACKEND_UPSTREAM=http://backend:8001 \
    CLIENT_MAX_BODY_SIZE=25m

RUN apk add --no-cache curl
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/build /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1/healthz || exit 1
